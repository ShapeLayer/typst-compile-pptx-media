import contextlib
import io
import unittest
from unittest.mock import patch
from typst_pptx.cli import confirm_video_foreground, main


class ForegroundPromptTests(unittest.TestCase):
    def test_yes_and_no_are_explicit_choices(self):
        for answer, expected in [('yes', True), ('예', True), ('n', False), ('', False)]:
            with self.subTest(answer=answer), patch('sys.stdin.isatty', return_value=True), patch('builtins.input', return_value=answer), contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertIs(confirm_video_foreground(8, 'video.mp4'), expected)
                self.assertIn('8페이지', output.getvalue())
                self.assertIn('다시 인코딩', output.getvalue())

    def test_noninteractive_does_not_assume_consent(self):
        with patch('sys.stdin.isatty', return_value=False), patch('builtins.input') as ask, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, '--video-foreground composite'):
                confirm_video_foreground(9, 'video.mp4')
            ask.assert_not_called()

    def test_eof_cancels_instead_of_accepting(self):
        with patch('sys.stdin.isatty', return_value=True), patch('builtins.input', side_effect=EOFError), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, '중단'):
                confirm_video_foreground(8, 'video.mp4')

    def test_cli_forwards_policy_and_callback(self):
        with patch('sys.argv', ['typst-pptx', 'in.typ', 'out.pptx', '--video-foreground', 'preserve']), patch('typst_pptx.cli.compile_pptx') as compile:
            self.assertEqual(main(), 0)
            self.assertEqual(compile.call_args.kwargs['video_foreground'], 'preserve')
            self.assertIs(compile.call_args.kwargs['confirm_video_foreground'], confirm_video_foreground)
