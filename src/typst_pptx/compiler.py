"""Compile with the installed Typst CLI, then convert its paged output."""
import io
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import warnings
from urllib.parse import urlsplit

import pymupdf as fitz
from PIL import Image
from .ooxml import Deck


def _run(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Typst executable not found: {command[0]}") from exc
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Command failed: {command[0]}")
    return result.stdout


def _box(rect):
    r = fitz.Rect(rect)
    return r.x0, r.y0, r.width, r.height


def _png(page, ppi=144, clip=None):
    return page.get_pixmap(matrix=fitz.Matrix(ppi / 72, ppi / 72), clip=clip, alpha=False).tobytes('png')


def _playback(value):
    if not isinstance(value, dict) or set(value) - {'autoplay', 'loop', 'muted', 'volume'}:
        raise ValueError('Unsupported media playback dictionary')
    for key, item in value.items():
        if key == 'volume':
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not 0 <= item <= 1:
                raise ValueError('media volume must be a number between 0 and 1')
        elif not isinstance(item, bool):
            raise ValueError(f'media {key} must be boolean')
    return value


def _media(records, document, media_root):
    result = {}
    for record in records:
        if record.get('kind') != 'typst-pptx-media' or record.get('version') != 1:
            raise ValueError('Unsupported media metadata version')
        page_number = record['page']
        if type(page_number) is not int or not 1 <= page_number <= len(document):
            raise ValueError('Media page is outside the document')
        box = tuple(float(record[k]) for k in ('x', 'y', 'width', 'height'))
        if not all(math.isfinite(v) for v in box) or box[2] <= 0 or box[3] <= 0:
            raise ValueError('Invalid media rectangle')
        rect = fitz.Rect(box[0], box[1], box[0] + box[2], box[1] + box[3])
        page = document[page_number - 1]
        if not page.rect.contains(rect):
            raise ValueError('Media must fit completely on one page')
        source = record['source']
        parsed = urlsplit(source)
        data = None
        extension = Path(parsed.path).suffix.lower().lstrip('.') or 'mp4'
        if parsed.scheme in ('http', 'https'):
            if not parsed.netloc:
                raise ValueError(f'Invalid video URL: {source}')
        else:
            # A drive letter on Windows is not a URL scheme.
            if parsed.scheme and not (len(parsed.scheme) == 1 and source[1:3] in (':/', ':\\')):
                raise ValueError('Video URLs must use http or https')
            path = Path(source)
            if not path.is_absolute():
                path = media_root / path
            data = path.read_bytes()
        if extension not in ('mp4', 'm4v', 'mov', 'avi', 'wmv', 'webm', 'mpeg', 'mpg'):
            raise ValueError(f'Unsupported video extension: {extension}')
        entry = dict(source=source, data=data, extension=extension, box=box,
                     thumbnail=_png(page, clip=rect), playback=_playback(record.get('playback', {})))
        result.setdefault(page_number - 1, []).append(entry)
    return result


def _editable(slide, page):
    """Preserve PDF paint order and expose text, images and vector paths."""
    events = []
    for span in page.get_texttrace():
        if span['type'] == 3:  # PDF invisible text
            continue
        events.append((span['seqno'], 'text', span))
    for drawing in page.get_drawings():
        events.append((drawing['seqno'], 'path', drawing))
    paint_log = page.get_bboxlog()
    image_sequences = [(i, fitz.Rect(b)) for i, (kind, b) in enumerate(paint_log) if kind == 'fill-image']
    shading_sequences = [i for i, (kind, _) in enumerate(paint_log) if kind == 'fill-shade']
    has_shading = bool(shading_sequences)
    for block in page.get_text('dict')['blocks']:
        if block['type'] != 1:
            continue
        bbox = fitz.Rect(block['bbox'])
        match = next(((i, r) for i, r in image_sequences if all(abs(a-b) < .1 for a, b in zip(r, bbox))), None)
        if match:
            seq = match[0]
            image_sequences.remove(match)
        elif shading_sequences:
            # MuPDF exposes a shading as an isolated raster image block.
            seq = shading_sequences.pop(0)
        else:
            seq = len(paint_log)
        events.append((seq, 'image', block))
    if shading_sequences:
        raise ValueError(f'Page {page.number + 1}: cannot isolate PDF shading; use background mode')
    if has_shading:
        warnings.warn(f'Page {page.number + 1}: shading exported as separate image objects', stacklevel=2)
    for _, kind, item in sorted(events, key=lambda e: e[0]):
        if kind == 'path':
            slide.drawing(item)
        elif kind == 'image':
            # Extracted images remain independently movable/replacable.
            data = item['image']
            if item.get('mask'):
                image = Image.open(io.BytesIO(data)).convert('RGBA')
                image.putalpha(Image.open(io.BytesIO(item['mask'])).convert('L'))
                output = io.BytesIO()
                image.save(output, 'PNG')
                data = output.getvalue()
                extension = 'png'
            else:
                extension = item['ext']
            slide.picture(data, extension, _box(item['bbox']))
        else:
            # One textbox per PDF text run; it remains editable in PowerPoint.
            chars = item['chars']
            if not chars:
                continue
            text = ''.join(chr(c[0]) for c in chars)
            x, y, w, h = _box(item['bbox'])
            size = item['size']
            font = item['font'].split('+')[-1]
            for suffix in ('-BoldItalic', '-Bold', '-Italic', '-Regular', '-Roman'):
                font = font.removesuffix(suffix)
            # DrawingML's text top uses the font ascender, unlike trace bboxes.
            baseline = chars[0][2][1]
            rotation = math.degrees(math.atan2(item['dir'][1], item['dir'][0]))
            if abs(rotation) < .01:
                y = baseline - size * item['ascender']
            slide.text(text, (x, y, w + size * .2, max(h, size * 1.3)), font,
                       size, item['color'], item['flags'], rotation, item['opacity'])


def compile_pptx(input, output, *, mode='background', background_format='png', ppi=144,
                 root=None, media_root=None, typst='typst', inputs=(), font_path=()):
    """Export all Typst pages. Local videos embed; HTTP(S) videos remain linked.

    ``root``, ``inputs`` and ``font_path`` are passed consistently to both
    rendering and metadata evaluation. Output is atomically replaced on success.
    """
    if mode not in ('background', 'editable'):
        raise ValueError('mode must be background or editable')
    if background_format not in ('png', 'jpeg', 'svg'):
        raise ValueError('background_format must be png, jpeg, or svg')
    if not math.isfinite(ppi) or ppi <= 0:
        raise ValueError('ppi must be positive and finite')
    source, destination = Path(input).resolve(), Path(output).resolve()
    if source == destination:
        raise ValueError('Input and output paths must differ')
    project_root = Path(root).resolve() if root else source.parent
    video_root = Path(media_root).resolve() if media_root else source.parent
    common = ['--root', str(project_root)]
    for value in inputs:
        common += ['--input', value]
    for value in font_path:
        common += ['--font-path', str(value)]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='typst-pptx-') as tmp:
        work = Path(tmp)
        pdf = work / 'document.pdf'
        _run([typst, 'compile', str(source), str(pdf), *common])
        records = json.loads(_run([typst, 'query', str(source), '<typst-pptx-media>', '--field', 'value', *common]))
        with fitz.open(pdf) as document:
            if not len(document):
                raise ValueError('The document contains no pages')
            first = document[0].rect
            if any(abs(p.rect.width-first.width) > .01 or abs(p.rect.height-first.height) > .01 for p in document):
                raise ValueError('PowerPoint requires every page to have the same size')
            videos = _media(records, document, video_root)
            deck = Deck(first.width, first.height)
            for i, page in enumerate(document):
                slide = deck.slide()
                if mode == 'editable':
                    _editable(slide, page)
                else:
                    svg = None
                    if background_format in ('png', 'svg'):
                        image_path = work / f'page-{i+1}.png'
                        _run([typst, 'compile', str(source), str(image_path), '--format', 'png', '--pages', str(i+1), '--ppi', str(ppi), *common])
                        data = image_path.read_bytes()
                        extension = 'png'
                        if background_format == 'svg':
                            svg_path = work / f'page-{i+1}.svg'
                            _run([typst, 'compile', str(source), str(svg_path), '--format', 'svg', '--pages', str(i+1), *common])
                            svg = svg_path.read_bytes()
                    else:
                        png_path = work / f'page-{i+1}.png'
                        _run([typst, 'compile', str(source), str(png_path), '--format', 'png', '--pages', str(i+1), '--ppi', str(ppi), *common])
                        image = Image.open(png_path).convert('RGB')
                        stream = io.BytesIO()
                        image.save(stream, 'JPEG', quality=95)
                        data, extension = stream.getvalue(), 'jpeg'
                    slide.picture(data, extension, (0, 0, first.width, first.height), background=True, svg=svg)
                for video in videos.get(i, []):
                    slide.video(**video)
            # Same-directory staging preserves an existing output on failure.
            fd, staged = tempfile.mkstemp(prefix='.typst-pptx-', suffix='.pptx', dir=destination.parent)
            os.close(fd)
            try:
                deck.save(staged)
                os.replace(staged, destination)
            finally:
                if os.path.exists(staged):
                    os.unlink(staged)
    return destination
