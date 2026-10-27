import io
import json
import math
from pathlib import Path
import posixpath
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from email.message import Message
from urllib.error import URLError
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pymupdf
from PIL import Image
from typst_pptx import compile_pptx
from typst_pptx.ooxml import NS

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'packages/pptx-media/lib.typ'
REL = {'r': 'http://schemas.openxmlformats.org/package/2006/relationships'}


@unittest.skipUnless(shutil.which('typst'), 'Typst CLI required')
class CompilerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.work = Path(self.tmp.name)
        self.source = self.work / 'slides.typ'
        self.output = self.work / 'slides.pptx'
        self.import_line = '#import "../packages/pptx-media/lib.typ": media\n'
        self.header = self.import_line + '#set page(width: 400pt, height: 300pt, margin: 20pt)\n'
        Image.new('RGB', (160, 90), 'red').save(self.work / 'thumb.png')
        shutil.copy(ROOT / 'tests/fixtures/video.mp4', self.work / 'video.mp4')

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, body):
        self.source.write_text(self.header + body)

    def compile(self, **kw):
        return compile_pptx(self.source, self.output, root=ROOT, **kw)

    def xml(self, archive, name):
        return ET.fromstring(archive.read(name))

    def assert_package(self, archive):
        names = set(archive.namelist())
        for name in names:
            if name.endswith('.xml') or name.endswith('.rels'):
                ET.fromstring(archive.read(name))
            if name.endswith('.rels'):
                base = posixpath.dirname(posixpath.dirname(name))
                for rel in ET.fromstring(archive.read(name)):
                    if rel.get('TargetMode') != 'External':
                        target = posixpath.normpath(posixpath.join(base, rel.get('Target')))
                        self.assertIn(target, names, (name, target))

    def test_background_formats_and_page_count(self):
        self.write('First page\n#pagebreak()\nSecond page')
        for fmt in ('png', 'jpeg', 'svg'):
            with self.subTest(fmt=fmt):
                self.compile(background_format=fmt)
                with ZipFile(self.output) as archive:
                    self.assert_package(archive)
                    slides = [n for n in archive.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
                    self.assertEqual(len(slides), 2)
                    for name in slides:
                        root = self.xml(archive, name)
                        self.assertIsNotNone(root.find('p:cSld/p:bg/p:bgPr/a:blipFill', NS))
                        self.assertEqual(len(root.findall('.//p:sp', NS)), 0)
                    if fmt == 'png':
                        images = [n for n in archive.namelist() if n.endswith('.png')]
                        image = Image.open(io.BytesIO(archive.read(images[0])))
                        self.assertEqual(image.size, (1067, 800))  # 400 x 300pt at 192 PPI
                    if fmt == 'svg':
                        self.assertEqual(sum(n.endswith('.svg') for n in archive.namelist()), 2)
                    if fmt == 'jpeg':
                        images = [n for n in archive.namelist() if n.endswith('.jpeg')]
                        self.assertEqual(Image.open(io.BytesIO(archive.read(images[0]))).format, 'JPEG')

    def test_editable_text_paths_images_and_order(self):
        self.write('Editable text 한글\n#rect(width: 80pt, height: 30pt, fill: blue)\n#image("thumb.png", width: 80pt)')
        self.compile(mode='editable', vector_format='native')
        with ZipFile(self.output) as archive:
            self.assert_package(archive)
            root = self.xml(archive, 'ppt/slides/slide1.xml')
            self.assertIn('Editable text', ''.join(root.itertext()))
            self.assertIn('한글', ''.join(root.itertext()))
            self.assertIsNotNone(root.find('.//a:custGeom', NS))
            self.assertIsNotNone(root.find('.//p:pic', NS))
            self.assertIsNone(root.find('.//p:bg', NS))
            ids = [e.get('id') for e in root.findall('.//p:cNvPr', NS)]
            self.assertEqual(len(ids), len(set(ids)))

    def test_default_background_uses_real_svg(self):
        self.write('#circle(radius: 25pt, fill: blue)')
        self.compile()
        with ZipFile(self.output) as archive:
            self.assert_package(archive)
            svgs = [n for n in archive.namelist() if n.endswith('.svg')]
            self.assertEqual(len(svgs), 1)
            svg = self.xml(archive, svgs[0])
            self.assertTrue(any(e.tag.endswith('}path') for e in svg.iter()))
            self.assertFalse(any(e.tag.endswith('}image') for e in svg.iter()))

    def test_default_editable_vectors_are_svg_pictures(self):
        self.write('Editable text\n#rect(width: 80pt, height: 30pt, radius: 5pt, fill: blue, stroke: (paint: red, thickness: 2pt, dash: "dashed"))')
        self.compile(mode='editable')
        with ZipFile(self.output) as archive:
            self.assert_package(archive)
            root = self.xml(archive, 'ppt/slides/slide1.xml')
            self.assertIn('Editable text', ''.join(root.itertext()))
            self.assertIsNone(root.find('.//a:custGeom', NS))
            svg_blips = root.findall('.//{http://schemas.microsoft.com/office/drawing/2016/SVG/main}svgBlip')
            self.assertTrue(svg_blips)
            svgs = [n for n in archive.namelist() if n.endswith('.svg')]
            self.assertTrue(svgs)
            for name in svgs:
                svg = self.xml(archive, name)
                self.assertTrue(any(e.tag.endswith('}path') for e in svg.iter()))
                self.assertFalse(any(e.tag.endswith('}image') for e in svg.iter()))
            pngs = [n for n in archive.namelist() if n.endswith('.png')]
            self.assertTrue(any(Image.open(io.BytesIO(archive.read(n))).getchannel('A').getextrema()[1] > 0 for n in pngs))

    def test_portrait_image_rotation_scale_and_reflection(self):
        image = Image.new('RGB', (80, 160), 'red')
        image.paste('blue', (0, 80, 80, 160))
        image.save(self.work / 'portrait.png')
        picture = 'image("portrait.png", height: 120pt)'
        bodies = [picture,
            'rotate(90deg, reflow: true, ' + picture + ')',
            'rotate(270deg, reflow: true, ' + picture + ')',
            'rotate(33deg, reflow: true, ' + picture + ')',
            'scale(x: -100%, reflow: true, ' + picture + ')',
            'scale(y: -100%, reflow: true, ' + picture + ')',
            'rotate(90deg, reflow: true, scale(x: -100%, ' + picture + '))']
        self.write('\n#pagebreak()\n'.join('#' + body for body in bodies))
        pdf = self.work / 'expected.pdf'
        subprocess.run(['typst', 'compile', str(self.source), str(pdf), '--root', str(ROOT)], check=True)
        self.compile(mode='editable')
        with pymupdf.open(pdf) as document, ZipFile(self.output) as archive:
            self.assertEqual(len(document), len(bodies))
            self.assert_package(archive)
            for number, page in enumerate(document, 1):
                block = next(b for b in page.get_text('dict')['blocks'] if b['type'] == 1)
                root = self.xml(archive, f'ppt/slides/slide{number}.xml')
                xf = root.find('.//p:pic/p:spPr/a:xfrm', NS)
                off, ext = xf.find('a:off', NS), xf.find('a:ext', NS)
                x, y = int(off.get('x'))/12700, int(off.get('y'))/12700
                w, h = int(ext.get('cx'))/12700, int(ext.get('cy'))/12700
                # Rotation must not swap the original image's width/height.
                self.assertAlmostEqual(w, 60, places=3)
                self.assertAlmostEqual(h, 120, places=3)
                angle = math.radians(int(xf.get('rot', 0))/60000)
                for u, v in [(0, 0), (1, 0), (0, 1), (1, 1), (.5, .5)]:
                    dx, dy = (u-.5)*w, (v-.5)*h
                    if xf.get('flipV') == '1':
                        dy = -dy
                    actual = (x+w/2 + math.cos(angle)*dx-math.sin(angle)*dy,
                              y+h/2 + math.sin(angle)*dx+math.cos(angle)*dy)
                    a, b, c, d, e, f = block['transform']
                    expected = (a*u+c*v+e, b*u+d*v+f)
                    for got, want in zip(actual, expected):
                        self.assertAlmostEqual(got, want, places=3)

    def test_local_video_embedded_with_thumbnail_and_playback(self):
        self.write('#media("video.mp4", thumbnail: path("thumb.png"), width: 160pt, height: 90pt, playback: (autoplay: true, loop: true, muted: true))')
        for mode in ('background', 'editable'):
            with self.subTest(mode=mode):
                self.compile(mode=mode)
                with ZipFile(self.output) as archive:
                    self.assert_package(archive)
                    root = self.xml(archive, 'ppt/slides/slide1.xml')
                    self.assertEqual(root.find('.//p:cMediaNode', NS).get('vol'), '0')
                    self.assertEqual(root.find('.//p:cMediaNode/p:cTn', NS).get('repeatCount'), 'indefinite')
                    self.assertEqual(root.find('.//p:cMediaNode/p:cTn/p:stCondLst/p:cond', NS).get('delay'), 'indefinite')
                    self.assertIsNotNone(root.find(".//p:cmd[@cmd='playFrom(0.0)']", NS))
                    self.assertIsNotNone(root.find(".//p:ext[@uri='{DAA4B4D4-6D71-4841-9C94-3DE7FCFB9230}']/p14:media", NS))
                    self.assertIsNotNone(root.find('.//p14:media', NS).get('{'+NS['r']+'}embed'))
                    video = [n for n in archive.namelist() if n.endswith('.mp4')]
                    self.assertEqual(len(video), 1)
                    self.assertEqual(archive.read(video[0]), (self.work / 'video.mp4').read_bytes())

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg tools required')
    def test_codec_confirmation_conversion_and_preserved_output(self):
        original = self.work / 'incompatible.avi'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(self.work / 'video.mp4'),
                        '-c:v', 'mpeg4', '-c:a', 'pcm_s16le', str(original)], check=True)
        original_bytes = original.read_bytes()
        self.write('#media("incompatible.avi", width: 160pt, height: 90pt)')
        self.output.write_bytes(b'previous')
        with self.assertRaisesRegex(RuntimeError, 'declined'):
            self.compile(confirm_video_conversion=lambda *args: False)
        self.assertEqual(self.output.read_bytes(), b'previous')
        self.compile(confirm_video_conversion=lambda *args: True)
        with ZipFile(self.output) as archive:
            self.assert_package(archive)
            video = next(n for n in archive.namelist() if n.endswith('.mp4'))
            extracted = self.work / 'extracted.mp4'
            extracted.write_bytes(archive.read(video))
            from typst_pptx.video import inspect_video
            self.assertTrue(inspect_video(extracted, 'mp4').compatible)
            self.assertFalse(any(n.endswith('.avi') for n in archive.namelist()))
        self.assertEqual(original.read_bytes(), original_bytes)

    def test_autoplay_loop_defaults_survive_wrapper_and_explicit_override(self):
        self.write('''#let video(..options) = media("video.mp4", width: 160pt, height: 90pt,
  playback: (autoplay: true, loop: true, ..options.named()))
#video()
#pagebreak()
#video(autoplay: false)
''')
        self.compile()
        with ZipFile(self.output) as archive:
            for page, automatic in [(1, True), (2, False)]:
                root = self.xml(archive, f'ppt/slides/slide{page}.xml')
                main = root.find(".//p:cTn[@nodeType='mainSeq']", NS)
                first = main.find('p:childTnLst/p:par/p:cTn', NS)
                self.assertEqual(first.find('p:stCondLst/p:cond', NS).get('delay'),
                                 '0' if automatic else 'indefinite')
                effect = main.find(".//p:cTn[@presetClass='mediacall']", NS)
                self.assertEqual(effect.get('nodeType'), 'afterEffect' if automatic else 'clickEffect')
                controller = root.find('.//p:cMediaNode/p:cTn', NS)
                self.assertEqual(controller.get('repeatCount'), 'indefinite')

    def test_video_and_thumbnail_keep_original_aspect_in_wide_slot(self):
        self.write('#media("video.mp4", thumbnail: path("thumb.png"), width: 300pt, height: 90pt)')
        for mode in ('background', 'editable'):
            with self.subTest(mode=mode):
                self.compile(mode=mode)
                with ZipFile(self.output) as archive:
                    self.assert_package(archive)
                    root = self.xml(archive, 'ppt/slides/slide1.xml')
                    video = next(p for p in root.findall('.//p:pic', NS)
                        if p.find('p:nvPicPr/p:nvPr/a:videoFile', NS) is not None)
                    transform = video.find('p:spPr/a:xfrm', NS)
                    ext = transform.find('a:ext', NS)
                    off = transform.find('a:off', NS)
                    self.assertAlmostEqual(int(ext.get('cx'))/12700, 160, places=3)
                    self.assertAlmostEqual(int(ext.get('cy'))/12700, 90, places=3)
                    self.assertAlmostEqual(int(off.get('x'))/12700, 90, places=3)
                    self.assertAlmostEqual(int(off.get('y'))/12700, 20, places=3)
                    rid = video.find('p:blipFill/a:blip', NS).get('{'+NS['r']+'}embed')
                    rels = self.xml(archive, 'ppt/slides/_rels/slide1.xml.rels')
                    target = next(r.get('Target') for r in rels if r.get('Id') == rid)
                    poster = Image.open(io.BytesIO(archive.read(posixpath.normpath('ppt/slides/'+target))))
                    self.assertAlmostEqual(poster.width/poster.height, 16/9, delta=.02)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_portrait_video_in_landscape_slot(self):
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(self.work/'video.mp4'),
            '-vf', 'scale=90:160,setsar=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'copy',
            str(self.work/'portrait.mp4')], check=True)
        self.write('#media("portrait.mp4", width: 300pt, height: 90pt)')
        self.compile()
        with ZipFile(self.output) as archive:
            root = self.xml(archive, 'ppt/slides/slide1.xml')
            ext = root.find('.//p:pic/p:spPr/a:xfrm/a:ext', NS)
            self.assertAlmostEqual(int(ext.get('cx'))/int(ext.get('cy')), 9/16, places=5)

    def test_remote_video_embedded_and_click_volume(self):
        url = 'https://example.org/clip.mp4?a=1&b=2'
        self.write('#media("' + url + '", width: 160pt, height: 90pt, playback: (volume: 0.25))')
        data = (self.work / 'video.mp4').read_bytes()
        for mode in ('background', 'editable'):
            with self.subTest(mode=mode):
                response = io.BytesIO(data)
                response.headers = Message()
                response.headers['Content-Type'] = 'video/mp4'
                response.geturl = lambda: url
                with patch('typst_pptx.compiler.urlopen', return_value=response) as download:
                    self.compile(mode=mode)
                    download.assert_called_once_with(url, timeout=60)
                with ZipFile(self.output) as archive:
                    self.assert_package(archive)
                    rels = self.xml(archive, 'ppt/slides/_rels/slide1.xml.rels')
                    self.assertFalse(any(r.get('TargetMode') == 'External' for r in rels))
                    media = [r for r in rels if r.get('Type').endswith(('/media', '/video'))]
                    self.assertEqual(len(media), 2)
                    self.assertEqual(len({r.get('Target') for r in media}), 1)
                    target = posixpath.normpath('ppt/slides/' + media[0].get('Target'))
                    self.assertEqual(archive.read(target), data)
                    root = self.xml(archive, 'ppt/slides/slide1.xml')
                    self.assertIsNotNone(root.find('.//p14:media', NS).get('{'+NS['r']+'}embed'))
                    self.assertEqual(root.find('.//p:cMediaNode', NS).get('vol'), '25000')
                    interactive = root.find(".//p:cTn[@nodeType='interactiveSeq']", NS)
                    self.assertEqual(interactive.find('p:stCondLst/p:cond', NS).get('evt'), 'onClick')
                    self.assertIsNotNone(interactive.find(".//p:cmd[@cmd='togglePause']", NS))

    def test_download_failure_preserves_previous_output(self):
        self.write('#media("https://example.org/clip.mp4", width: 160pt, height: 90pt)')
        self.output.write_bytes(b'previous')
        with patch('typst_pptx.compiler.urlopen', side_effect=URLError('download failed')):
            with self.assertRaisesRegex(RuntimeError, 'Could not download video'):
                self.compile()
        self.assertEqual(self.output.read_bytes(), b'previous')

    def test_webpage_and_empty_download_rejected(self):
        url = 'https://example.org/clip.mp4'
        self.write('#media("' + url + '", width: 160pt, height: 90pt)')
        for content_type, data in [('text/html', b'<html>Not a video</html>'), ('video/mp4', b'')]:
            response = io.BytesIO(data)
            response.headers = Message()
            response.headers['Content-Type'] = content_type
            response.geturl = lambda: url
            with patch('typst_pptx.compiler.urlopen', return_value=response):
                with self.assertRaises(ValueError):
                    self.compile()

    def test_none_does_not_download_video(self):
        self.write('#media("https://example.org/missing.mp4", compatible: "none")')
        with patch('typst_pptx.compiler.urlopen') as download:
            self.compile()
            download.assert_not_called()

    def test_none_is_only_an_image_and_never_reads_missing_video(self):
        self.write('#media("missing.mp4", compatible: "none", thumbnail: path("thumb.png"))')
        self.compile(mode='editable')
        with ZipFile(self.output) as archive:
            self.assertIsNone(self.xml(archive, 'ppt/slides/slide1.xml').find('.//a:videoFile', NS))
            self.assertFalse(any(n.endswith('.mp4') for n in archive.namelist()))

    def test_default_width_and_normal_typst_thumbnail(self):
        self.write('#media("video.mp4", thumbnail: path("thumb.png"))')
        query = subprocess.run(['typst', 'query', str(self.source), '<typst-pptx-media>', '--field', 'value', '--root', str(ROOT)], check=True, capture_output=True, text=True)
        record = json.loads(query.stdout)[0]
        self.assertEqual(record['width'], 360)
        self.assertEqual(record['height'], 180)
        pdf = self.work / 'normal.pdf'
        subprocess.run(['typst', 'compile', str(self.source), str(pdf), '--root', str(ROOT)], check=True)
        with pymupdf.open(pdf) as doc:
            pixel = doc[0].get_pixmap().pixel(100, 100)
            self.assertEqual(pixel[:3], (255, 0, 0))
        self.compile()

    def test_multiple_videos_and_page_locations(self):
        self.write('#media("video.mp4", width: 100pt, height: 60pt)\n#media("video.mp4", width: 100pt, height: 60pt)\n#pagebreak()\n#media("video.mp4", width: 100pt, height: 60pt)')
        self.compile()
        with ZipFile(self.output) as archive:
            for page, expected in [(1, 2), (2, 1)]:
                root = self.xml(archive, f'ppt/slides/slide{page}.xml')
                self.assertEqual(len(root.findall('.//a:videoFile', NS)), expected)
                ids = [e.get('id') for e in root.findall('.//p:cTn', NS)]
                self.assertEqual(len(ids), len(set(ids)))

    def test_media_root_override(self):
        (self.work / 'assets').mkdir()
        shutil.move(self.work / 'video.mp4', self.work / 'assets/video.mp4')
        self.write('#media("video.mp4", width: 100pt, height: 60pt)')
        self.compile(media_root=self.work / 'assets')
        with ZipFile(self.output) as archive:
            self.assertTrue(any(n.endswith('.mp4') for n in archive.namelist()))

    def test_local_package_with_caller_owned_thumbnail(self):
        package_dir = self.work / 'packages/local/pptx-media/0.1.0'
        shutil.copytree(ROOT / 'packages/pptx-media', package_dir)
        self.source.write_text('#import "@local/pptx-media:0.1.0": media\n'
            '#set page(width: 400pt, height: 300pt)\n'
            '#media("video.mp4", thumbnail: path("thumb.png"), width: 100pt, height: 60pt)')
        result = subprocess.run(['typst', 'compile', str(self.source), str(self.work / 'package.pdf'),
            '--package-path', str(self.work / 'packages')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_video_preserves_previous_output(self):
        self.write('#media("missing.mp4", width: 100pt)')
        self.output.write_bytes(b'previous')
        with self.assertRaises(FileNotFoundError):
            self.compile()
        self.assertEqual(self.output.read_bytes(), b'previous')

    def test_bad_typst_preserves_previous_output(self):
        self.write('#invalid_function()')
        self.output.write_bytes(b'previous')
        with self.assertRaises(RuntimeError):
            self.compile()
        self.assertEqual(self.output.read_bytes(), b'previous')

    def test_mixed_page_sizes_rejected(self):
        self.write('First\n#pagebreak()\n#set page(width: 500pt)\nSecond')
        with self.assertRaisesRegex(ValueError, 'same size'):
            self.compile()

    def test_invalid_parameters(self):
        self.write('Hello')
        for kwargs in ({'ppi': 0}, {'ppi': float('nan')}, {'mode': 'bad'}, {'background_format': 'pdf'}, {'vector_format': 'bad'}, {'video_conversion': 'bad'}, {'video_foreground': 'bad'}):
            with self.assertRaises(ValueError):
                self.compile(**kwargs)
        for body in ('#media("v.mp4", compatible: "pdf")', '#media("v.mp4", playback: (muted: 1))', '#media("v.mp4", playback: (volume: 2))'):
            self.write(body)
            with self.assertRaises(RuntimeError):
                self.compile()

    def test_gradient_is_separate_picture_with_editable_text(self):
        self.write('Gradient caption\n#rect(width: 100pt, height: 60pt, fill: gradient.linear(red, blue))')
        with self.assertWarnsRegex(UserWarning, 'shading'):
            self.compile(mode='editable')
        with ZipFile(self.output) as archive:
            root = self.xml(archive, 'ppt/slides/slide1.xml')
            self.assertIn('Gradient caption', ''.join(root.itertext()))
            self.assertEqual(len(root.findall('.//p:pic', NS)), 1)
            pngs = [n for n in archive.namelist() if n.endswith('.png')]
            img = Image.open(io.BytesIO(archive.read(pngs[0])))
            self.assertLessEqual(img.width, 102)
            self.assertGreater(img.width, 90)
            self.assertNotEqual(img.getpixel((10, 10)), img.getpixel((80, 10)))

    def test_inputs_and_font_paths(self):
        self.write('#sys.inputs.at("title")')
        self.compile(mode='editable', inputs=['title=Custom title'], font_path=[self.work])
        with ZipFile(self.output) as archive:
            self.assertIn('Custom title', ''.join(self.xml(archive, 'ppt/slides/slide1.xml').itertext()))

    def test_svg_background_normalizes_exif_against_pdf_orientation(self):
        import base64
        from PIL import ImageChops, ImageOps
        image = Image.new('RGB', (120, 60), 'red')
        image.paste('blue', (60, 0, 120, 60))
        for orientation in (3, 6, 8):
            exif = Image.Exif()
            exif[274] = orientation
            image.save(self.work / f'photo{orientation}.jpg', exif=exif)
        self.write('#image("photo3.jpg", width: 80pt) #image("photo6.jpg", height: 80pt) #image("photo8.jpg", height: 80pt)')
        self.compile()
        with ZipFile(self.output) as archive:
            svg = ET.fromstring(archive.read(next(n for n in archive.namelist() if n.endswith('.svg'))))
            embedded = list(svg.iter('{http://www.w3.org/2000/svg}image'))
            self.assertEqual(len(embedded), 3)
            for orientation, element in zip((3, 6, 8), embedded):
                data = base64.b64decode(element.get('{http://www.w3.org/1999/xlink}href').split(',')[1])
                with Image.open(io.BytesIO(data)) as actual, Image.open(self.work / f'photo{orientation}.jpg') as original:
                    expected = ImageOps.exif_transpose(original)
                    self.assertEqual(actual.size, expected.size)
                    self.assertIsNone(actual.getexif().get(274))
                    self.assertIsNone(ImageChops.difference(actual.convert('RGB'), expected.convert('RGB')).getbbox())


    def test_imported_svg_background_keeps_visible_vector_paths(self):
        (self.work / 'circuit.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 40"><path d="M0 0L80 40" stroke="red"/></svg>')
        self.write('#image("circuit.svg", width: 160pt)')
        self.compile()
        with ZipFile(self.output) as archive:
            svg = archive.read(next(n for n in archive.namelist() if n.endswith('.svg')))
            root = ET.fromstring(svg)
            self.assertNotIn(b'data:image/svg+xml', svg)
            self.assertTrue(any(p.get('d') == 'M0 0L80 40' for p in root.iter('{http://www.w3.org/2000/svg}path')))
            self.assertEqual(len(list(root.iter('{http://www.w3.org/2000/svg}svg'))), 2)


    def test_background_video_keeps_foreground_above_playback(self):
        self.write('#place(top + left, media("video.mp4", thumbnail: path("thumb.png"), width: 160pt, height: 90pt))\n#place(top + left, text(fill: green)[Foreground title])')
        for fmt in ('svg', 'png', 'jpeg'):
            with self.subTest(format=fmt):
                self.compile(background_format=fmt, video_foreground="composite")
                with ZipFile(self.output) as archive:
                    root = self.xml(archive, 'ppt/slides/slide1.xml')
                    pictures = root.findall('p:cSld/p:spTree/p:pic', NS)
                    self.assertEqual(len(pictures), 2)
                    self.assertIsNotNone(pictures[1].find('p:nvPicPr/p:nvPr/a:videoFile', NS))
                    self.assertIsNone(pictures[0].find('p:nvPicPr/p:nvPr/a:videoFile', NS))
                    rid = pictures[0].find('p:blipFill/a:blip', NS).get('{'+NS['r']+'}embed')
                    rels = self.xml(archive, 'ppt/slides/_rels/slide1.xml.rels')
                    target = next(r.get('Target') for r in rels if r.get('Id') == rid)
                    with Image.open(io.BytesIO(archive.read('ppt/'+target.removeprefix('../')))) as foreground:
                        self.assertEqual(foreground.mode, 'RGBA')
                        self.assertEqual(foreground.getchannel('A').getextrema(), (0, 255))
                    if fmt == 'svg':
                        # Verify the embedded movie, not only its still poster:
                        # PowerPoint may draw its video surface above every shape.
                        movie_target = next(r.get('Target') for r in rels if r.get('Type').endswith('/video'))
                        movie = self.work / 'embedded.mp4'
                        movie.write_bytes(archive.read('ppt/'+movie_target.removeprefix('../')))
                        decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(movie),
                            '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'],
                            capture_output=True, check=True).stdout
                        with Image.open(io.BytesIO(decoded)) as frame:
                            self.assertGreater(sum(g > 25 and r < 80 for r, g, b in frame.convert('RGB').getdata()), 5)



    def test_foreground_policy_requires_confirmation_and_preserves_output(self):
        self.write('#place(top + left, media("video.mp4", thumbnail: path("thumb.png"), width: 160pt, height: 90pt))\n#place(top + left, text(fill: green)[Foreground title])')
        self.output.write_bytes(b'previous output')
        for kwargs in ({}, {'video_foreground': 'error'}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(RuntimeError, 'foreground'):
                self.compile(**kwargs)
            self.assertEqual(self.output.read_bytes(), b'previous output')
        calls = []
        def decline(page, source):
            calls.append((page, source))
            return False
        with self.assertWarnsRegex(UserWarning, 'Original video preserved'):
            self.compile(confirm_video_foreground=decline)
        self.assertEqual(calls, [(1, 'video.mp4')])
        with ZipFile(self.output) as archive:
            movie = next(n for n in archive.namelist() if n.endswith('.mp4'))
            self.assertEqual(archive.read(movie), (self.work/'video.mp4').read_bytes())
        with self.assertWarnsRegex(UserWarning, 'Original video preserved'):
            self.compile(video_foreground='preserve', confirm_video_foreground=lambda *a: self.fail('must not prompt'))
        with patch('typst_pptx.video.VideoProcessor.composite_foreground', wraps=None) as compose:
            self.write('#media("video.mp4", thumbnail: path("thumb.png"), width: 160pt, height: 90pt)')
            self.compile(confirm_video_foreground=lambda *a: self.fail('no overlap must not prompt'))
            compose.assert_not_called()

    def test_foreground_approval_is_explicit(self):
        self.write('#place(top + left, media("video.mp4", thumbnail: path("thumb.png"), width: 160pt, height: 90pt))\n#place(top + left, text(fill: green)[Foreground title])')
        calls = []
        def approve(page, source):
            calls.append((page, source))
            return True
        self.compile(confirm_video_foreground=approve)
        self.assertEqual(calls, [(1, 'video.mp4')])
        with ZipFile(self.output) as archive:
            movie = next(n for n in archive.namelist() if n.endswith('.mp4'))
            self.assertNotEqual(archive.read(movie), (self.work/'video.mp4').read_bytes())


if __name__ == '__main__':
    unittest.main()
