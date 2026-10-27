"""Small, dependency-free OPC / DrawingML writer used by the compiler."""
import mimetypes
from xml.etree import ElementTree as E
from zipfile import ZipFile, ZIP_DEFLATED

NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main"}
for prefix, uri in NS.items():
    E.register_namespace(prefix, uri)


def node(tag, attrs=None, *children):
    prefix, name = tag.split(":")
    el = E.Element(f"{{{NS[prefix]}}}{name}", {k: str(v) for k, v in (attrs or {}).items()})
    el.extend(children)
    return el


def sub(parent, tag, attrs=None, *children):
    el = node(tag, attrs, *children)
    parent.append(el)
    return el


def emu(pt):
    return str(round(pt * 12700))


def color(rgb):
    if isinstance(rgb, int):
        return f"{rgb:06X}"
    if len(rgb) == 1:
        rgb = rgb * 3
    return ''.join(f'{max(0, min(255, round(c * 255))):02X}' for c in rgb[:3])


def solid(parent, rgb, opacity=1):
    c = sub(sub(parent, "a:solidFill"), "a:srgbClr", {"val": color(rgb)})
    if opacity < 1:
        sub(c, "a:alpha", {"val": round(opacity * 100000)})


def transform(parent, box):
    x, y, w, h = box
    return sub(parent, "a:xfrm", None,
               node("a:off", {"x": emu(x), "y": emu(y)}),
               node("a:ext", {"cx": emu(max(w, .001)), "cy": emu(max(h, .001))}))


