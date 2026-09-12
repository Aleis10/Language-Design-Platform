import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PySide6.QtGui import QPainterPath, QPolygonF
from PySide6.QtCore import QPointF

from ui.components.glyph_canvas import VectorStroke
from font_tools.font_builder import (
    build_font_from_strokes,
    FilledContour,
    _sanitize_glyph_name,
    FONT_FAMILY,
)

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