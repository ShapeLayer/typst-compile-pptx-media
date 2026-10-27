"""Split Typst SVG paint order around native video placeholders."""
import copy
import math
import re
from xml.etree import ElementTree as ET

import pymupdf as fitz

SVG = '{http://www.w3.org/2000/svg}'
# MuPDF's SVG <use> resolver requires unprefixed symbol elements.
ET.register_namespace('', SVG[1:-1])
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
PAINT = {'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'image', 'use', 'text', 'foreignObject'}
RESOURCES = {'defs', 'style', 'metadata', 'title', 'desc'}


def _matrix(value):
    result = fitz.Matrix(1, 1)
    for name, args in re.findall(r'([A-Za-z]+)\s*\(([^)]*)\)', value or ''):
        v = [float(x) for x in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?', args)]
        if name == 'matrix' and len(v) == 6:
            m = fitz.Matrix(*v)
        elif name == 'translate':
            m = fitz.Matrix(1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == 'scale':
            m = fitz.Matrix(v[0], v[1] if len(v) > 1 else v[0])
        elif name == 'rotate':
            m = fitz.Matrix(v[0])
            if len(v) == 3:
                m = fitz.Matrix(1, 0, 0, 1, -v[1], -v[2]) * m * fitz.Matrix(1, 0, 0, 1, v[1], v[2])
        else:
            raise ValueError(f'Unsupported SVG transform in media placement: {name}')
        result = m * result
    return result


def split_media_layers(svg, videos):
    """Return ordered (SVG segment, video or None) pairs without flattening.

    Resource trees and ancestor transforms/clips survive every partition.
    Each placeholder is replaced at its original paint position, so content
    painted later remains above the native video during playback.
    """
    root = ET.fromstring(svg)
    paints, images = [], []
    def visit(el, matrix):
        tag = el.tag.removeprefix(SVG)
        if tag in RESOURCES:
            return
        matrix = _matrix(el.get('transform')) * matrix
        if tag in PAINT:
            index = len(paints)
            paints.append(el)
            if tag == 'image':
                x, y = float(el.get('x', 0)), float(el.get('y', 0))
                w, h = float(el.get('width')), float(el.get('height'))
                box = fitz.Rect(x, y, x+w, y+h) * matrix
                images.append((index, box))
            return
        for child in el:
            visit(child, matrix)
    visit(root, fitz.Matrix(1, 1))
    matches = {}
    for video in videos:
        x, y, w, h = video['box']
        target = fitz.Rect(x, y, x+w, y+h)
        candidates = []
        for index, box in images:
            if index in matches:
                continue
            center_error = math.hypot((box.x0+box.x1-target.x0-target.x1)/2,
                                      (box.y0+box.y1-target.y0-target.y1)/2)
            overlap = (box & target).get_area()
            if center_error < 1 and overlap > .5*min(box.get_area(), target.get_area()):
                candidates.append((abs(box.get_area()-target.get_area()), index))
        if not candidates:
            raise ValueError('Cannot locate media thumbnail in SVG paint order; refusing to cover foreground content')
        matches[min(candidates)[1]] = video
    indices = {id(el): i for i, el in enumerate(paints)}
    def segment(start, end, excluded=()):
        if start == end:
            return None
        def prune(el):
            if el.tag.removeprefix(SVG) in RESOURCES:
                return copy.deepcopy(el)
            index = indices.get(id(el))
            if index is not None:
                return copy.deepcopy(el) if start <= index < end and index not in excluded else None
            out = ET.Element(el.tag, el.attrib)
            out.text, out.tail = el.text, el.tail
            for child in el:
                kept = prune(child)
                if kept is not None:
                    out.append(kept)
            return out if len(out) or el is root else None
        return ET.tostring(prune(root), encoding='utf-8', xml_declaration=True)
    result, start = [], 0
    for index, video in sorted(matches.items()):
        # Isolated placeholder, without overlaid page titles, is its poster.
        result.append((segment(start, index), (video, segment(index, index+1), segment(index+1, len(paints), matches))))
        start = index+1
    result.append((segment(start, len(paints)), None))
    return result
