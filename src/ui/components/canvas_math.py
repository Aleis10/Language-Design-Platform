import math
from typing import Iterable, List, Optional, Sequence, Tuple

# Plain geometry for the glyph canvas. Points are (x, y) tuples in canvas coordinates (y points down).
# No Qt in here, so all of it can be tested on its own.

Point = Tuple[float, float]
Bounds = Tuple[float, float, float, float]   # x0, y0, x1, y1


def dist_point_to_segment(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length_sq))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def dist_point_to_polyline(p: Point, points: Sequence[Point]) -> float:
    if not points:
        return math.inf
    if len(points) == 1:
        return math.hypot(p[0] - points[0][0], p[1] - points[0][1])
    return min(dist_point_to_segment(p, points[i], points[i + 1]) for i in range(len(points) - 1))


def stroke_hit(points: Sequence[Point], width: float, center: Point, radius: float) -> bool:
    # a round eraser of `radius` at `center` touches a stroke of `width` drawn along `points`
    return dist_point_to_polyline(center, points) <= width / 2.0 + radius


def rotate_points(points: Iterable[Point], pivot: Point, degrees: float) -> List[Point]:
    # positive degrees turn clockwise on screen (y points down)
    rad = math.radians(degrees)
    c, s = math.cos(rad), math.sin(rad)
    px, py = pivot
    return [(px + (x - px) * c - (y - py) * s, py + (x - px) * s + (y - py) * c) for x, y in points]


def scale_points(points: Iterable[Point], pivot: Point, factor: float) -> List[Point]:
    px, py = pivot
    return [(px + (x - px) * factor, py + (y - py) * factor) for x, y in points]


def translate_points(points: Iterable[Point], dx: float, dy: float) -> List[Point]:
    return [(x + dx, y + dy) for x, y in points]


def union_bounds(parts: Iterable[Tuple[Sequence[Point], float]]) -> Optional[Bounds]:
    # parts: (points, extra padding), padding is half the stroke width so the ink is included
    x0 = y0 = math.inf
    x1 = y1 = -math.inf
    found = False
    for points, pad in parts:
        for x, y in points:
            found = True
            x0, y0 = min(x0, x - pad), min(y0, y - pad)
            x1, y1 = max(x1, x + pad), max(y1, y + pad)
    return (x0, y0, x1, y1) if found else None


def bounds_center(b: Bounds) -> Point:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def angle_delta(pivot: Point, start: Point, current: Point) -> float:
    # how far the mouse has turned around the pivot, in degrees, normalised to [-180, 180)
    a0 = math.atan2(start[1] - pivot[1], start[0] - pivot[0])
    a1 = math.atan2(current[1] - pivot[1], current[0] - pivot[0])
    deg = math.degrees(a1 - a0)
    return (deg + 180.0) % 360.0 - 180.0


def snap_value(value: float, step: float) -> float:
    return round(value / step) * step if step else value


def snap_angle(origin: Point, point: Point, step_deg: float = 15.0) -> Point:
    # keep the distance, round the direction to a multiple of step_deg
    dx, dy = point[0] - origin[0], point[1] - origin[1]
    r = math.hypot(dx, dy)
    if r == 0:
        return point
    ang = math.radians(snap_value(math.degrees(math.atan2(dy, dx)), step_deg))
    return (origin[0] + r * math.cos(ang), origin[1] + r * math.sin(ang))


def scale_ratio(pivot: Point, start: Point, current: Point,
                minimum: float = 0.05, maximum: float = 20.0) -> float:
    d0 = math.hypot(start[0] - pivot[0], start[1] - pivot[1])
    d1 = math.hypot(current[0] - pivot[0], current[1] - pivot[1])
    if d0 < 1.0:                     # the mouse started on the pivot: use one pixel as the base
        d0 = 1.0
    return max(minimum, min(maximum, d1 / d0))


def center_offset(b: Bounds, box_size: float) -> Point:
    cx, cy = bounds_center(b)
    return (box_size / 2.0 - cx, box_size / 2.0 - cy)


def fit_transform(b: Bounds, box_size: float, margin: float) -> Tuple[float, Point]:
    # scale about the middle of the bounds so the biggest side fills the box minus the margins,
    # then move the middle to the middle of the box. Returns (factor, (dx, dy)) to apply in that order.
    w, h = b[2] - b[0], b[3] - b[1]
    biggest = max(w, h)
    available = max(1.0, box_size - 2.0 * margin)
    factor = available / biggest if biggest > 0 else 1.0
    return factor, center_offset(b, box_size)


def parse_number(text: str) -> Optional[float]:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def flow_positions(sizes: Sequence[Tuple[float, float]], width: float,
                   h_spacing: float, v_spacing: float) -> Tuple[List[Point], float]:
    # wrap items left to right, starting a new row when the next one would not fit.
    # Returns the top left corner of every item and the total height used.
    positions: List[Point] = []
    x = y = 0.0
    row_height = 0.0
    for w, h in sizes:
        if x > 0 and x + w > width:
            x = 0.0
            y += row_height + v_spacing
            row_height = 0.0
        positions.append((x, y))
        x += w + h_spacing
        row_height = max(row_height, h)
    total = y + row_height if sizes else 0.0
    return positions, total
