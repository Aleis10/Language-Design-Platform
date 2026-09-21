from typing import Dict, List, Optional, Sequence, Tuple, Mapping
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QFontDatabase, QFont

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen

try:
    from ui.components.glyph_canvas import VectorStroke
except ImportError:
    from ..ui.components.glyph_canvas import VectorStroke

# Font constants
PPUA_START = 0xE000
PPUA_END = 0xF8FF
FONT_FAMILY = "LexiLogograms"
PS_NAME = "LexiLogograms"
UNITS_PER_EM = 1000  # logical canvas is 500x500 -> scale x2 for decent metrics
FONTS_SUBDIR = "fonts"


# Core font builder (stroke → closed contour → TTF)

def stroke_to_closed_path(stroke_path: QPainterPath, width: float) -> QPainterPath:
    if stroke_path.isEmpty():
        return QPainterPath()

    stroker = QPainterPathStroker()
    stroker.setWidth(max(0.01, width))
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    stroker.setMiterLimit(4.0)
    return stroker.createStroke(stroke_path)


def qpainterpath_to_contours(
    path: QPainterPath, scale: float = 1.0
) -> List[List[Tuple[str, Tuple[float, float], Tuple[float, float], Tuple[float, float]]]]:
    contours: List[List[Tuple[str, Tuple[float, float], Tuple[float, float], Tuple[float, float]]]] = []
    current: List[Tuple[str, Tuple[float, float], Tuple[float, float], Tuple[float, float]]] = []

    count = path.elementCount()
    i = 0
    while i < count:
        el = path.elementAt(i)

        if el.type == QPainterPath.ElementType.MoveToElement:
            if current:
                contours.append(current)
            current = [("move", (_sx(el.x, scale), _sy(el.y, scale)),
                       (_sx(el.x, scale), _sy(el.y, scale)),
                       (_sx(el.x, scale), _sy(el.y, scale)))]
            i += 1

        elif el.type == QPainterPath.ElementType.LineToElement:
            current.append(("line", (_sx(el.x, scale), _sy(el.y, scale)),
                           (_sx(el.x, scale), _sy(el.y, scale)),
                           (_sx(el.x, scale), _sy(el.y, scale))))
            i += 1

        elif el.type == QPainterPath.ElementType.CurveToElement:
            c1 = (_sx(el.x, scale), _sy(el.y, scale))
            c2, end = c1, c1
            if i + 2 < count:
                el2 = path.elementAt(i + 1)
                el3 = path.elementAt(i + 2)
                if el2.type == QPainterPath.ElementType.CurveToDataElement and \
                   el3.type == QPainterPath.ElementType.CurveToDataElement:
                    c2 = (_sx(el2.x, scale), _sy(el2.y, scale))
                    end = (_sx(el3.x, scale), _sy(el3.y, scale))
            current.append(("cubic", c1, c2, end))
            i += 3

        else:
            i += 1

    if current:
        contours.append(current)
    return contours


def _flip_y(path: QPainterPath, canvas_size: float, scale: float) -> QPainterPath:
    out = QPainterPath()
    count = path.elementCount()
    if count == 0:
        return out
    first = path.elementAt(0)
    mx = first.x * scale
    my = (canvas_size - first.y) * scale
    out.moveTo(mx, my)
    i = 1
    while i < count:
        el = path.elementAt(i)
        if el.type == QPainterPath.ElementType.LineToElement:
            out.lineTo(el.x * scale, (canvas_size - el.y) * scale)
            i += 1
        elif el.type == QPainterPath.ElementType.CurveToElement:
            if i + 2 < count:
                e2 = path.elementAt(i + 1)
                e3 = path.elementAt(i + 2)
                out.cubicTo(
                    el.x * scale, (canvas_size - el.y) * scale,
                    e2.x * scale, (canvas_size - e2.y) * scale,
                    e3.x * scale, (canvas_size - e3.y) * scale,
                )
                i += 3
            else:
                i += 1
        elif el.type == QPainterPath.ElementType.MoveToElement:
            out.moveTo(el.x * scale, (canvas_size - el.y) * scale)
            i += 1
        else:
            i += 1
    return out


