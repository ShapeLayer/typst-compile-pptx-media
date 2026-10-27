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
