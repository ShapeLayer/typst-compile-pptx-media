import unittest
from xml.etree import ElementTree as ET
from typst_pptx.layers import split_media_layers


class MediaLayerTests(unittest.TestCase):
    def test_foreground_keeps_clip_and_resources_after_video(self):
        svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><rect id="background" width="400" height="300" fill="white"/><g transform="translate(10 20)" clip-path="url(#clip)"><image href="poster.png" width="160" height="90"/><path id="title" d="M0 0L10 10"/></g><defs><clipPath id="clip"><rect width="160" height="90"/></clipPath></defs></svg>'''
        video = {'box': (10, 20, 160, 90)}
        layers = split_media_layers(svg, [video])
        self.assertEqual(len(layers), 2)
        before, (actual, poster, foreground) = layers[0]
        after, empty = layers[1]
        self.assertIs(actual, video)
        self.assertIsNone(empty)
        self.assertNotIn(b'id="title"', before)
        self.assertNotIn(b'<ns0:image', after)
        self.assertIn(b'id="title"', after)
        self.assertIn(b'id="title"', foreground)
        self.assertIn(b'translate(10 20)', after)
        self.assertIn(b'id="clip"', after)
        self.assertIn(b'poster.png', poster)
        self.assertNotIn(b'id="title"', poster)

    def test_two_videos_keep_their_original_paint_order(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><image width="100" height="50"/><rect id="middle"/><g transform="translate(0 70)"><image width="100" height="50"/></g><rect id="front"/></svg>'
        first, second = {'box': (0, 0, 100, 50)}, {'box': (0, 70, 100, 50)}
        layers = split_media_layers(svg, [second, first])
        self.assertIsNone(layers[0][0])
        self.assertIs(layers[0][1][0], first)
        self.assertIn(b'id="middle"', layers[1][0])
        self.assertIs(layers[1][1][0], second)
        self.assertIn(b'id="front"', layers[2][0])

    def test_unmatched_thumbnail_fails_instead_of_covering_content(self):
        with self.assertRaisesRegex(ValueError, 'Cannot locate'):
            split_media_layers(b'<svg xmlns="http://www.w3.org/2000/svg"/>', [{'box': (0, 0, 100, 50)}])
