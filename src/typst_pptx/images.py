"""Translate PDF image placement without stretching rotated image pixels."""
import base64
import io
import math
import re
from xml.etree import ElementTree as ET

import pymupdf as fitz
from PIL import Image


def image_placement(block, ppi=192):
    data, extension = block['image'], block['ext']
    with Image.open(io.BytesIO(data)) as original:
        # PDF matrices describe encoded pixel coordinates. Letting Office apply
        # EXIF orientation again would rotate them a second time.
        if block.get('mask') or original.getexif().get(274, 1) != 1:
            image = original.convert('RGBA')
            if block.get('mask'):
                with Image.open(io.BytesIO(block['mask'])) as mask:
                    image.putalpha(mask.convert('L'))
            output = io.BytesIO()
            image.save(output, 'PNG', exif=b'')
            data, extension = output.getvalue(), 'png'
    bbox = fitz.Rect(block['bbox'])
    a, b, c, d, e, f = block.get('transform', (bbox.width, 0, 0, bbox.height, bbox.x0, bbox.y0))
    width, height = math.hypot(a, b), math.hypot(c, d)
    determinant = a*d - b*c
    if width <= 0 or height <= 0 or abs(determinant) < 1e-10:
        raise ValueError('Image has a degenerate placement matrix')
    if abs(a*c + b*d) <= 1e-6 * width * height:
        # DrawingML rotates/flips around the center of the unrotated rectangle.
        cx, cy = e + (a+c)/2, f + (b+d)/2
        return dict(data=data, extension=extension,
                    box=(cx-width/2, cy-height/2, width, height),
                    rotation=math.degrees(math.atan2(b, a)) % 360,
                    flip_v=determinant < 0)
    # DrawingML has no shear attribute. Preserve the full affine transform in
    # an SVG image, with a transparent raster fallback for older viewers.
    svg = ET.Element('svg', {'xmlns': 'http://www.w3.org/2000/svg',
        'xmlns:xlink': 'http://www.w3.org/1999/xlink',
        'width': str(bbox.width), 'height': str(bbox.height),
        'viewBox': f'{bbox.x0} {bbox.y0} {bbox.width} {bbox.height}'})
    mime = 'image/jpeg' if extension in ('jpg', 'jpeg') else 'image/' + extension
    ET.SubElement(svg, 'image', {'width': '1', 'height': '1', 'preserveAspectRatio': 'none',
        'transform': f'matrix({a} {b} {c} {d} {e} {f})',
        'xlink:href': f'data:{mime};base64,' + base64.b64encode(data).decode('ascii')})
    vector = ET.tostring(svg, encoding='utf-8', xml_declaration=True)
    with fitz.open(stream=vector, filetype='svg') as doc:
        fallback = doc[0].get_pixmap(matrix=fitz.Matrix(ppi/72, ppi/72), alpha=True).tobytes('png')
    return dict(data=fallback, extension='png',
                box=(bbox.x0, bbox.y0, bbox.width, bbox.height), svg=vector)


def normalize_svg_images(svg):
    """Bake EXIF orientation into SVG raster pixels for Office's SVG renderer.

    Typst SVG sizes already describe the oriented image. Office does not
    consistently honor EXIF inside SVG data URLs, unlike Typst/PDF viewers.
    Keep the SVG geometry and remove that viewer-dependent metadata.
    """
    from PIL import ImageOps

    root = ET.fromstring(svg)
    changed = False
    # Office ignores SVG images referenced by SVG data URLs. Include their
    # vector nodes in a nested viewport instead, preserving the image slot.
    svg_ns = '{http://www.w3.org/2000/svg}'
    xlink = '{http://www.w3.org/1999/xlink}href'
    used_ids = {e.get('id') for e in root.iter() if e.get('id')}
    for parent in list(root.iter()):
        for element in list(parent):
            if element.tag != svg_ns + 'image':
                continue
            href = element.get(xlink, element.get('href', ''))
            if not href.startswith('data:image/svg+xml;base64,'):
                continue
            embedded = ET.fromstring(normalize_svg_images(base64.b64decode(href.split(',', 1)[1])))
            # Imported SVGs often reuse short IDs (clip0, gradient0, etc.).
            # Isolate references from the page and other imported images.
            mapping = {}
            for item in embedded.iter():
                old = item.get('id')
                if old and old not in mapping:
                    new = f'pptx-import-{len(used_ids)}'
                    while new in used_ids:
                        new += '-i'
                    used_ids.add(new)
                    mapping[old] = new
            def references(value):
                value = re.sub(r'url\(\s*([\'"]?)#([^\s)\'"]+)\1\s*\)',
                               lambda m: 'url(#' + mapping.get(m[2], m[2]) + ')', value)
                return value
            for item in embedded.iter():
                for key, value in list(item.attrib.items()):
                    if key == 'id':
                        item.set(key, mapping[value])
                    elif key in (xlink, 'href') and value.startswith('#'):
                        item.set(key, '#' + mapping.get(value[1:], value[1:]))
                    else:
                        item.set(key, references(value))
                if item.tag == svg_ns + 'style' and item.text:
                    item.text = references(item.text)
                    for old, new in mapping.items():
                        item.text = re.sub(r'#' + re.escape(old) + r'(?![\w-])', '#' + new, item.text)
            wrapper = ET.Element(svg_ns + 'g', {k: v for k, v in element.attrib.items()
                if k not in (xlink, 'href', 'x', 'y', 'width', 'height', 'preserveAspectRatio')})
            for key in ('x', 'y', 'width', 'height', 'preserveAspectRatio'):
                if key in element.attrib:
                    embedded.set(key, element.get(key))
            # An SVG loaded as an image has its own initial paint defaults.
            # Typst's page root uses fill=none, which must not leak inside.
            embedded.attrib.setdefault('fill', 'black')
            embedded.attrib.setdefault('stroke', 'none')
            embedded.attrib.setdefault('color', 'black')
            wrapper.append(embedded)
            wrapper.tail = element.tail
            index = list(parent).index(element)
            parent.remove(element)
            parent.insert(index, wrapper)
            changed = True
    for element in root.iter():
        if element.tag != '{http://www.w3.org/2000/svg}image':
            continue
        for key in ('{http://www.w3.org/1999/xlink}href', 'href'):
            href = element.get(key, '')
            if not href.startswith('data:image/') or ';base64,' not in href:
                continue
            if href.split(';', 1)[0] not in ('data:image/jpeg', 'data:image/png',
                                               'data:image/webp', 'data:image/tiff'):
                continue
            raw = base64.b64decode(href.split(',', 1)[1])
            with Image.open(io.BytesIO(raw)) as image:
                if image.getexif().get(274, 1) == 1:
                    continue
                oriented = ImageOps.exif_transpose(image)
                output = io.BytesIO()
                oriented.save(output, 'PNG', exif=b'')
            element.set(key, 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode('ascii'))
            changed = True
    return ET.tostring(root, encoding='utf-8', xml_declaration=True) if changed else svg
