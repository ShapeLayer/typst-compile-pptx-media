"""PowerPoint media extension and behavior requirements (not just XML validity)."""
import io
import unittest
from PIL import Image
from typst_pptx.ooxml import Deck, NS


class PowerPointMediaTests(unittest.TestCase):
    def test_native_extension_and_per_shape_commands(self):
        deck = Deck(400, 300)
        slide = deck.slide()
        thumbnail = io.BytesIO()
        Image.new('RGB', (16, 9), 'blue').save(thumbnail, 'PNG')
        for autoplay in [False, True, True]:
            slide.video(b'video', 'mp4', 'video.mp4', thumbnail.getvalue(),
                        (20, 20, 160, 90), dict(autoplay=autoplay, loop=True, muted=True))
        root = slide.root
        pictures = root.findall('.//p:pic', NS)
        shape_ids = {p.find('p:nvPicPr/p:cNvPr', NS).get('id') for p in pictures}
        for pic in pictures:
            # The extension URI is a fixed Microsoft identifier. An arbitrary
            # URI passes generic schema checks but Office ignores its media.
            ext = pic.find('p:nvPicPr/p:nvPr/p:extLst/p:ext', NS)
            self.assertEqual(ext.get('uri'), '{DAA4B4D4-6D71-4841-9C94-3DE7FCFB9230}')
            self.assertIsNotNone(ext.find('p14:media', NS).get('{'+NS['r']+'}embed'))
        ids = [n.get('id') for n in root.findall('.//p:cTn', NS)]
        self.assertEqual(len(ids), len(set(ids)))
        controllers = root.findall('.//p:cMediaNode', NS)
        self.assertEqual(len(controllers), 3)
        for media in controllers:
            self.assertEqual(media.get('vol'), '0')
            self.assertIsNone(media.get('numSld'))
            self.assertIsNone(media.get('showWhenStopped'))
            ctn = media.find('p:cTn', NS)
            self.assertEqual(ctn.get('repeatCount'), 'indefinite')
            self.assertEqual(ctn.find('p:stCondLst/p:cond', NS).get('delay'), 'indefinite')
        triggers = root.findall(".//p:cTn[@nodeType='interactiveSeq']", NS)
        self.assertEqual(len(triggers), 3)
        for trigger in triggers:
            self.assertEqual(trigger.get('evtFilter'), 'cancelBubble')
            shape_id = trigger.find('p:stCondLst/p:cond/p:tgtEl/p:spTgt', NS).get('spid')
            command = trigger.find(".//p:cmd[@cmd='togglePause']", NS)
            self.assertEqual(command.find('p:cBhvr/p:tgtEl/p:spTgt', NS).get('spid'), shape_id)
        mains = root.findall(".//p:cTn[@nodeType='mainSeq']", NS)
        self.assertEqual(len(mains), 1)
        self.assertEqual(len(mains[0].findall(".//p:cmd[@cmd='playFrom(0.0)']", NS)), 3)
        self.assertEqual(len(mains[0].findall(".//p:cTn[@nodeType='afterEffect']", NS)), 2)
        self.assertEqual(len(mains[0].findall(".//p:cTn[@nodeType='clickEffect']", NS)), 1)
        for target in root.findall('.//p:spTgt', NS):
            self.assertIn(target.get('spid'), shape_ids)