def _sx(x: float, scale: float) -> float:
    return float(x) * scale


def _sy(y: float, scale: float) -> float:
    return float(y) * scale


def _feed_contour_to_pen(
    pen,
    contour: List[Tuple[str, Tuple[float, float], Tuple[float, float], Tuple[float, float]]],
) -> None:
    if not contour:
        return
    first_pt = contour[0][3]
    pen.moveTo(first_pt)
    for kind, c1, c2, end in contour[1:]:
        if kind == "line":
            pen.lineTo(end)
        elif kind == "cubic":
            pen.curveTo(c1, c2, end)
    pen.closePath()


class FilledContour:
    """Wrapper marking a pre-filled QPainterPath as a direct glyph contour."""

    def __init__(self, path: QPainterPath):
        self.path = path


def strokes_to_ttf(
    glyphs: Dict[str, Sequence[Tuple[QPainterPath, float]]],
    output_path: str,
    family: str = FONT_FAMILY,
    units_per_em: int = UNITS_PER_EM,
) -> Dict[str, int]:
    scale = units_per_em / 500.0
    glyph_order: List[str] = [".notdef"]
    cmapping: Dict[int, str] = {}
    pen_map: Dict[str, TTGlyphPen] = {}
    adv_widths: Dict[str, Tuple[int, int]] = {".notdef": (units_per_em // 2, 0)}

    cp = PPUA_START
    for gname, strokes in glyphs.items():
        gname_clean = _sanitize_glyph_name(gname)
        glyph_order.append(gname_clean)
        adv_widths[gname_clean] = (units_per_em, 0)

        pen = TTGlyphPen(None)
        qupen = Cu2QuPen(pen, max_err=1.0, all_quadratic=True)
        for spath, swidth in strokes:
            if isinstance(spath, FilledContour):
                # pre-filled contour (external path SVG): use path directly
                flipped = _flip_y(spath.path, 500.0, scale)
                for contour in qpainterpath_to_contours(flipped, 1.0):
                    if len(contour) < 2:
                        continue
                    _feed_contour_to_pen(qupen, contour)
                continue
            closed = stroke_to_closed_path(spath, swidth)
            if closed.isEmpty():
                continue
            # canvas is Y-down; fonts are Y-up — flip so the glyph isn't rotated 180
            flipped = _flip_y(closed, 500.0, scale)
            for contour in qpainterpath_to_contours(flipped, 1.0):
                if len(contour) < 2:
                    continue
                _feed_contour_to_pen(qupen, contour)
        pen_map[gname_clean] = pen

        if cp <= PPUA_END:
            cmapping[cp] = gname_clean
            cp += 1

    glyphs_obj = {}
    for gname, pen in pen_map.items():
        glyphs_obj[gname] = pen.glyph()
    empty_pen = TTGlyphPen(None)
    glyphs_obj[".notdef"] = empty_pen.glyph()

    fb = FontBuilder(units_per_em)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmapping)
    fb.setupGlyf(glyphs_obj)
    fb.setupHorizontalMetrics(adv_widths)

    ascent = int(units_per_em * 0.8)
    descent = -int(units_per_em * 0.2)
    fb.setupHorizontalHeader(
        ascent=ascent,
        descent=descent,
        lineGap=0,
    )
    fb.setupNameTable(
        {
            "familyName": family,
            "styleName": "Regular",
            "uniqueFontIdentifier": f"{family}: 1.0",
            "fullName": family,
            "psName": PS_NAME,
            "version": "Version 1.0",
            "manufacturer": "Lexicography Workspace",
        }
    )
    fb.setupOS2(
        sTypoAscender=ascent,
        sTypoDescender=descent,
        sTypoLineGap=0,
        usWinAscent=ascent,
        usWinDescent=-descent,
        xAvgCharWidth=units_per_em // 2,
        fsSelection=0b1000000,
        usWeightClass=400,
        usWidthClass=5,
        fsType=0,
    )
    fb.setupPost()
    fb.setupMaxp()
    fb.setupHead(
        created=0,
        unitsPerEm=units_per_em,
        macStyle=0,
        lowestRecPPEM=6,
    )

    fb.font["OS/2"].sTypoDescender = -int(units_per_em * 0.25)
    fb.save(output_path)
    return {gname: cp for cp, gname in cmapping.items()}


def _sanitize_glyph_name(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum() and ord(ch) < 128:
            out.append(ch)
        elif ch in "._":
            out.append(ch)
        else:
            out.append(f"uni{ord(ch):04X}")
    s = "".join(out)
    if not s:
        s = "glyph"
    if s[0].isdigit():
        s = "g" + s
    return s[:63]


def build_font_from_strokes(
    strokes_by_glyph: Mapping[str, Sequence[object]],
    output_path: str,
    family: str = FONT_FAMILY,
) -> Dict[str, int]:
    glyphs: Dict[str, List[Tuple[object, float]]] = {}
    for gname, strokes in strokes_by_glyph.items():
        entry: List[Tuple[object, float]] = []
        for s in strokes:
            if isinstance(s, FilledContour):
                # pre-filled contour (external path SVG): mark width -1
                entry.append((s, -1.0))
                continue
            if getattr(s, "is_eraser", False):
                continue
            entry.append((s.build_path(), s.width))
        glyphs[gname] = entry
    return strokes_to_ttf(glyphs, output_path, family=family)


# Export service (glyph DB → font file)

@dataclass
class FontExportResult:
    ttf_path: str
    mapping_path: str
    family_name: str
    num_glyphs: int
    mapping: Dict[str, int]


def _extract_strokes(svg_str: str) -> List[object]:
    if not svg_str:
        return []
    try:
        root = ET.fromstring(svg_str)
        meta = root.find(".//{*}metadata")
        if meta is None:
            meta = root.find(".//metadata")
        if meta is not None and meta.text:
            data = json.loads(meta.text.strip())
            return [VectorStroke.from_dict(item) for item in data]
    except Exception:
        pass
    # no stroke metadata: fall back to any <path d="..."> as a filled contour
    try:
        root = ET.fromstring(svg_str)
        for el in root.iter():
            if el.tag.split("}")[-1] == "path":
                d = el.get("d")
                if d:
                    qp = _parse_svg_path(d)
                    if not qp.isEmpty():
                        return [FilledContour(qp)]
    except Exception:
        pass
    return []


def _parse_svg_path(d: str) -> QPainterPath:
    """Parse an SVG path 'd' attribute (M/L/C/Q/Z) into a QPainterPath."""
    path = QPainterPath()
    tokens = re.findall(r"[MLCQZmlcqz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?", d)
    i = 0
    cur = QPointF(0, 0)
    n = len(tokens)
    while i < n:
        cmd = tokens[i]
        i += 1
        if cmd in "Mm":
            x = float(tokens[i]); y = float(tokens[i + 1]); i += 2
            if cmd == "m":
                x += cur.x(); y += cur.y()
            cur = QPointF(x, y)
            path.moveTo(cur)
        elif cmd in "Ll":
            x = float(tokens[i]); y = float(tokens[i + 1]); i += 2
            if cmd == "l":
                x += cur.x(); y += cur.y()
            cur = QPointF(x, y)
            path.lineTo(cur)
        elif cmd in "Cc":
            x1 = float(tokens[i]); y1 = float(tokens[i + 1]); i += 2
            x2 = float(tokens[i]); y2 = float(tokens[i + 1]); i += 2
            x = float(tokens[i]); y = float(tokens[i + 1]); i += 2
            if cmd == "c":
                x1 += cur.x(); y1 += cur.y()
                x2 += cur.x(); y2 += cur.y()
                x += cur.x(); y += cur.y()
            path.cubicTo(QPointF(x1, y1), QPointF(x2, y2), QPointF(x, y))
            cur = QPointF(x, y)
        elif cmd in "Qq":
            x1 = float(tokens[i]); y1 = float(tokens[i + 1]); i += 2
            x = float(tokens[i]); y = float(tokens[i + 1]); i += 2
            if cmd == "q":
                x1 += cur.x(); y1 += cur.y()
                x += cur.x(); y += cur.y()
            path.quadTo(QPointF(x1, y1), QPointF(x, y))
            cur = QPointF(x, y)
        elif cmd in "Zz":
            path.closeSubpath()
    return path


def export_language_font(
    glyph_rows: List[Dict],
    output_dir: str,
    family: str = FONT_FAMILY,
) -> FontExportResult:
    os.makedirs(output_dir, exist_ok=True)
    strokes_by_name: Dict[str, List[object]] = {}
    id_by_name: Dict[str, str] = {}
    name_by_id: Dict[str, str] = {}

    for row in glyph_rows:
        name = row.get("name") or row.get("id") or "glyph"
        strokes = _extract_strokes(row.get("svg_data", ""))
        gname = _sanitize_glyph_name(name)
        strokes_by_name[gname] = strokes
        id_by_name[gname] = row.get("id", name)
        name_by_id[row.get("id", name)] = gname

    ttf_path = os.path.join(output_dir, f"{family}.ttf")
    mapping = build_font_from_strokes(strokes_by_name, ttf_path, family=family)

    by_id: Dict[str, int] = {}
    for name, cp in mapping.items():
        gid = id_by_name.get(name, name)
        by_id[gid] = cp

    mapping_path = os.path.join(output_dir, f"{family}.mapping.json")
    with open(mapping_path, "w") as f:
        json.dump(
            {
                "family": family,
                "ttf": os.path.basename(ttf_path),
                "glyphs": by_id,
                "notes": "codepoints are in Unicode Private Use Area U+E000+; "
                         "type the character in a field using this font to render the glyph",
            },
            f,
            indent=2,
        )

    return FontExportResult(
        ttf_path=ttf_path,
        mapping_path=mapping_path,
        family_name=family,
        num_glyphs=len(by_id),
        mapping=by_id,
    )


# Font registry (Qt font loading, glyph lookup)

def get_fonts_dir(data_dir: str) -> str:
    d = os.path.join(data_dir, FONTS_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


def register_language_font(data_dir: str) -> Optional[str]:
    fonts_dir = get_fonts_dir(data_dir)
    if not os.path.isdir(fonts_dir):
        return None

    candidates = sorted(
        f for f in os.listdir(fonts_dir)
        if f.lower().endswith((".ttf", ".otf"))
    )
    for fname in candidates:
        path = os.path.join(fonts_dir, fname)
        fid = QFontDatabase.addApplicationFont(path)
        families = QFontDatabase.applicationFontFamilies(fid)
        if families:
            return families[0]
    return None


def load_font_mapping(data_dir: str) -> Dict[str, int]:
    fonts_dir = get_fonts_dir(data_dir)
    if not os.path.isdir(fonts_dir):
        return {}
    for fname in sorted(os.listdir(fonts_dir)):
        if fname.endswith(".mapping.json"):
            try:
                with open(os.path.join(fonts_dir, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                glyphs = data.get("glyphs", {})
                return {gid: int(cp) for gid, cp in glyphs.items()}
            except Exception:
                continue
    return {}


def glyph_codepoint(data_dir: str, glyph_id: str) -> Optional[int]:
    return load_font_mapping(data_dir).get(glyph_id)


def glyph_character(data_dir: str, glyph_id: str) -> str:
    cp = glyph_codepoint(data_dir, glyph_id)
    if cp is None:
        return ""
    return chr(cp)


def conlang_font(family: Optional[str] = None, point_size: int = 11) -> QFont:
    return QFont(family or FONT_FAMILY, point_size)


def apply_conlang_font(widget, data_dir: str, point_size: int = 11) -> None:
    fam = register_language_font(data_dir) or FONT_FAMILY
    if fam:
        widget.setFont(QFont(fam, point_size))