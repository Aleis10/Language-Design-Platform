from typing import Any, Callable, Dict, Optional, Tuple

# How the language font looks, as settings the user can change (the Typeface window).
# Plain Python only (no Qt, no fontTools), so the rules can be tested on their own.
#
#   scale         size of each glyph inside its slot, in percent (the slot itself stays the same)
#   thickness     stroke thickness, in percent (round, square and tip strokes; imported SVG outlines cannot be thickened)
#   glyph_gap     extra room between typed glyphs, in font units (1000 = the full slot); negative = tighter
#   space_enabled use space_width for the space bar (otherwise spaces come from the normal text font)
#   space_width   width of a space, in font units

DEFAULT_STYLE: Dict[str, Any] = {
    "scale": 100.0,
    "thickness": 100.0,
    "glyph_gap": 0.0,
    "space_enabled": False,
    "space_width": 500.0,
}

RANGES: Dict[str, Tuple[float, float]] = {
    "scale": (30.0, 200.0),
    "thickness": (30.0, 300.0),
    "glyph_gap": (-300.0, 600.0),
    "space_width": (0.0, 1500.0),
}

MAX_ADVANCE = 65535


def normalize_style(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    # always a complete, in-range style, whatever was stored or passed in
    style = dict(DEFAULT_STYLE)
    if isinstance(data, dict):
        for key, (low, high) in RANGES.items():
            if key in data:
                try:
                    style[key] = max(low, min(high, float(data[key])))
                except (TypeError, ValueError):
                    pass
        if "space_enabled" in data:
            style["space_enabled"] = bool(data["space_enabled"])
    return style


def is_default(style: Optional[Dict[str, Any]]) -> bool:
    return normalize_style(style) == DEFAULT_STYLE


def thickness_factor(style: Dict[str, Any]) -> float:
    return normalize_style(style)["thickness"] / 100.0


def advance_width(style: Dict[str, Any], units_per_em: int = 1000) -> int:
    # every glyph has the same slot: the full em plus the gap
    return max(0, min(MAX_ADVANCE, int(round(units_per_em + normalize_style(style)["glyph_gap"]))))


def space_advance(style: Dict[str, Any]) -> Optional[int]:
    s = normalize_style(style)
    return int(round(s["space_width"])) if s["space_enabled"] else None


def make_point_transform(style: Dict[str, Any], units_per_em: int = 1000) -> Callable[[float, float], Tuple[float, float]]:
    # for a point in font units: scale about the middle of the slot, then move right by half the gap
    # so the glyph stays in the middle of its (wider or narrower) slot
    s = normalize_style(style)
    factor = s["scale"] / 100.0
    center = units_per_em / 2.0
    shift = s["glyph_gap"] / 2.0

    def transform(x: float, y: float) -> Tuple[float, float]:
        return ((x - center) * factor + center + shift, (y - center) * factor + center)

    return transform
