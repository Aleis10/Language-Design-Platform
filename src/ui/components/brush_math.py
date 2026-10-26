import math
from typing import List, Sequence, Tuple

# Brush shapes for the glyph canvas. No Qt in here, so it can be tested on its own.
#
# A "round" stroke is drawn by Qt with a round pen. The "square" and "tip" brushes are different: a
# nib (a square, or a circle that changes size) is dragged along the stroke, and the area it covers is
# the stroke. Between two neighbouring positions of the nib that area is the convex hull of the two nib
# shapes, so a stroke is a list of small convex polygons. Drawn with the winding fill rule they merge
# into one shape, and the font builder can use them as they are.

Point = Tuple[float, float]
Polygon = List[Point]

BRUSHES = ("round", "square", "tip")
BRUSH_LABELS = {"round": "Round", "square": "Square", "tip": "Tip"}

# the "tip" brush: a little thinner where the stroke starts, full width in the middle,
# then it thins out to a point at the end like a brush being lifted
TIP_START_FACTOR = 0.65      # width at the very start, as a share of the full width
TIP_ENTRY_END = 0.12         # the start reaches full width after this share of the stroke
TIP_TAPER_START = 0.50       # the end starts thinning after this share of the stroke
TIP_END_FACTOR = 0.10        # width at the very end, as a share of the full width
CIRCLE_SIDES = 14
MAX_NIB_POSITIONS = 400


def signed_area(poly: Sequence[Point]) -> float:
    total = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        total += x0 * y1 - x1 * y0
    return total / 2.0


def convex_hull(points: Sequence[Point]) -> Polygon:
    # Andrew's monotone chain; the result always has a positive signed area
    pts = sorted(set((round(x, 6), round(y, 6)) for x, y in points))
    if len(pts) <= 2:
        return list(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: Polygon = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: Polygon = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def path_length(points: Sequence[Point]) -> float:
    return sum(math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
               for i in range(len(points) - 1))


def resample(points: Sequence[Point], spacing: float) -> List[Point]:
    # points spaced evenly along the path (first and last point are kept)
    pts = list(points)
    if len(pts) < 2:
        return pts
    total = path_length(pts)
    if total <= 0:
        return [pts[0]]
    count = max(1, int(math.ceil(total / max(0.5, spacing))))
    count = min(count, MAX_NIB_POSITIONS)
    step = total / count
    out: List[Point] = [pts[0]]
    walked, target, i = 0.0, step, 0
    while len(out) < count and i < len(pts) - 1:
        seg = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        if seg > 0 and walked + seg >= target:
            t = (target - walked) / seg
            out.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t))
            target += step
        else:
            walked += seg
            i += 1
    out.append(pts[-1])
    return out


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def tip_factor(share: float) -> float:
    # width factor at `share` (0 start .. 1 end) of the way along the stroke
    if share < TIP_ENTRY_END:
        return TIP_START_FACTOR + (1.0 - TIP_START_FACTOR) * _smoothstep(share / TIP_ENTRY_END)
    if share <= TIP_TAPER_START:
        return 1.0
    return 1.0 - (1.0 - TIP_END_FACTOR) * _smoothstep((share - TIP_TAPER_START) / (1.0 - TIP_TAPER_START))


def circle_nib(cx: float, cy: float, radius: float, sides: int = CIRCLE_SIDES) -> Polygon:
    return [(cx + radius * math.cos(2 * math.pi * k / sides), cy + radius * math.sin(2 * math.pi * k / sides))
            for k in range(sides)]


def square_nib(cx: float, cy: float, half: float, degrees: float = 0.0) -> Polygon:
    # a square of side 2 * half, turned by `degrees` (clockwise on screen, y points down)
    rad = math.radians(degrees)
    c, s = math.cos(rad), math.sin(rad)
    corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
    return [(cx + x * c - y * s, cy + x * s + y * c) for x, y in corners]


def brush_polygons(centerline: Sequence[Point], width: float, brush: str, angle: float = 0.0) -> List[Polygon]:
    # the polygons that make up a "square" or "tip" stroke (empty for "round")
    if brush not in ("square", "tip") or not centerline:
        return []
    width = max(0.5, float(width))
    pts = resample(centerline, max(1.0, width * 0.35))
    n = len(pts)

    nibs: List[Polygon] = []
    for i, (x, y) in enumerate(pts):
        if brush == "square":
            nibs.append(square_nib(x, y, width / 2.0, angle))
        else:
            share = i / (n - 1) if n > 1 else 0.0
            nibs.append(circle_nib(x, y, max(0.25, width / 2.0 * tip_factor(share))))

    if n == 1:
        return [convex_hull(nibs[0])]
    polys: List[Polygon] = []
    for i in range(n - 1):
        hull = convex_hull(nibs[i] + nibs[i + 1])
        if len(hull) >= 3:
            polys.append(hull)
    return polys


def polygons_to_svg_path(polys: Sequence[Sequence[Point]]) -> str:
    parts = []
    for poly in polys:
        if len(poly) < 3:
            continue
        parts.append(f"M {poly[0][0]:.1f} {poly[0][1]:.1f} " +
                     " ".join(f"L {x:.1f} {y:.1f}" for x, y in poly[1:]) + " Z")
    return " ".join(parts)


def point_in_polygon(p: Point, poly: Sequence[Point]) -> bool:
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def covered(p: Point, polys: Sequence[Sequence[Point]]) -> bool:
    return any(point_in_polygon(p, poly) for poly in polys)
