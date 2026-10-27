import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from typst_pptx.cli import confirm_video_conversion
from typst_pptx.video import VideoInspection, VideoProcessor, inspect_video, display_aspect_ratio

FIXTURE = Path(__file__).parent / 'fixtures/video.mp4'


class CodecInspectionTests(unittest.TestCase):
    def info(self, video='h264', audio='aac', pixels='yuv420p', extension='mp4'):
        streams = [{'index': 0, 'codec_type': 'video', 'codec_name': video, 'pix_fmt': pixels, 'width': 160, 'height': 90}]
        if audio:
            streams.append({'index': 1, 'codec_type': 'audio', 'codec_name': audio})
        response = subprocess.CompletedProcess([], 0, json.dumps({'streams': streams,
            'format': {'format_name': 'mov,mp4,m4a,3gp,3g2,mj2'}}), '')
        with patch('typst_pptx.video.subprocess.run', return_value=response):
            return inspect_video('video.bin', extension)

    def test_profiles(self):
        self.assertTrue(self.info().compatible)
        self.assertTrue(self.info(audio=None).compatible)
        self.assertTrue(self.info(extension='mov').compatible)
        for change in ({'video': 'hevc'}, {'video': 'av1'}, {'audio': 'opus'},
                       {'pixels': 'yuv420p10le'}, {'extension': 'avi'}):
            with self.subTest(change=change):
                self.assertFalse(self.info(**change).compatible)

    def test_display_aspect_includes_pixels_and_rotation(self):
        self.assertAlmostEqual(display_aspect_ratio({'width': 1920, 'height': 1080}), 16/9)
        self.assertAlmostEqual(display_aspect_ratio({'width': 1920, 'height': 1080,
            'side_data_list': [{'rotation': -90}]}), 9/16)
        self.assertAlmostEqual(display_aspect_ratio({'width': 720, 'height': 576,
            'sample_aspect_ratio': '16:15'}), 4/3)
        self.assertAlmostEqual(display_aspect_ratio({'width': 720, 'height': 576,
            'sample_aspect_ratio': '16:15', 'tags': {'rotate': '90'}}), 3/4)
        with self.assertRaises(RuntimeError):
            display_aspect_ratio({'width': 0, 'height': 1080})

    def test_invalid_media_is_not_treated_as_compatible(self):
        for raw in ('not JSON', '{}', '{"streams": []}'):
            response = subprocess.CompletedProcess([], 0, raw, '')
            with patch('typst_pptx.video.subprocess.run', return_value=response):
                with self.assertRaisesRegex(RuntimeError, 'playable video'):
                    inspect_video('video.bin', 'mp4')

    def test_missing_probe_is_actionable(self):
        with patch('typst_pptx.video.subprocess.run', side_effect=FileNotFoundError):
            with self.assertRaisesRegex(RuntimeError, 'Install FFmpeg'):
                inspect_video('video.bin', 'mp4')


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.info = VideoInspection(0, 'hevc', ('aac',), 'yuv420p', ('H.264 required',))

    def test_explicit_yes_only(self):
        for reply, expected in [('y', True), ('YES', True), ('예', True), ('', False), ('n', False)]:
            with self.subTest(reply=reply), patch('sys.stdin.isatty', return_value=True), \
                 patch('builtins.input', return_value=reply), patch('sys.stderr', new_callable=io.StringIO) as output:
                self.assertEqual(confirm_video_conversion('movie.mp4', self.info), expected)
                self.assertIn('hevc', output.getvalue())
                self.assertIn('[y/N]', output.getvalue())

    def test_no_interactive_input_means_no_conversion(self):
        with patch('sys.stdin.isatty', return_value=False), patch('builtins.input') as prompt, \
             patch('sys.stderr', new_callable=io.StringIO):
            with self.assertRaisesRegex(RuntimeError, '--video-conversion convert'):
                confirm_video_conversion('movie.mp4', self.info)
            prompt.assert_not_called()

    def test_closed_input_means_no_conversion(self):
        with patch('sys.stdin.isatty', return_value=True), patch('builtins.input', side_effect=EOFError), \
             patch('sys.stderr', new_callable=io.StringIO):
            self.assertFalse(confirm_video_conversion('movie.mp4', self.info))


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg tools required')
class VideoProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.video = self.work / 'incompatible.avi'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(FIXTURE),
            '-c:v', 'mpeg4', '-c:a', 'pcm_s16le', str(self.video)], check=True)
        self.data = self.video.read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def test_compatible_media_not_reencoded_and_never_prompts(self):
        data = FIXTURE.read_bytes()
        def no_prompt(*args):
            self.fail('Compatible video must not request conversion')
        result = VideoProcessor(self.work, confirm=no_prompt).prepare(data, 'mp4', 'video.mp4')
        self.assertEqual(result, (data, 'mp4'))

    def test_decline_and_noninteractive_api_never_convert(self):
        for confirm in (None, lambda *args: False):
            with self.subTest(confirm=confirm), patch('typst_pptx.video._invoke', wraps=__import__('typst_pptx.video', fromlist=['_invoke'])._invoke) as run:
                with self.assertRaises(RuntimeError):
                    VideoProcessor(self.work, confirm=confirm).prepare(self.data, 'avi', 'video.avi')
                self.assertFalse(any(call.args[1] == 'FFmpeg' for call in run.call_args_list))
        self.assertEqual(self.video.read_bytes(), self.data)

    def test_approval_converts_verifies_and_caches(self):
        confirmations = []
        def yes(source, inspection):
            confirmations.append((source, inspection))
            return True
        processor = VideoProcessor(self.work, confirm=yes)
        converted, extension = processor.prepare(self.data, 'avi', 'video.avi')
        self.assertEqual(extension, 'mp4')
        self.assertNotEqual(converted, self.data)
        path = self.work / 'result.mp4'
        path.write_bytes(converted)
        self.assertTrue(inspect_video(path, extension).compatible)
        self.assertEqual(len(confirmations), 1)
        self.assertEqual(confirmations[0][1].video_codec, 'mpeg4')
        self.assertEqual(processor.prepare(self.data, 'avi', 'video.avi'), (converted, extension))
        self.assertEqual(len(confirmations), 1)
        self.assertEqual(self.video.read_bytes(), self.data)

    def test_explicit_policies(self):
        with self.assertRaisesRegex(RuntimeError, '--video-conversion convert'):
            VideoProcessor(self.work, policy='error').prepare(self.data, 'avi', 'video.avi')
        data, ext = VideoProcessor(self.work, policy='convert').prepare(self.data, 'avi', 'video.avi')
        self.assertEqual(ext, 'mp4')
        self.assertNotEqual(data, self.data)

    def test_converter_missing_and_failure_never_fall_back_to_bad_media(self):
        with self.assertRaisesRegex(RuntimeError, 'FFmpeg is required'):
            VideoProcessor(self.work, policy='convert', ffmpeg=str(self.work / 'missing')).prepare(self.data, 'avi', 'v.avi')
        with patch('typst_pptx.video.inspect_video', return_value=VideoInspection(0, 'hevc', (), 'yuv420p', ('H.264 required',))), \
             patch('typst_pptx.video._invoke', side_effect=RuntimeError('encoder failed')):
            with self.assertRaisesRegex(RuntimeError, 'encoder failed'):
                VideoProcessor(self.work, policy='convert').prepare(self.data, 'avi', 'v.avi')
