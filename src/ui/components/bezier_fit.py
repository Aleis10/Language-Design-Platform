import math
from typing import List, Optional, Sequence, Tuple

# Piecewise cubic Bezier fitting for hand drawn strokes.
#
# This is a Python port of FitCurves.c, the code that goes with
#   "An Algorithm for Automatically Fitting Digitized Curves"
#   by Philip J. Schneider, from "Graphics Gems", Academic Press, 1990.
# Original C code: https://github.com/erich666/GraphicsGems (gems/FitCurves.c)
# The Graphics Gems code may be used in any program, product or library, commercial or not; crediting
# the author is appreciated, so this header must stay. The code comes as is, without any guarantee.
#
# Changes from the C code: plain Python tuples (no numpy), duplicate points are removed first,
# zero length tangents are guarded, and a failure returns an empty list instead of crashing.

Point = Tuple[float, float]
Curve = Tuple[Point, Point, Point, Point]


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _scale(a: Point, s: float) -> Point:
    return (a[0] * s, a[1] * s)


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _length(a: Point) -> float:
    return math.hypot(a[0], a[1])


def _normalize(a: Point) -> Point:
    n = _length(a)
    if n < 1e-12:
        return (0.0, 0.0)
    return (a[0] / n, a[1] / n)


# Bezier multipliers (B0 .. B3 in the C code)
def _b0(u: float) -> float:
    t = 1.0 - u
    return t * t * t


def _b1(u: float) -> float:
    t = 1.0 - u
    return 3 * u * (t * t)


def _b2(u: float) -> float:
    t = 1.0 - u
    return 3 * u * u * t


def _b3(u: float) -> float:
    return u * u * u


def bezier_point(degree: int, v: Sequence[Point], t: float) -> Point:
    # evaluate a Bezier curve of any degree with the triangle computation (BezierII in the C code)
    tmp = [p for p in v[: degree + 1]]
    for i in range(1, degree + 1):
        for j in range(degree - i + 1):
            tmp[j] = ((1.0 - t) * tmp[j][0] + t * tmp[j + 1][0], (1.0 - t) * tmp[j][1] + t * tmp[j + 1][1])
    return tmp[0]


def _compute_left_tangent(d: Sequence[Point], end: int) -> Point:
    return _normalize(_sub(d[end + 1], d[end]))


def _compute_right_tangent(d: Sequence[Point], end: int) -> Point:
    return _normalize(_sub(d[end - 1], d[end]))


def _compute_center_tangent(d: Sequence[Point], center: int) -> Point:
    v1 = _sub(d[center - 1], d[center])
    v2 = _sub(d[center], d[center + 1])
    t = _normalize(((v1[0] + v2[0]) / 2.0, (v1[1] + v2[1]) / 2.0))
    if t == (0.0, 0.0):                    # a cusp: the two directions cancel out
        t = _normalize(v1)
    return t


def _chord_length_parameterize(d: Sequence[Point], first: int, last: int) -> List[float]:
    u = [0.0]
    for i in range(first + 1, last + 1):
        u.append(u[i - first - 1] + _length(_sub(d[i], d[i - 1])))
    total = u[last - first]
    if total <= 0.0:
        return [i / max(1, last - first) for i in range(last - first + 1)]
    return [x / total for x in u]


def _generate_bezier(d: Sequence[Point], first: int, last: int, u_prime: Sequence[float],
                     t_hat1: Point, t_hat2: Point) -> Curve:
    # least squares fit of the two inner control points
    n_pts = last - first + 1
    a = []
    for i in range(n_pts):
        a.append((_scale(t_hat1, _b1(u_prime[i])), _scale(t_hat2, _b2(u_prime[i]))))

    c = [[0.0, 0.0], [0.0, 0.0]]
    x = [0.0, 0.0]
    for i in range(n_pts):
        c[0][0] += _dot(a[i][0], a[i][0])
        c[0][1] += _dot(a[i][0], a[i][1])
        c[1][0] = c[0][1]
        c[1][1] += _dot(a[i][1], a[i][1])
        tmp = _sub(d[first + i], _add(
            _scale(d[first], _b0(u_prime[i])),
            _add(_scale(d[first], _b1(u_prime[i])),
                 _add(_scale(d[last], _b2(u_prime[i])), _scale(d[last], _b3(u_prime[i]))))))
        x[0] += _dot(a[i][0], tmp)
        x[1] += _dot(a[i][1], tmp)

    det_c0_c1 = c[0][0] * c[1][1] - c[1][0] * c[0][1]
    det_c0_x = c[0][0] * x[1] - c[1][0] * x[0]
    det_x_c1 = x[0] * c[1][1] - x[1] * c[0][1]
    alpha_l = 0.0 if det_c0_c1 == 0 else det_x_c1 / det_c0_c1
    alpha_r = 0.0 if det_c0_c1 == 0 else det_c0_x / det_c0_c1

    # if alpha is negative or tiny, use the Wu/Barsky heuristic (a third of the distance)
    seg_length = _length(_sub(d[last], d[first]))
    epsilon = 1.0e-6 * seg_length
    if alpha_l < epsilon or alpha_r < epsilon:
        dist = seg_length / 3.0
        return (d[first], _add(d[first], _scale(t_hat1, dist)), _add(d[last], _scale(t_hat2, dist)), d[last])

    return (d[first], _add(d[first], _scale(t_hat1, alpha_l)), _add(d[last], _scale(t_hat2, alpha_r)), d[last])


