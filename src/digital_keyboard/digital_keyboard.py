from typing import Dict, List, Optional, Sequence, Tuple, Mapping
import hashlib
import io
import json
import os
import re
import weakref
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from PySide6.QtCore import QByteArray, QEvent, QObject, QPointF, Qt
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QFontDatabase, QFont
from PySide6.QtWidgets import (
    QStyledItemDelegate, QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox,
    QComboBox, QLabel,
)

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
    codepoints: Optional[Dict[str, int]] = None,
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

        # FIX: use the caller-supplied STABLE codepoint when there is one.
        # (Before, codepoints were handed out by loop position, so adding,
        # deleting or reordering a glyph shifted every later glyph.)
        if codepoints and gname_clean in codepoints:
            cmapping[codepoints[gname_clean]] = gname_clean
        elif cp <= PPUA_END:
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
    codepoints: Optional[Dict[str, int]] = None,
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
    return strokes_to_ttf(glyphs, output_path, family=family, codepoints=codepoints)


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
    # no stroke metadata
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
    #Parse an SVG path 'd' attribute (M/L/C/Q/Z) into a QPainterPath
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


def _load_codepoint_table(output_dir: str, family: str) -> Tuple[Dict[str, int], int]:
    """Read the previous mapping.json so existing glyphs KEEP their codepoint."""
    path = os.path.join(output_dir, f"{family}.mapping.json")
    table: Dict[str, int] = {}
    next_cp = PPUA_START
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for gid, cp in data.get("glyphs", {}).items():
                cp = int(cp)
                if PPUA_START <= cp <= PPUA_END:
                    table[str(gid)] = cp
            next_cp = max(int(data.get("next_cp", PPUA_START)), PPUA_START)
        except Exception:
            pass
    if table:
        next_cp = max(next_cp, max(table.values()) + 1)
    return table, next_cp


def export_language_font(
    glyph_rows: List[Dict],
    output_dir: str,
    family: str = FONT_FAMILY,
) -> FontExportResult:
    os.makedirs(output_dir, exist_ok=True)

    # 1) Stable codepoint per glyph ID (never per list position, never reused).
    table, next_cp = _load_codepoint_table(output_dir, family)
    current: Dict[str, int] = {}
    for row in glyph_rows:
        gid = str(row.get("id") or row.get("name") or "glyph")
        if gid not in table:
            if next_cp > PPUA_END:
                raise RuntimeError("Ran out of Private Use Area codepoints")
            table[gid] = next_cp
            next_cp += 1
        current[gid] = table[gid]

    # 2) Build the font. Internal glyph names come from the codepoint, so two
    #    glyphs that share a display name no longer overwrite each other.
    strokes_by_name: Dict[str, List[object]] = {}
    cp_by_name: Dict[str, int] = {}
    for row in glyph_rows:
        gid = str(row.get("id") or row.get("name") or "glyph")
        cp = current[gid]
        gname = f"uni{cp:04X}"
        strokes_by_name[gname] = _extract_strokes(row.get("svg_data", ""))
        cp_by_name[gname] = cp

    ttf_path = os.path.join(output_dir, f"{family}.ttf")
    build_font_from_strokes(strokes_by_name, ttf_path, family=family, codepoints=cp_by_name)

    mapping_path = os.path.join(output_dir, f"{family}.mapping.json")
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "family": family,
                "ttf": os.path.basename(ttf_path),
                "glyphs": current,
                "next_cp": next_cp,
                "notes": "codepoints are in Unicode Private Use Area U+E000+ and are "
                         "STABLE per glyph id (never reassigned)",
            },
            f,
            indent=2,
        )

    return FontExportResult(
        ttf_path=ttf_path,
        mapping_path=mapping_path,
        family_name=family,
        num_glyphs=len(current),
        mapping=dict(current),
    )


# Font registry (Qt font loading, glyph lookup)