class Deck:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.parts = {}
        self.types = {}
        self.slides = []

    def asset(self, data, extension, content_type=None):
        name = f"media/asset{len(self.types) + 1}.{extension}"
        self.parts['ppt/' + name] = data
        self.types['ppt/' + name] = content_type or mimetypes.guess_type(name)[0] or 'application/octet-stream'
        return '../' + name

    def slide(self):
        slide = Slide(self)
        self.slides.append(slide)
        return slide

    def save(self, path):
        ct = 'application/vnd.openxmlformats-officedocument.presentationml.'
        self.parts['ppt/presentation.xml'] = node('p:presentation', None,
            node('p:sldMasterIdLst', None, node('p:sldMasterId', {'id': 2147483648, '{'+NS['r']+'}id': 'rId1'})),
            node('p:sldIdLst', None, *[node('p:sldId', {'id': 256+i, '{'+NS['r']+'}id': f'rId{i+2}'}) for i in range(len(self.slides))]),
            node('p:sldSz', {'cx': emu(self.width), 'cy': emu(self.height), 'type': 'custom'}),
            node('p:notesSz', {'cx': 6858000, 'cy': 9144000}))
        self.types['ppt/presentation.xml'] = ct + 'presentation.main+xml'
        rels = [('slideMaster', 'slideMasters/slideMaster1.xml', False)]
        rels += [('slide', f'slides/slide{i+1}.xml', False) for i in range(len(self.slides))]
        self.parts['ppt/_rels/presentation.xml.rels'] = relationships(rels)
        mapping = node('p:clrMap', dict(bg1='lt1', tx1='dk1', bg2='lt2', tx2='dk2', accent1='accent1', accent2='accent2', accent3='accent3', accent4='accent4', accent5='accent5', accent6='accent6', hlink='hlink', folHlink='folHlink'))
        self.parts['ppt/slideMasters/slideMaster1.xml'] = node('p:sldMaster', None,
            node('p:cSld', None, empty_tree()), mapping,
            node('p:sldLayoutIdLst', None, node('p:sldLayoutId', {'id': 2147483649, '{'+NS['r']+'}id': 'rId1'})), node('p:txStyles', None, node('p:titleStyle'), node('p:bodyStyle'), node('p:otherStyle')))
        self.types['ppt/slideMasters/slideMaster1.xml'] = ct + 'slideMaster+xml'
        self.parts['ppt/slideMasters/_rels/slideMaster1.xml.rels'] = relationships([('slideLayout', '../slideLayouts/slideLayout1.xml', False), ('theme', '../theme/theme1.xml', False)])
        self.parts['ppt/slideLayouts/slideLayout1.xml'] = node('p:sldLayout', {'type': 'blank', 'preserve': 1}, node('p:cSld', {'name': 'Blank'}, empty_tree()), node('p:clrMapOvr', None, node('a:masterClrMapping')))
        self.types['ppt/slideLayouts/slideLayout1.xml'] = ct + 'slideLayout+xml'
        self.parts['ppt/slideLayouts/_rels/slideLayout1.xml.rels'] = relationships([('slideMaster', '../slideMasters/slideMaster1.xml', False)])
        colors = node('a:clrScheme', {'name': 'Typst'})
        for k, v in dict(dk1='000000', lt1='FFFFFF', dk2='172033', lt2='EEEEEE', accent1='4775D1', accent2='ED7D31', accent3='A5A5A5', accent4='FFC000', accent5='5B9BD5', accent6='70AD47', hlink='0563C1', folHlink='954F72').items():
            sub(colors, 'a:'+k, None, node('a:srgbClr', {'val': v}))
        fonts = node('a:fontScheme', {'name': 'Typst'})
        for kind in ['majorFont', 'minorFont']:
            sub(fonts, 'a:'+kind, None, node('a:latin', {'typeface': 'Arial'}), node('a:ea', {'typeface': ''}), node('a:cs', {'typeface': ''}))
        fmt = node('a:fmtScheme', {'name': 'Typst'})
        for kind in ['fillStyleLst', 'lnStyleLst', 'effectStyleLst', 'bgFillStyleLst']:
            lst = sub(fmt, 'a:'+kind)
            for _ in range(3):
                if kind == 'lnStyleLst':
                    sub(lst, 'a:ln', {'w': 12700}, node('a:solidFill', None, node('a:schemeClr', {'val': 'phClr'})), node('a:prstDash', {'val': 'solid'}))
                elif kind == 'effectStyleLst':
                    sub(lst, 'a:effectStyle', None, node('a:effectLst'))
                else:
                    sub(lst, 'a:solidFill', None, node('a:schemeClr', {'val': 'phClr'}))
        self.parts['ppt/theme/theme1.xml'] = node('a:theme', {'name': 'Typst'}, node('a:themeElements', None, colors, fonts, fmt))
        self.types['ppt/theme/theme1.xml'] = 'application/vnd.openxmlformats-officedocument.theme+xml'
        for i, slide in enumerate(self.slides, 1):
            self.parts[f'ppt/slides/slide{i}.xml'] = slide.root
            self.parts[f'ppt/slides/_rels/slide{i}.xml.rels'] = relationships(slide.rels)
            self.types[f'ppt/slides/slide{i}.xml'] = ct + 'slide+xml'
        self.parts['_rels/.rels'] = relationships([('officeDocument', 'ppt/presentation.xml', False)])
        ns = 'http://schemas.openxmlformats.org/package/2006/content-types'
        types = E.Element('{'+ns+'}Types')
        for ext, mime in [('rels', 'application/vnd.openxmlformats-package.relationships+xml'), ('xml', 'application/xml')]:
            E.SubElement(types, '{'+ns+'}Default', Extension=ext, ContentType=mime)
        for name, mime in self.types.items():
            E.SubElement(types, '{'+ns+'}Override', PartName='/'+name, ContentType=mime)
        self.parts['[Content_Types].xml'] = types
        with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
            for name, data in self.parts.items():
                if not isinstance(data, bytes):
                    if data.tag.endswith('}Types') or data.tag.endswith('}Relationships'):
                        E.register_namespace('', data.tag[1:].split('}')[0])
                    data = E.tostring(data, encoding='utf-8', xml_declaration=True)
                archive.writestr(name, data)


def relationships(items):
    ns = 'http://schemas.openxmlformats.org/package/2006/relationships'
    root = E.Element('{'+ns+'}Relationships')
    for i, (kind, target, external) in enumerate(items, 1):
        uri = NS['r'] + '/' + kind if not kind.startswith('http') else kind
        attrs = dict(Id=f'rId{i}', Type=uri, Target=target)
        if external:
            attrs['TargetMode'] = 'External'
        E.SubElement(root, '{'+ns+'}Relationship', attrs)
    return root


def empty_tree():
    return node('p:spTree', None,
        node('p:nvGrpSpPr', None, node('p:cNvPr', {'id': 1, 'name': ''}), node('p:cNvGrpSpPr'), node('p:nvPr')),
        node('p:grpSpPr', None, node('a:xfrm', None, node('a:off', {'x': 0, 'y': 0}), node('a:ext', {'cx': 0, 'cy': 0}), node('a:chOff', {'x': 0, 'y': 0}), node('a:chExt', {'cx': 0, 'cy': 0}))))


