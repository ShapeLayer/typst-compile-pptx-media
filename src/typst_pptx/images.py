"""Translate PDF image placement without stretching rotated image pixels."""
import base64
import io
import math
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