def get_fonts_dir(data_dir: str) -> str:
    d = os.path.join(data_dir, FONTS_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


_REGISTERED_BY_DIGEST: Dict[str, str] = {}   # content hash -> unique family
_ACTIVE_FAMILY: Optional[str] = None


def _register_ttf_unique(path: str) -> Optional[str]:
    """Register a TTF under a content-unique family name.

    Qt/fontconfig keeps the FIRST font it ever saw for a family name and
    ignores later files with the same name. Re-exporting the font during a
    session therefore left the UI drawing the OLD outlines while the keyboard
    mapping already pointed at the NEW codepoints (= consistent wrong glyphs).
    Renaming the family per content hash makes every rebuild a new family.
    """
    from fontTools.ttLib import TTFont

    with open(path, "rb") as f:
        raw = f.read()
    digest = hashlib.sha1(raw).hexdigest()[:10]
    if digest in _REGISTERED_BY_DIGEST:
        return _REGISTERED_BY_DIGEST[digest]

    family = f"{FONT_FAMILY}_{digest}"
    font = TTFont(io.BytesIO(raw))
    for rec in font["name"].names:
        if rec.nameID in (1, 4, 16):
            rec.string = family
        elif rec.nameID == 6:
            rec.string = family
    buf = io.BytesIO()
    font.save(buf)

    fid = QFontDatabase.addApplicationFontFromData(QByteArray(buf.getvalue()))
    if fid < 0:
        return None
    families = QFontDatabase.applicationFontFamilies(fid)
    if not families:
        return None
    _REGISTERED_BY_DIGEST[digest] = families[0]
    return families[0]


def register_language_font(data_dir: str) -> Optional[str]:
    global _ACTIVE_FAMILY
    fonts_dir = get_fonts_dir(data_dir)
    if not os.path.isdir(fonts_dir):
        return _ACTIVE_FAMILY

    preferred = os.path.join(fonts_dir, f"{FONT_FAMILY}.ttf")
    candidates = [preferred] if os.path.exists(preferred) else []
    candidates += [
        os.path.join(fonts_dir, f)
        for f in sorted(os.listdir(fonts_dir))
        if f.lower().endswith((".ttf", ".otf"))
        and os.path.join(fonts_dir, f) not in candidates
    ]
    for path in candidates:
        try:
            fam = _register_ttf_unique(path)
        except Exception:
            fam = None
        if fam:
            if fam != _ACTIVE_FAMILY:
                _ACTIVE_FAMILY = fam
                _refresh_tracked()      # every page's fields/tables pick up the new build
            return fam
    return _ACTIVE_FAMILY


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


def active_conlang_family() -> str:
    return _ACTIVE_FAMILY or FONT_FAMILY


def conlang_font(family: Optional[str] = None, point_size: int = 11) -> QFont:
    """Mixed font: conlang family first, normal UI font as per-character fallback.

    The conlang TTF only contains the PPUA codepoints, so Latin/IPA/umlaut
    characters fall through to the system font instead of rendering blank,
    and PPUA characters can never fall through to a random system font.
    """
    fam = family or active_conlang_family()
    ui_family = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()
    font = QFont(fam, point_size)
    font.setFamilies([fam, ui_family])
    return font


def has_ppua(text: str) -> bool:
    return any(PPUA_START <= ord(c) <= PPUA_END for c in text or "")


# Live registry: widgets/views that must follow the CURRENT font build

_TRACKED_WIDGETS: List[Tuple["weakref.ref", int]] = []
_TRACKED_VIEWS: List["weakref.ref"] = []
_TRACKED_LABELS: List["weakref.ref"] = []


def _refresh_tracked() -> None:
    alive = []
    for ref, size in _TRACKED_WIDGETS:
        w = ref()
        if w is None:
            continue
        try:
            w.setFont(conlang_font(point_size=size))
            alive.append((ref, size))
        except RuntimeError:        # underlying C++ object already deleted
            pass
    _TRACKED_WIDGETS[:] = alive

    alive_labels = []
    for ref in _TRACKED_LABELS:
        lb = ref()
        if lb is None:
            continue
        try:
            lb._cl_refresh()
            alive_labels.append(ref)
        except RuntimeError:
            pass
    _TRACKED_LABELS[:] = alive_labels

    alive_views = []
    for ref in _TRACKED_VIEWS:
        v = ref()
        if v is None:
            continue
        try:
            v.viewport().update()
            alive_views.append(ref)
        except RuntimeError:
            pass
    _TRACKED_VIEWS[:] = alive_views


_GUARD_EVENTS = (
    QEvent.Type.FontChange, QEvent.Type.StyleChange, QEvent.Type.ParentChange,
    QEvent.Type.Polish, QEvent.Type.Show,
)


class _ConlangFontGuard(QObject):
    """Re-applies the conlang font whenever Qt/QSS resets it.

    With an application stylesheet loaded, Qt re-resolves widget fonts when a
    widget is polished or reparented (e.g. `QScrollArea.setWidget(...)`), and for
    editable QComboBox that silently throws away the font set earlier with
    setFont(). A one-time setFont() can therefore never be enough; the guard
    checks on those events and puts the conlang font back.
    """

    def __init__(self, widget, point_size: int):
        super().__init__(widget)
        self.point_size = point_size
        self._busy = False
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if not self._busy and event.type() in _GUARD_EVENTS:
            want = active_conlang_family()
            if obj.font().families()[:1] != [want]:
                self._busy = True
                try:
                    obj.setFont(conlang_font(point_size=self.point_size))
                finally:
                    self._busy = False
        return False


def track_conlang_widget(widget, point_size: int = 12) -> None:
    """Give a field the conlang font AND keep it: across font rebuilds and QSS resets."""
    widget.setFont(conlang_font(point_size=point_size))
    guard = widget.findChild(_ConlangFontGuard, "", Qt.FindChildOption.FindDirectChildrenOnly)
    if guard is None:
        _ConlangFontGuard(widget, point_size)
    else:
        guard.point_size = point_size
    for i, (ref, _) in enumerate(_TRACKED_WIDGETS):
        if ref() is widget:
            _TRACKED_WIDGETS[i] = (ref, point_size)
            return
    _TRACKED_WIDGETS.append((weakref.ref(widget), point_size))


def apply_conlang_font(widget, data_dir: str, point_size: int = 11) -> None:
    if data_dir:
        register_language_font(data_dir)
    track_conlang_widget(widget, point_size)


def track_conlang_combo(combo: QComboBox, point_size: int = 12) -> None:
    """Editable (or not) combo whose edit box AND drop-down list use the conlang font."""
    track_conlang_widget(combo, point_size)
    if combo.lineEdit() is not None:
        track_conlang_widget(combo.lineEdit(), point_size)
    try:
        track_conlang_widget(combo.view(), point_size)
    except Exception:
        pass


def apply_conlang_to_fields(root, point_size: int = 12) -> None:
    """Apply the conlang font to every text input under `root` (dialog or page)."""
    for cls in (QLineEdit, QTextEdit, QPlainTextEdit):
        for w in root.findChildren(cls):
            if isinstance(w.parentWidget(), QAbstractSpinBox):
                continue
            track_conlang_widget(w, point_size)
    for combo in root.findChildren(QComboBox):
        if combo.isEditable():
            track_conlang_combo(combo, point_size)


class ConlangItemDelegate(QStyledItemDelegate):
    """Chooses the font PER CELL from its text, at paint time.

    Item-level setFont() was fragile: it only ran for some columns, was lost on
    re-population, and kept the family name from whenever the page was built.
    The delegate always reads the current family and works for every column,
    row and refresh, in tables and lists alike.
    """

    def __init__(self, parent=None, point_size: int = 16):
        super().__init__(parent)
        self._point_size = point_size

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if has_ppua(option.text):
            f = conlang_font(point_size=self._point_size)
            f.setBold(option.font.bold())
            option.font = f


def install_conlang_delegate(view, point_size: int = 16) -> None:
    """Install on a QTableWidget / QTableView / QListWidget."""
    view.setItemDelegate(ConlangItemDelegate(view, point_size))
    _TRACKED_VIEWS.append(weakref.ref(view))


class ConlangLabel(QLabel):
    """QLabel for DISPLAYING user-entered text (titles, names, descriptions).

    If the text contains conlang glyph characters the label uses the conlang
    font (UI font as per-character fallback); otherwise it keeps its normal
    font. Only the font FAMILY is touched, so stylesheet size/weight rules
    (font-size, font-weight, ...) keep working. Text can change at any time
    via setText() and the font follows; it also follows font rebuilds.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        f = self.font()
        self._cl_base = list(f.families()) or [f.family()]
        self._cl_applied = False
        self._cl_busy = False
        _TRACKED_LABELS.append(weakref.ref(self))
        if text:
            self.setText(text)

    def setText(self, text) -> None:
        super().setText(text)
        self._cl_refresh()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange,
                            QEvent.Type.ParentChange) and not self._cl_busy:
            self._cl_busy = True
            try:
                self._cl_refresh()
            finally:
                self._cl_busy = False

    def _cl_refresh(self) -> None:
        ppua = has_ppua(self.text())
        if not ppua and not self._cl_applied:
            return                      # ordinary text: leave the font alone (keeps inheritance)
        f = self.font()
        if ppua:
            fam = active_conlang_family()
            f.setFamilies([fam] + self._cl_base)
            self._cl_applied = True
        else:
            f.setFamilies(self._cl_base)
            self._cl_applied = False
        self.setFont(f)
