import argparse
import sys
from .compiler import compile_pptx


def main():
    parser = argparse.ArgumentParser(description="Compile Typst pages to PowerPoint")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--mode", choices=["background", "editable"], default="background")
    parser.add_argument("--background-format", choices=["png", "jpeg", "svg"], default="svg")
    parser.add_argument("--vector-format", choices=["svg", "native"], default="svg",
                        help="Vector paths in editable mode (default: svg)")
    parser.add_argument("--ppi", type=float, default=192)
    parser.add_argument("--root")
    parser.add_argument("--media-root")
    parser.add_argument("--typst", default="typst")
    parser.add_argument("--input", action="append", default=[], dest="inputs", metavar="KEY=VALUE")
    parser.add_argument("--font-path", action="append", default=[])
    args = vars(parser.parse_args())
    try:
        compile_pptx(**args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"typst-pptx: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
