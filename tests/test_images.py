import io
import unittest
from xml.etree import ElementTree as ET

from PIL import Image
from typst_pptx.images import image_placement


class ImagePlacementTests(unittest.TestCase):
    def fixture(self, exif_orientation=None):
        image = Image.new('RGB', (80, 160), 'red')
        image.paste('blue', (0, 80, 80, 160))
        stream = io.BytesIO()
        exif = Image.Exif()
        if exif_orientation is not None:
            exif[274] = exif_orientation
        image.save(stream, 'JPEG', exif=exif)
        return dict(image=stream.getvalue(), ext='jpeg', bbox=(10, 20, 70, 140),
                    transform=(60, 0, 0, 120, 10, 20))

    def test_exif_cannot_rotate_the_pdf_image_twice(self):
        result = image_placement(self.fixture(6))
        with Image.open(io.BytesIO(result['data'])) as image:
            self.assertEqual(image.size, (80, 160))
            self.assertIsNone(image.getexif().get(274))
            self.assertGreater(image.getpixel((10, 10))[0], 200)
        self.assertEqual(result['box'], (10, 20, 60, 120))
        self.assertEqual(result['rotation'], 0)

    def test_sheared_image_keeps_affine_transform_and_transparent_fallback(self):
        block = self.fixture()
        block.update(transform=(60, 0, 30, 120, 10, 20), bbox=(10, 20, 100, 140))
        result = image_placement(block)
        root = ET.fromstring(result['svg'])
        image = root.find('{http://www.w3.org/2000/svg}image')
        self.assertEqual(image.get('transform'), 'matrix(60 0 30 120 10 20)')
        with Image.open(io.BytesIO(result['data'])) as fallback:
            self.assertEqual(fallback.getchannel('A').getextrema(), (0, 255))

    def test_mask_survives_rotation(self):
        block = self.fixture()
        mask = io.BytesIO()
        Image.new('L', (80, 160), 128).save(mask, 'PNG')
        block.update(mask=mask.getvalue(), transform=(0, 60, -120, 0, 130, 20), bbox=(10, 20, 130, 80))
        result = image_placement(block)
        self.assertEqual(result['rotation'], 90)
        with Image.open(io.BytesIO(result['data'])) as image:
            self.assertEqual(image.getchannel('A').getextrema(), (128, 128))

    def test_svg_bakes_all_exif_orientations_without_changing_geometry(self):
        import base64
        from PIL import ImageOps, ImageChops
        from typst_pptx.images import normalize_svg_images
        for orientation in range(2, 9):
            with self.subTest(orientation=orientation):
                raw = self.fixture(orientation)['image']
                href = 'data:image/jpeg;base64,' + base64.b64encode(raw).decode()
                svg = f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><image xlink:href="{href}" width="60" height="120" transform="translate(10 20)"/></svg>'.encode()
                root = ET.fromstring(normalize_svg_images(svg))
                element = root[0]
                self.assertEqual(element.get('width'), '60')
                self.assertEqual(element.get('height'), '120')
                self.assertEqual(element.get('transform'), 'translate(10 20)')
                data = base64.b64decode(element.get('{http://www.w3.org/1999/xlink}href').split(',')[1])
                with Image.open(io.BytesIO(raw)) as original, Image.open(io.BytesIO(data)) as actual:
                    expected = ImageOps.exif_transpose(original)
                    self.assertEqual(actual.size, expected.size)
                    self.assertIsNone(actual.getexif().get(274))
                    self.assertIsNone(ImageChops.difference(actual.convert('RGB'), expected.convert('RGB')).getbbox())

    def test_svg_without_oriented_images_is_unchanged(self):
        from typst_pptx.images import normalize_svg_images
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L20 20"/></svg>'
        self.assertEqual(normalize_svg_images(svg), svg)

    def test_embedded_svg_keeps_vectors_viewport_and_unique_references(self):
        import base64
        from typst_pptx.images import normalize_svg_images
        nested = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 20"><defs><linearGradient id="g"><stop stop-color="red"/></linearGradient></defs><path id="p" d="M0 0L40 20" stroke="url(#g)"/><use href="#p"/></svg>'
        href = 'data:image/svg+xml;base64,' + base64.b64encode(nested).decode()
        svg = f'<svg xmlns="http://www.w3.org/2000/svg"><path id="g"/><image href="{href}" width="80" height="40" transform="translate(5 10)"/><image href="{href}" width="40" height="20"/></svg>'.encode()
        root = ET.fromstring(normalize_svg_images(svg))
        ns = '{http://www.w3.org/2000/svg}'
        self.assertEqual(len(list(root.iter(ns+'image'))), 0)
        viewports = list(root.iter(ns+'svg'))[1:]
        self.assertEqual(len(viewports), 2)
        self.assertEqual(viewports[0].get('width'), '80')
        self.assertEqual(viewports[0].get('fill'), 'black')
        self.assertEqual(viewports[0].get('stroke'), 'none')
        self.assertEqual(viewports[0].get('viewBox'), '0 0 40 20')
        self.assertEqual(root[1].get('transform'), 'translate(5 10)')
        ids = [e.get('id') for e in root.iter() if e.get('id')]
        self.assertEqual(len(ids), len(set(ids)))
        for viewport in viewports:
            gradient = viewport.find('.//'+ns+'linearGradient').get('id')
            path = viewport.find(ns+'path')
            self.assertEqual(path.get('stroke'), f'url(#{gradient})')
            self.assertEqual(viewport.find(ns+'use').get('href'), '#'+path.get('id'))
