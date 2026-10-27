import argparse
import sys
from .compiler import compile_pptx


def confirm_video_conversion(source, inspection):
    print(f"영상 {source!r}: {inspection.description}", file=sys.stderr)
    print("PowerPoint 공통 호환 프로필에 맞지 않습니다:", file=sys.stderr)
    for reason in inspection.reasons:
        print(f"  - {reason}", file=sys.stderr)
    if not sys.stdin.isatty():
        raise RuntimeError('대화형 입력이 필요합니다. 변환하려면 --video-conversion convert, 중단하려면 --video-conversion error를 지정하세요.')
    print("H.264/AAC MP4로 변환하여 포함할까요? 이 과정에서 원본 파일은 수정되지 않습니다. [y/N] ",
          file=sys.stderr, end='', flush=True)
    try:
        return input().strip().lower() in ('y', 'yes', '예')
    except EOFError:
        return False


def confirm_video_foreground(page, source):
    print(f"{page}페이지 영상 {source!r}: 영상 위에 겹치는 제목·머리말 등의 요소가 있습니다.", file=sys.stderr)
    print("PowerPoint에서 재생 중 가려질 수 있습니다.", file=sys.stderr)
    if not sys.stdin.isatty():
        raise RuntimeError('대화형 입력이 필요합니다. 합성하려면 --video-foreground composite, 원본 영상을 유지하려면 --video-foreground preserve, 중단하려면 --video-foreground error를 지정하세요.')
    print("겹치는 요소를 내장 영상에 합성할까요? H.264로 다시 인코딩하며 원본 파일은 수정하지 않습니다. 아니오를 선택하면 합성 없이 계속합니다. [y/N] ",
          file=sys.stderr, end='', flush=True)
    try:
        return input().strip().lower() in ('y', 'yes', '예')
    except EOFError:
        raise RuntimeError('입력이 종료되어 컴파일을 중단합니다. --video-foreground composite 또는 preserve를 지정하세요.')


def main():
    parser = argparse.ArgumentParser(description="Compile Typst pages to PowerPoint")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--mode", choices=["background", "editable"], default="background")
    parser.add_argument("--background-format", choices=["png", "jpeg", "svg"], default="svg")
    parser.add_argument("--vector-format", choices=["svg", "native"], default="svg",
                        help="Vector paths in editable mode (default: svg)")
    parser.add_argument("--ppi", type=float, default=192)
    parser.add_argument("--video-conversion", choices=["ask", "convert", "error"], default="ask",
                        help="Incompatible video handling (default: ask before conversion)")
    parser.add_argument("--video-foreground", choices=["ask", "composite", "preserve", "error"], default="ask",
                        help="Overlapping foreground in background mode: ask, composite into video, preserve original, or error (default: ask)")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--root")
    parser.add_argument("--media-root")
    parser.add_argument("--typst", default="typst")
    parser.add_argument("--input", action="append", default=[], dest="inputs", metavar="KEY=VALUE")
    parser.add_argument("--font-path", action="append", default=[])
    args = vars(parser.parse_args())
    try:
        compile_pptx(**args, confirm_video_conversion=confirm_video_conversion,
                     confirm_video_foreground=confirm_video_foreground)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"typst-pptx: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
