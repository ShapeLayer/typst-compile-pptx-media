import io
import json
from pathlib import Path
import posixpath
import shutil
import subprocess
import tempfile
import unittest
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
                    if fmt == 'svg':
                        self.assertEqual(sum(n.endswith('.svg') for n in archive.namelist()), 2)
                    if fmt == 'jpeg':
                        images = [n for n in archive.namelist() if n.endswith('.jpeg')]
                        self.assertEqual(Image.open(io.BytesIO(archive.read(images[0]))).format, 'JPEG')

    def test_editable_text_paths_images_and_order(self):
        self.write('Editable text 한글\n#rect(width: 80pt, height: 30pt, fill: blue)\n#image("thumb.png", width: 80pt)')
        self.compile(mode='editable')
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
                    self.assertEqual(root.find('.//p:stCondLst/p:cond', NS).get('delay'), '0')
                    self.assertIsNotNone(root.find('.//p14:media', NS).get('{'+NS['r']+'}embed'))
                    video = [n for n in archive.namelist() if n.endswith('.mp4')]
                    self.assertEqual(len(video), 1)
                    self.assertEqual(archive.read(video[0]), (self.work / 'video.mp4').read_bytes())

    def test_remote_video_link_and_click_volume(self):
        self.write('#media("https://example.org/clip.mp4?a=1&b=2", width: 160pt, height: 90pt, playback: (volume: 0.25))')
        self.compile()
        with ZipFile(self.output) as archive:
            self.assert_package(archive)
            rels = self.xml(archive, 'ppt/slides/_rels/slide1.xml.rels')
            remote = [r for r in rels if r.get('TargetMode') == 'External']
            self.assertEqual(len(remote), 2)
            self.assertTrue(all(r.get('Target') == 'https://example.org/clip.mp4?a=1&b=2' for r in remote))
            root = self.xml(archive, 'ppt/slides/slide1.xml')
            self.assertEqual(root.find('.//p:cMediaNode', NS).get('vol'), '25000')
            self.assertEqual(root.find('.//p:stCondLst/p:cond', NS).get('evt'), 'onClick')

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
        for kwargs in ({'ppi': 0}, {'ppi': float('nan')}, {'mode': 'bad'}, {'background_format': 'pdf'}):
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


if __name__ == '__main__':
    unittest.main()