class Slide:
    def __init__(self, deck):
        self.deck = deck
        self.rels = [('slideLayout', '../slideLayouts/slideLayout1.xml', False)]
        self.tree = empty_tree()
        self.root = node('p:sld', None, node('p:cSld', None, self.tree), node('p:clrMapOvr', None, node('a:masterClrMapping')))
        self.next_id = 2

    def rid(self, kind, target, external=False):
        self.rels.append((kind, target, external))
        return f'rId{len(self.rels)}'

    def identity(self, name):
        result = node('p:cNvPr', {'id': self.next_id, 'name': f'{name} {self.next_id}'})
        self.next_id += 1
        return result

    def picture(self, data, extension, box, background=False, svg=None):
        rid = self.rid('image', self.deck.asset(data, extension))
        blip = node('a:blip', {'{'+NS['r']+'}embed': rid})
        if svg is not None:
            svg_rid = self.rid('image', self.deck.asset(svg, 'svg', 'image/svg+xml'))
            ext = sub(sub(blip, 'a:extLst'), 'a:ext', {'uri': '{96DAC541-7B7A-43D3-8B79-37D633B846F1}'})
            E.SubElement(ext, '{http://schemas.microsoft.com/office/drawing/2016/SVG/main}svgBlip', {'{'+NS['r']+'}embed': svg_rid})
        if background:
            csld = self.root.find('p:cSld', NS)
            bg = node('p:bg', None, node('p:bgPr', None, node('a:blipFill', {'dpi': 0, 'rotWithShape': 1}, blip, node('a:stretch', None, node('a:fillRect'))), node('a:effectLst')))
            csld.insert(0, bg)
            return
        identity = self.identity('Image')
        pic = sub(self.tree, 'p:pic', None, node('p:nvPicPr', None, identity, node('p:cNvPicPr', None, node('a:picLocks', {'noChangeAspect': 1})), node('p:nvPr')),
            node('p:blipFill', None, blip, node('a:stretch', None, node('a:fillRect'))))
        sp = sub(pic, 'p:spPr')
        transform(sp, box)
        sub(sp, 'a:prstGeom', {'prst': 'rect'}, node('a:avLst'))
        return pic

    def text(self, text, box, font, size, rgb, flags=0, rotation=0, opacity=1):
        sp = sub(self.tree, 'p:sp', None, node('p:nvSpPr', None, self.identity('Text'), node('p:cNvSpPr', {'txBox': 1}), node('p:nvPr')))
        props = sub(sp, 'p:spPr')
        xf = transform(props, box)
        if rotation:
            xf.set('rot', str(round(rotation * 60000)))
        sub(props, 'a:prstGeom', {'prst': 'rect'}, node('a:avLst'))
        sub(props, 'a:noFill')
        body = sub(sp, 'p:txBody', None, node('a:bodyPr', {'wrap': 'none', 'lIns': 0, 'tIns': 0, 'rIns': 0, 'bIns': 0, 'anchor': 't'}, node('a:noAutofit')), node('a:lstStyle'))
        para = sub(body, 'a:p')
        sub(para, 'a:pPr', None, node('a:lnSpc', None, node('a:spcPct', {'val': 100000})), node('a:spcBef', None, node('a:spcPts', {'val': 0})))
        run = sub(para, 'a:r')
        rpr = sub(run, 'a:rPr', {'lang': 'en-US', 'sz': round(size * 100), 'b': int(bool(flags & 16)), 'i': int(bool(flags & 2)), 'dirty': 0})
        solid(rpr, rgb, opacity)
        sub(rpr, 'a:latin', {'typeface': font})
        sub(rpr, 'a:ea', {'typeface': font})
        sub(rpr, 'a:cs', {'typeface': font})
        sub(run, 'a:t').text = text
        return sp

    def drawing(self, drawing):
        rect = drawing['rect']
        x, y = rect.x0, rect.y0
        w, h = max(rect.width, .01), max(rect.height, .01)
        sp = sub(self.tree, 'p:sp', None, node('p:nvSpPr', None, self.identity('Path'), node('p:cNvSpPr'), node('p:nvPr')))
        props = sub(sp, 'p:spPr')
        transform(props, (x, y, w, h))
        geom = sub(props, 'a:custGeom', None, node('a:avLst'), node('a:gdLst'), node('a:ahLst'), node('a:cxnLst'), node('a:rect', {'l': 0, 't': 0, 'r': 'w', 'b': 'h'}))
        path = sub(sub(geom, 'a:pathLst'), 'a:path', {'w': emu(w), 'h': emu(h), 'fill': 'norm' if drawing.get('fill') else 'none', 'stroke': int(drawing.get('color') is not None)})
        current = None
        def point(tag, points):
            el = sub(path, 'a:'+tag)
            for pt in points:
                sub(el, 'a:pt', {'x': emu(pt.x-x), 'y': emu(pt.y-y)})
        for item in drawing['items']:
            kind = item[0]
            if kind in ('l', 'c'):
                if current != item[1]:
                    point('moveTo', [item[1]])
                point('lnTo' if kind == 'l' else 'cubicBezTo', item[2:])
                current = item[-1]
            elif kind in ('re', 'qu'):
                r = item[1]
                pts = [r.tl, r.tr, r.br, r.bl] if kind == 're' else [r.ul, r.ur, r.lr, r.ll]
                if kind == 're' and item[2] < 0:
                    pts.reverse()
                point('moveTo', [pts[0]])
                for pt in pts[1:]:
                    point('lnTo', [pt])
                sub(path, 'a:close')
                current = None
        if drawing.get('closePath'):
            sub(path, 'a:close')
        if drawing.get('fill') is not None:
            solid(props, drawing['fill'], drawing.get('fill_opacity', 1))
        else:
            sub(props, 'a:noFill')
        line = sub(props, 'a:ln', {'w': emu((drawing.get('width') or 1)), 'cap': ['flat', 'rnd', 'sq'][min(2, max((drawing.get('lineCap') or (0,))))]})
        if drawing.get('color') is not None:
            solid(line, drawing['color'], drawing.get('stroke_opacity', 1))
        else:
            sub(line, 'a:noFill')
        return sp

    def video(self, data, extension, source, thumbnail, box, playback):
        pic = self.picture(thumbnail, 'png', box)
        nv = pic.find('p:nvPicPr', NS)
        cpr = nv.find('p:cNvPr', NS)
        cpr.set('name', f'Video {source}')
        shape_id = cpr.get('id')
        sub(cpr, 'a:hlinkClick', {'{'+NS['r']+'}id': '', 'action': 'ppaction://media'})
        external = data is None
        target = source if external else self.deck.asset(data, extension)
        video_id = self.rid('video', target, external)
        media_id = self.rid('http://schemas.microsoft.com/office/2007/relationships/media', target, external)
        nvpr = nv.find('p:nvPr', NS)
        sub(nvpr, 'a:videoFile', {'{'+NS['r']+'}link': video_id})
        ext = sub(sub(nvpr, 'p:extLst'), 'p:ext', {'uri': '{DAA4B4D4-6D71-4841-9C94-3DE7FCFB9EE3}'})
        sub(ext, 'p14:media', {'{'+NS['r']+'}'+('link' if external else 'embed'): media_id})
        timing = self.root.find('p:timing', NS)
        if timing is None:
            timing = sub(self.root, 'p:timing', None, node('p:tnLst', None, node('p:par', None, node('p:cTn', {'id': 1, 'dur': 'indefinite', 'restart': 'never', 'nodeType': 'tmRoot'}, node('p:childTnLst')))))
        children = timing.find('.//p:childTnLst', NS)
        volume = 0 if playback.get('muted', False) else round(playback.get('volume', 1) * 100000)
        video = sub(children, 'p:video', None)
        media = sub(video, 'p:cMediaNode', {'vol': volume, 'numSld': 1, 'showWhenStopped': 1})
        attrs = {'id': self.next_id + 100, 'fill': 'hold', 'display': 0}
        if playback.get('loop', False):
            attrs['repeatCount'] = 'indefinite'
        ctn = sub(media, 'p:cTn', attrs)
        conditions = sub(ctn, 'p:stCondLst')
        if playback.get('autoplay', False):
            sub(conditions, 'p:cond', {'delay': 0})
        else:
            sub(conditions, 'p:cond', {'evt': 'onClick', 'delay': 0}, node('p:tgtEl', None, node('p:spTgt', {'spid': shape_id})))
        sub(media, 'p:tgtEl', None, node('p:spTgt', {'spid': shape_id}))