def _newton_raphson_root_find(q: Curve, p: Point, u: float) -> float:
    # one Newton-Raphson step towards a better parameter for the point p
    q_u = bezier_point(3, q, u)
    q1 = [_scale(_sub(q[i + 1], q[i]), 3.0) for i in range(3)]
    q2 = [_scale(_sub(q1[i + 1], q1[i]), 2.0) for i in range(2)]
    q1_u = bezier_point(2, q1, u)
    q2_u = bezier_point(1, q2, u)
    numerator = (q_u[0] - p[0]) * q1_u[0] + (q_u[1] - p[1]) * q1_u[1]
    denominator = (q1_u[0] * q1_u[0] + q1_u[1] * q1_u[1]
                   + (q_u[0] - p[0]) * q2_u[0] + (q_u[1] - p[1]) * q2_u[1])
    if denominator == 0.0:
        return u
    return u - numerator / denominator


def _reparameterize(d: Sequence[Point], first: int, last: int, u: Sequence[float], bez: Curve) -> List[float]:
    return [_newton_raphson_root_find(bez, d[i], u[i - first]) for i in range(first, last + 1)]


def _compute_max_error(d: Sequence[Point], first: int, last: int, bez: Curve,
                       u: Sequence[float]) -> Tuple[float, int]:
    # largest squared distance from the points to the curve, and the index where it happens
    split_point = (last - first + 1) // 2
    max_dist = 0.0
    for i in range(first + 1, last):
        p = bezier_point(3, bez, u[i - first])
        v = _sub(p, d[i])
        dist = v[0] * v[0] + v[1] * v[1]
        if dist >= max_dist:
            max_dist = dist
            split_point = i
    return max_dist, split_point


def _fit_cubic(d: Sequence[Point], first: int, last: int, t_hat1: Point, t_hat2: Point,
               error: float, out: List[Curve]) -> None:
    max_iterations = 4
    iteration_error = error * 4.0
    n_pts = last - first + 1

    # use a heuristic if the region only has two points in it
    if n_pts == 2:
        dist = _length(_sub(d[last], d[first])) / 3.0
        out.append((d[first], _add(d[first], _scale(t_hat1, dist)),
                    _add(d[last], _scale(t_hat2, dist)), d[last]))
        return

    # parameterize the points and try to fit one curve
    u = _chord_length_parameterize(d, first, last)
    bez = _generate_bezier(d, first, last, u, t_hat1, t_hat2)
    max_error, split_point = _compute_max_error(d, first, last, bez, u)
    if max_error < error:
        out.append(bez)
        return

    # if the error is not too large, try some reparameterization and iteration
    if max_error < iteration_error:
        for _ in range(max_iterations):
            u_prime = _reparameterize(d, first, last, u, bez)
            bez = _generate_bezier(d, first, last, u_prime, t_hat1, t_hat2)
            max_error, split_point = _compute_max_error(d, first, last, bez, u_prime)
            if max_error < error:
                out.append(bez)
                return
            u = u_prime

    # fitting failed: split at the point of maximum error and fit both halves
    t_center = _compute_center_tangent(d, split_point)
    _fit_cubic(d, first, split_point, t_hat1, t_center, error, out)
    t_center = (-t_center[0], -t_center[1])
    _fit_cubic(d, split_point, last, t_center, t_hat2, error, out)


def _remove_duplicates(points: Sequence[Point]) -> List[Point]:
    out: List[Point] = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) > 1e-9 or abs(p[1] - out[-1][1]) > 1e-9:
            out.append((float(p[0]), float(p[1])))
    return out


def fit_curve(points: Sequence[Point], error: float) -> List[Curve]:
    # error is the largest allowed squared distance between a point and the fitted curve
    d = _remove_duplicates(points)
    if len(d) < 2:
        return []
    try:
        t_hat1 = _compute_left_tangent(d, 0)
        t_hat2 = _compute_right_tangent(d, len(d) - 1)
        out: List[Curve] = []
        _fit_cubic(d, 0, len(d) - 1, t_hat1, t_hat2, max(1e-6, error), out)
        return out
    except (RecursionError, ZeroDivisionError, ValueError):
        return []


def curves_to_chain(curves: Sequence[Curve]) -> List[Point]:
    # [p0, c1, c2, p1, c1, c2, p2 ...]: the end of one curve is the start of the next
    if not curves:
        return []
    chain: List[Point] = [curves[0][0]]
    for _p0, c1, c2, p3 in curves:
        chain.extend([c1, c2, p3])
    return chain


def chain_to_polyline(chain: Sequence[Point], steps_per_curve: int = 12) -> List[Point]:
    # points along a chain of cubic curves (3 * n + 1 points)
    if len(chain) < 4:
        return list(chain)
    out: List[Point] = [chain[0]]
    for i in range(0, len(chain) - 3, 3):
        seg = chain[i:i + 4]
        for s in range(1, steps_per_curve + 1):
            out.append(bezier_point(3, seg, s / steps_per_curve))
    return out


def fit_chain(points: Sequence[Point], tolerance: float) -> Optional[List[Point]]:
    # the one call the canvas needs: points in, a chain of cubic control points out (None when not possible)
    if tolerance <= 0 or len(_remove_duplicates(points)) < 3:
        return None
    curves = fit_curve(points, tolerance * tolerance)
    return curves_to_chain(curves) if curves else None
