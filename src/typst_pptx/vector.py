"""Preserve PDF vector paths as standalone SVG picture assets."""
import re
from xml.etree import ElementTree as ET

import pymupdf as fitz
from .ooxml import color


def drawing_svg(drawing, ppi=192):
    """Return SVG bytes, transparent PNG fallback, and the picture rectangle."""
    rect = fitz.Rect(drawing['rect'])
    stroke = drawing.get('color') is not None
    width = drawing.get('width') or 1
    # Leave room for stroke joins and antialiasing outside the PDF path bounds.
    pad = width * 5 if stroke else 0
    rect = fitz.Rect(rect.x0-pad, rect.y0-pad, rect.x1+pad, rect.y1+pad)
    w, h = max(rect.width, .01), max(rect.height, .01)
    svg = ET.Element('svg', {'xmlns': 'http://www.w3.org/2000/svg',
        'width': str(w), 'height': str(h), 'viewBox': f'{rect.x0} {rect.y0} {w} {h}'})
    commands = []
    current = None

    def point(p):
        return f'{p.x:.9g} {p.y:.9g}'

    for item in drawing['items']:
        kind = item[0]
        if kind in ('l', 'c'):
            if current != item[1]:
                commands.append('M' + point(item[1]))
            commands.append(('L' if kind == 'l' else 'C') + ' '.join(point(p) for p in item[2:]))
            current = item[-1]
        elif kind in ('re', 'qu'):
            shape = item[1]
            pts = [shape.tl, shape.tr, shape.br, shape.bl] if kind == 're' else [shape.ul, shape.ur, shape.lr, shape.ll]
            if kind == 're' and item[2] < 0:
                pts.reverse()
            commands.append('M' + point(pts[0]))
            commands.extend('L' + point(p) for p in pts[1:])
            commands.append('Z')
            current = None
        else:
            raise ValueError(f'Unsupported vector path command: {kind}')
    if drawing.get('closePath'):
        commands.append('Z')
    attrs = {'d': ' '.join(commands),
             'fill': '#' + color(drawing['fill']) if drawing.get('fill') is not None else 'none',
             'fill-rule': 'evenodd' if drawing.get('even_odd') else 'nonzero',
             'fill-opacity': str(drawing.get('fill_opacity') or 0),
             'stroke': '#' + color(drawing['color']) if stroke else 'none'}
    if stroke:
        attrs.update({'stroke-width': str(width), 'stroke-opacity': str(drawing.get('stroke_opacity', 1)),
            'stroke-linecap': ['butt', 'round', 'square'][min(2, max(drawing.get('lineCap') or (0,)))],
            'stroke-linejoin': ['miter', 'round', 'bevel'][min(2, round(drawing.get('lineJoin') or 0))]})
        dashes = re.fullmatch(r'\[([^]]*)\]\s*([-+.\d]+)', drawing.get('dashes') or '')
        if dashes and dashes[1].strip():
            attrs['stroke-dasharray'] = dashes[1].strip()
            attrs['stroke-dashoffset'] = dashes[2]
    ET.SubElement(svg, 'path', attrs)
    data = ET.tostring(svg, encoding='utf-8', xml_declaration=True)
    with fitz.open(stream=data, filetype='svg') as fragment:
        fallback = fragment[0].get_pixmap(matrix=fitz.Matrix(ppi/72, ppi/72), alpha=True).tobytes('png')
    return data, fallback, (rect.x0, rect.y0, w, h)
