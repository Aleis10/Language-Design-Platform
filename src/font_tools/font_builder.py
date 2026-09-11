"""
Font builder — converts logogram strokes (QPainterPath) into a TrueType font
whose glyphs live in the Unicode Private Use Area (U+E000..U+F8FF).

The chain:
  VectorStroke (points, width)
    -> QPainterPath (you already build this via stroke.build_path())
    -> QPainterPathStroker  (Qt expands stroke to a CLOSED filled band)
    -> extract curves (cubic -> TTGlyphPen.curveTo handles quad conversion)
    -> TTGlyphPen -> glyf contours
    -> FontBuilder assembles tables (glyf, cmap, hmtx, head, OS/2, name...)
    -> .ttf file on disk
    -> QFontDatabase.addApplicationFont(path) at app start
    -> typing U+E000.. renders the glyph character

No rasterization, no potrace. Qt's QPainterPathStroker does the stroke->fill
expansion natively, preserving the calligraphic stroke ends (round caps).
"""
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainterPath, QPainterPathStroker

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.boundsPen import BoundsPen

# ---------------------------------------------------------------------------
# Stroke -> closed contour via QPainterPathStroker
# ---------------------------------------------------------------------------

PPUA_START = 0xE000
PPUA_END = 0xF8FF

FONT_FAMILY = "LexiLogograms"
PS_NAME = "LexiLogograms"
UNITS_PER_EM = 1000  # logical canvas is 500x500 -> scale x2 for decent metrics


def stroke_to_closed_path(stroke_path: QPainterPath, width: float) -> QPainterPath:
    """Expand an open stroked path into a closed, filled outline band."""
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
    """
    Walk a QPainterPath and split it into closed contour segment lists.
    Each contour is a list of segment tuples:
      ('move', None, None, end)
      ('line', None, None, end)
      ('cubic', c1, c2, end)
    """
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
            # c1 is THIS element; c2 + end are the next 2 CurveToDataElements
            c1 = (_sx(el.x, scale), _sy(el.y, scale))
            # read c2 and end
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


def _sx(x: float, scale: float) -> float:
    return float(x) * scale


def _sy(y: float, scale: float) -> float:
    return float(y) * scale


def _feed_contour_to_pen(
    pen,
    contour: List[Tuple[str, Tuple[float, float], Tuple[float, float], Tuple[float, float]]],
) -> None:
    """Push a segmentized contour into a pen (TTGlyphPen or Cu2QuPen-wrapped)."""
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


# ---------------------------------------------------------------------------
# Font assembly
# ---------------------------------------------------------------------------

def strokes_to_ttf(
    glyphs: Dict[str, Sequence[Tuple[QPainterPath, float]]],
    output_path: str,
    family: str = FONT_FAMILY,
    units_per_em: int = UNITS_PER_EM,
) -> Dict[str, int]:
    """
    Build a TTF from glyph outlines.

    Args:
        glyphs: {glyph_name: [(stroke_path, stroke_width), ...]}
        output_path: where to write the .ttf
        family: font family name
        units_per_em: font units per em. Canvas is 500 -> scale = upe/500.
    Returns:
        {glyph_name: codepoint} mapping for callers to persist.
    """
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
        # Cu2QuPen converts cubic curves to quadratics on the fly (glyf needs quads)
        qupen = Cu2QuPen(pen, max_err=1.0, all_quadratic=True)
        for spath, swidth in strokes:
            closed = stroke_to_closed_path(spath, swidth)
            if closed.isEmpty():
                continue
            for contour in qpainterpath_to_contours(closed, scale):
                if len(contour) < 2:
                    continue
                _feed_contour_to_pen(qupen, contour)
        pen_map[gname_clean] = pen

        if cp <= PPUA_END:
            cmapping[cp] = gname_clean
            cp += 1

    # Compute real bounds from the pens for head/OS2
    glyphs_obj = {}
    for gname, pen in pen_map.items():
        glyphs_obj[gname] = pen.glyph()
    # .notdef: blank glyph (must be a real Glyph object for FontBuilder)
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
    # Return the mapping in the caller-friendly direction: glyph_name -> codepoint
    return {gname: cp for cp, gname in cmapping.items()}


def _sanitize_glyph_name(name: str) -> str:
    """FontTools glyph names: alnum + '.' + '_' only."""
    out = [ch if (ch.isalnum() or ch in "._") else "_" for ch in name]
    s = "".join(out)
    if not s:
        s = "glyph"
    if s[0].isdigit():
        s = "g" + s
    return s[:63]


# ---------------------------------------------------------------------------
# Convenience: build from VectorStroke objects (glyph_canvas)
# ---------------------------------------------------------------------------

def build_font_from_strokes(
    strokes_by_glyph: Dict[str, Sequence[object]],
    output_path: str,
    family: str = FONT_FAMILY,
) -> Dict[str, int]:
    """
    Convenience wrapper — takes the app's VectorStroke objects directly.
    strokes_by_glyph: {glyph_name: [VectorStroke, ...]}
    Returns {glyph_name: PPUA codepoint}.
    """
    glyphs: Dict[str, List[Tuple[QPainterPath, float]]] = {}
    for gname, strokes in strokes_by_glyph.items():
        entry: List[Tuple[QPainterPath, float]] = []
        for s in strokes:
            if getattr(s, "is_eraser", False):
                continue
            entry.append((s.build_path(), s.width))
        glyphs[gname] = entry
    return strokes_to_ttf(glyphs, output_path, family=family)