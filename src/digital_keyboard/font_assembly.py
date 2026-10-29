import math
from typing import Dict, List, Optional

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

# The last step of building the language font: glyph outlines in, a .ttf file out.
# Needs fontTools only (no Qt), so it can be tested with a real font renderer.


def glyph_left_bearing(glyph) -> int:
    # the left side bearing has to equal the glyph's left edge. If it is wrong (for example 0) the font
    # renderer moves every glyph to the left edge of its slot, whatever was drawn.
    coords = getattr(glyph, "coordinates", None)
    if coords is None or len(coords) == 0:
        return 0
    try:
        return int(coords.calcIntBounds()[0])
    except Exception:
        return int(math.floor(min(x for x, _y in coords)))


def assemble_ttf(
    pen_map: Dict[str, TTGlyphPen],
    glyph_order: List[str],
    cmapping: Dict[int, str],
    advances: Dict[str, int],
    units_per_em: int,
    family: str,
    ps_name: str,
    output_path: str,
    space_advance: Optional[int] = None,
) -> None:
    glyphs_obj = {name: pen.glyph() for name, pen in pen_map.items()}
    glyphs_obj[".notdef"] = TTGlyphPen(None).glyph()

    order = list(glyph_order)
    cmap = dict(cmapping)
    adv = dict(advances)
    if space_advance is not None:
        # a real space glyph, so the width of a space is chosen instead of borrowed from another font
        order.append("space")
        cmap[0x20] = "space"
        glyphs_obj["space"] = TTGlyphPen(None).glyph()
        adv["space"] = int(space_advance)

    metrics = {name: (adv.get(name, units_per_em), glyph_left_bearing(glyphs_obj[name])) for name in order}

    fb = FontBuilder(units_per_em)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs_obj)
    fb.setupHorizontalMetrics(metrics)

    ascent = int(units_per_em * 0.8)
    descent = -int(units_per_em * 0.2)
    fb.setupHorizontalHeader(ascent=ascent, descent=descent, lineGap=0)
    fb.setupNameTable(
        {
            "familyName": family,
            "styleName": "Regular",
            "uniqueFontIdentifier": f"{family}: 1.0",
            "fullName": family,
            "psName": ps_name,
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
    fb.setupHead(created=0, unitsPerEm=units_per_em, macStyle=0, lowestRecPPEM=6)

    fb.font["OS/2"].sTypoDescender = -int(units_per_em * 0.25)
    fb.save(output_path)
