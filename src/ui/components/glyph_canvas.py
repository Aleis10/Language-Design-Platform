import json
import math
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider,
    QLabel, QToolButton, QButtonGroup, QFrame, QFileDialog, QMessageBox,
    QGraphicsView, QGraphicsScene, QGraphicsPathItem, QGraphicsItem,
    QDoubleSpinBox, QCheckBox, QApplication, QComboBox
)
from PySide6.QtCore import Qt, QPointF, Signal, QRectF, QSize
from PySide6.QtGui import (
    QPainter, QPen, QColor, QPainterPath, QPaintEvent, QKeyEvent, QCursor,
    QMouseEvent, QPixmap, QBrush, QTransform, QFont
)
from PySide6.QtSvg import QSvgRenderer

from .bezier_fit import fit_chain, chain_to_polyline
from .brush_math import BRUSHES, BRUSH_LABELS, brush_polygons, polygons_to_svg_path
from .flow_layout import FlowLayout
from .tool_icons import asset_icon
from .canvas_math import (
    stroke_hit, rotate_points, scale_points, translate_points, union_bounds, bounds_center,
    angle_delta, snap_value, snap_angle, scale_ratio, center_offset, fit_transform, parse_number,
)


class VectorStroke:
    # points are the drawn points, or, when `bezier` is true, the control points of a chain of cubic
    # curves (3 * n + 1 points). `brush` is "round", "square" or "tip". `angle` turns the square nib.
    def __init__(self, points: Optional[List[QPointF]] = None, width: float = 6.0, color: str = "#111111",
                 is_eraser: bool = False, brush: str = "round", bezier: bool = False, angle: float = 0.0):
        self.points: List[QPointF] = points or []
        self.width: float = width
        self.color: str = color
        self.is_eraser: bool = is_eraser
        self.brush: str = brush if brush in BRUSHES else "round"
        self.bezier: bool = bool(bezier)
        self.angle: float = float(angle)

    @property
    def is_filled(self) -> bool:
        # square and tip strokes are filled shapes instead of a line with a pen width
        return (not self.is_eraser) and self.brush in ("square", "tip")

    def centerline_xy(self):
        pts = [(p.x(), p.y()) for p in self.points]
        if self.bezier and len(pts) >= 4:
            return chain_to_polyline(pts, 12)
        return pts

    def build_path(self) -> QPainterPath:
        path = QPainterPath()
        if not self.points:
            return path

        if len(self.points) == 1:
            pt = self.points[0]
            path.addEllipse(pt, self.width / 2.0, self.width / 2.0)
            return path

        if self.bezier and len(self.points) >= 4:
            path.moveTo(self.points[0])
            for i in range(1, len(self.points) - 2, 3):
                path.cubicTo(self.points[i], self.points[i + 1], self.points[i + 2])
            return path

        path.moveTo(self.points[0])
        for i in range(1, len(self.points) - 1):
            p0 = self.points[i]
            p1 = self.points[i + 1]
            mid = QPointF((p0.x() + p1.x()) / 2.0, (p0.y() + p1.y()) / 2.0)
            path.quadTo(p0, mid)

        path.lineTo(self.points[-1])
        return path

    def fill_polygons(self):
        return brush_polygons(self.centerline_xy(), self.width, self.brush, self.angle)

    def build_fill_path(self) -> QPainterPath:
        # the shape of a square or tip stroke: many small convex polygons that merge with the winding rule
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        for poly in self.fill_polygons():
            path.moveTo(QPointF(poly[0][0], poly[0][1]))
            for x, y in poly[1:]:
                path.lineTo(QPointF(x, y))
            path.closeSubpath()
        return path

    def to_svg_fill_data(self) -> str:
        return polygons_to_svg_path(self.fill_polygons())

    def to_svg_path_data(self) -> str:
        if not self.points:
            return ""
        if len(self.points) == 1:
            p = self.points[0]
            r = self.width / 2.0
            return f"M {p.x()-r} {p.y()} A {r} {r} 0 1 0 {p.x()+r} {p.y()} A {r} {r} 0 1 0 {p.x()-r} {p.y()}"

        if self.bezier and len(self.points) >= 4:
            d = [f"M {self.points[0].x():.1f} {self.points[0].y():.1f}"]
            for i in range(1, len(self.points) - 2, 3):
                c1, c2, e = self.points[i], self.points[i + 1], self.points[i + 2]
                d.append(f"C {c1.x():.1f} {c1.y():.1f} {c2.x():.1f} {c2.y():.1f} {e.x():.1f} {e.y():.1f}")
            return " ".join(d)

        d = [f"M {self.points[0].x():.1f} {self.points[0].y():.1f}"]
        for i in range(1, len(self.points) - 1):
            p0 = self.points[i]
            p1 = self.points[i + 1]
            mid_x = (p0.x() + p1.x()) / 2.0
            mid_y = (p0.y() + p1.y()) / 2.0
            d.append(f"Q {p0.x():.1f} {p0.y():.1f} {mid_x:.1f} {mid_y:.1f}")
        d.append(f"L {self.points[-1].x():.1f} {self.points[-1].y():.1f}")
        return " ".join(d)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "points": [[p.x(), p.y()] for p in self.points],
            "width": self.width,
            "color": self.color,
            "is_eraser": self.is_eraser,
            "brush": self.brush,
            "bezier": self.bezier,
            "angle": self.angle,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VectorStroke":
        pts = [QPointF(x, y) for x, y in data.get("points", [])]
        bezier = bool(data.get("bezier", False)) and len(pts) >= 4 and (len(pts) - 1) % 3 == 0
        return cls(
            points=pts,
            width=data.get("width", 6.0),
            color=data.get("color", "#111111"),
            is_eraser=data.get("is_eraser", False),
            brush=data.get("brush", "round"),
            bezier=bezier,
            angle=data.get("angle", 0.0),
        )


class StrokeGraphicsItem(QGraphicsPathItem):
    # One stroke on the canvas. The item never keeps a rotation or scale of its own: moving, rotating
    # and scaling are written straight into the stroke's points (and width), so what you see is what is saved.
    def __init__(self, stroke: VectorStroke):
        super().__init__()
        self.stroke = stroke
        self._update_from_stroke()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

    def _update_from_stroke(self):
        # Build path and set pen from VectorStroke data
        if self.stroke.is_filled:
            # square / tip brush: a filled shape, no outline pen
            self.setPath(self.stroke.build_fill_path())
            self.setPen(QPen(Qt.PenStyle.NoPen))
            self.setBrush(QBrush(QColor(self.stroke.color)))
            return

        self.setPath(self.stroke.build_path())
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        if self.stroke.is_eraser:
            pen = QPen(QColor("#ffffff"), self.stroke.width, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        else:
            pen = QPen(QColor(self.stroke.color), self.stroke.width, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

    def paint(self, painter, option, widget=None):
        # Same as the default path item but without Qt's own selection highlight, which draws two
        # outlines (a solid one and a dashed one). One dashed outline is drawn instead.
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawPath(self.path())
        if self.isSelected():
            painter.save()
            outline = QPen(QColor("#007acc"), 1.0, Qt.PenStyle.DashLine)
            outline.setCosmetic(True)
            painter.setPen(outline)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())
            painter.restore()

    def points_xy(self):
        # the stored points (control points for a curve): what moving, rotating and scaling act on
        return [(p.x(), p.y()) for p in self.stroke.points]

    def outline_xy(self):
        # points along the stroke itself (curves flattened): for bounds and hit tests
        return self.stroke.centerline_xy()

    def set_geometry(self, points_xy, width: float, angle: Optional[float] = None):
        self.stroke.points = [QPointF(x, y) for x, y in points_xy]
        self.stroke.width = max(0.5, float(width))
        if angle is not None:
            self.stroke.angle = float(angle)
        self._update_from_stroke()

    def set_chain(self, chain_xy):
        # replace the points by a chain of cubic curves
        self.stroke.points = [QPointF(x, y) for x, y in chain_xy]
        self.stroke.bezier = True
        self._update_from_stroke()

    def bake_position(self) -> bool:
        # after a drag: move the item's offset into the points and put the item back at 0,0
        pos = self.pos()
        if pos.x() == 0 and pos.y() == 0:
            return False
        self.stroke.points = [QPointF(p.x() + pos.x(), p.y() + pos.y()) for p in self.stroke.points]
        self.setPos(0, 0)
        self._update_from_stroke()
        return True

    def get_transformed_stroke(self) -> VectorStroke:
        # The stroke as it is now, in canvas coordinates. The width follows any scale still on the item.
        t = self.sceneTransform()
        factor = math.sqrt(abs(t.m11() * t.m22() - t.m12() * t.m21())) or 1.0
        new_points = [t.map(p) for p in self.stroke.points]
        return VectorStroke(new_points, self.stroke.width * factor, self.stroke.color, self.stroke.is_eraser,
                            self.stroke.brush, self.stroke.bezier, self.stroke.angle)


class GlyphCanvasWidget(QGraphicsView):
    content_changed = Signal()
    legacy_erasers_removed = Signal(int)   # old eraser strokes found while loading a glyph
    selection_changed = Signal()           # the set of selected strokes changed

    CANVAS_SIZE = 500  # Logical coordinate size (SVG viewBox reference)
    GUIDE_MARGIN = 40  # the "safe area" the Fit button leaves around the drawing

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create scene
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, self.CANVAS_SIZE, self.CANVAS_SIZE)
        self.setScene(self.scene)

        # View settings
        self.setMinimumSize(self.CANVAS_SIZE, self.CANVAS_SIZE)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)     # R / S / G / Delete need the keyboard
        self.setMouseTracking(True)                          # R / S / G follow the mouse without a button
        self.viewport().setMouseTracking(True)

        # Undo/redo: each entry is the whole list of strokes before a change
        self.undo_stack: List[List[VectorStroke]] = []
        self.redo_stack: List[List[VectorStroke]] = []

        # Drawing state
        self.current_tool = "pen"  # "pen", "line", "eraser", "select"
        self.pen_width = 6.0
        self.pen_color = "#111111"
        self.brush = "round"       # brush of new strokes: "round", "square", "tip"
        self.smoothing = 3.0       # curve fitting tolerance in pixels for new pen strokes (0 = off)
        self.show_guides = True
        self.current_stroke: Optional[VectorStroke] = None
        self.temp_drawing_item: Optional[StrokeGraphicsItem] = None
        self._next_z = 0                                     # stacking order = drawing order
        self._pending_snapshot: Optional[List[VectorStroke]] = None
        self._erasing = False
        self._erased_any = False
        self._erase_last: Optional[QPointF] = None
        self._modal: Optional[Dict[str, Any]] = None         # R / S / G in progress
        self._width_snapshot: Optional[List[VectorStroke]] = None   # thickness being dragged on a selection
        self._width_changed = False

        # External SVG renderer (for imported SVGs without metadata)
        self.external_svg_renderer: Optional[QSvgRenderer] = None

        self.setStyleSheet("background-color: #ffffff; border: 1px solid #dcdcdc; border-radius: 6px;")
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        self.set_tool("pen")

    def _on_scene_selection_changed(self):
        try:
            self.selection_changed.emit()
        except RuntimeError:
            pass    # the scene is being torn down

    # ---------------------------------------------------------------- items and undo
    def _add_stroke_item(self, stroke: VectorStroke) -> StrokeGraphicsItem:
        item = StrokeGraphicsItem(stroke)
        item.setZValue(self._next_z)
        self._next_z += 1
        self.scene.addItem(item)
        return item

    def _stroke_items(self) -> List[StrokeGraphicsItem]:
        # in drawing order, bottom first (scene.items() alone is top first)
        items = [i for i in self.scene.items() if isinstance(i, StrokeGraphicsItem)]
        items.sort(key=lambda i: i.zValue())
        return items

    def _selected_items(self) -> List[StrokeGraphicsItem]:
        return [i for i in self._stroke_items() if i.isSelected()]

    def _get_all_strokes(self) -> List[VectorStroke]:
        return [i.get_transformed_stroke() for i in self._stroke_items()]

    def _restore_strokes(self, strokes: List[VectorStroke]):
        self._modal = None
        self.temp_drawing_item = None
        self.current_stroke = None
        self.scene.clear()
        self._next_z = 0
        for stroke in strokes:
            self._add_stroke_item(stroke)

    def _push_snapshot(self, strokes: List[VectorStroke]):
        self.undo_stack.append(strokes)
        self.redo_stack.clear()
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def _push_undo(self):
        self._push_snapshot(self._get_all_strokes())

    def undo(self):
        self._cancel_modal()
        if not self.undo_stack:
            return
        self.redo_stack.append(self._get_all_strokes())
        self._restore_strokes(self.undo_stack.pop())
        self.content_changed.emit()

    def redo(self):
        self._cancel_modal()
        if not self.redo_stack:
            return
        self.undo_stack.append(self._get_all_strokes())
        self._restore_strokes(self.redo_stack.pop())
        self.content_changed.emit()

    def clear_canvas(self):
        self._cancel_modal()
        if not self.scene.items() and not self.external_svg_renderer:
            self.content_changed.emit()  # Shrinks canvas entire fill called real strokes
            return
        self._push_undo()
        self.temp_drawing_item = None
        self.current_stroke = None
        self.scene.clear()
        self._next_z = 0
        self.external_svg_renderer = None
        self.content_changed.emit()

    # ---------------------------------------------------------------- tools
    def set_tool(self, tool: str):
        self._cancel_modal()
        self.current_tool = tool
        if tool == "select":
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.viewport().update()

    def set_guides_visible(self, visible: bool):
        self.show_guides = bool(visible)
        self.viewport().update()

    def _scene_pos(self, event) -> QPointF:
        return self.mapToScene(event.position().toPoint())

    def _cursor_scene_pos(self) -> QPointF:
        return self.mapToScene(self.viewport().mapFromGlobal(QCursor.pos()))

    # ---------------------------------------------------------------- mouse
    def mousePressEvent(self, event: QMouseEvent):
        self.setFocus()
        if self._modal is not None:                     # R / S / G: click confirms, right click cancels
            if event.button() == Qt.MouseButton.LeftButton:
                self._commit_modal()
            elif event.button() == Qt.MouseButton.RightButton:
                self._cancel_modal()
            event.accept()
            return

        if self.current_tool == "select":
            self._pending_snapshot = self._get_all_strokes()   # for undo if this turns out to be a drag
            super().mousePressEvent(event)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = self._scene_pos(event)
        self._pending_snapshot = self._get_all_strokes()

        if self.current_tool in ("pen", "line"):
            self.current_stroke = VectorStroke(points=[pos], width=self.pen_width, color=self.pen_color,
                                               brush=self.brush)
            self.temp_drawing_item = self._add_stroke_item(self.current_stroke)
        elif self.current_tool == "eraser":
            self._erasing = True
            self._erased_any = False
            self._erase_last = pos
            self._erase_at(pos)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = self._scene_pos(event)
        if self._modal is not None:
            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self._apply_modal((pos.x(), pos.y()), ctrl)
            event.accept()
            return

        if self.current_tool == "select":
            super().mouseMoveEvent(event)
            return

        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return

        if self.current_tool == "pen" and self.current_stroke is not None:
            last_p = self.current_stroke.points[-1]
            dx = pos.x() - last_p.x()
            dy = pos.y() - last_p.y()
            if dx * dx + dy * dy >= 4.0:
                self.current_stroke.points.append(pos)
                self.temp_drawing_item._update_from_stroke()
        elif self.current_tool == "line" and self.current_stroke is not None:
            start = self.current_stroke.points[0]
            end = pos
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:      # Shift keeps the angle on 15 degree steps
                sx, sy = snap_angle((start.x(), start.y()), (pos.x(), pos.y()), 15.0)
                end = QPointF(sx, sy)
            self.current_stroke.points = [start, end]
            self.temp_drawing_item._update_from_stroke()
        elif self.current_tool == "eraser" and self._erasing:
            self._erase_segment(self._erase_last, pos)
            self._erase_last = pos
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._modal is not None:
            event.accept()
            return

        if self.current_tool == "select":
            super().mouseReleaseEvent(event)
            self._commit_item_moves()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.current_tool in ("pen", "line") and self.current_stroke is not None:
            stroke, item = self.current_stroke, self.temp_drawing_item
            self.current_stroke = None
            self.temp_drawing_item = None
            if self.current_tool == "line" and (len(stroke.points) < 2 or
                    math.hypot(stroke.points[1].x() - stroke.points[0].x(),
                               stroke.points[1].y() - stroke.points[0].y()) < 3.0):
                self.scene.removeItem(item)             # a click without a drag is not a line
            else:
                if self.current_tool == "pen" and self.smoothing > 0 and len(stroke.points) >= 3:
                    self._smooth_item(item, self.smoothing)
                if self._pending_snapshot is not None:
                    self._push_snapshot(self._pending_snapshot)
                self.content_changed.emit()
        elif self.current_tool == "eraser" and self._erasing:
            self._erasing = False
            self._erase_last = None
            if self._erased_any:
                self.content_changed.emit()
        self._pending_snapshot = None
        event.accept()

    def _commit_item_moves(self):
        # Select tool: strokes dragged with the mouse get their new position written into their points
        moved = [i for i in self._stroke_items() if i.pos().x() != 0 or i.pos().y() != 0]
        if moved:
            if self._pending_snapshot is not None:
                self._push_snapshot(self._pending_snapshot)
            for item in moved:
                item.bake_position()
            self.content_changed.emit()
        self._pending_snapshot = None

    # ---------------------------------------------------------------- eraser
    def _erase_at(self, pos: QPointF):
        # remove every stroke the round eraser touches
        radius = max(3.0, self.pen_width / 2.0)
        center = (pos.x(), pos.y())
        for item in self._stroke_items():
            if not item.sceneBoundingRect().adjusted(-radius, -radius, radius, radius).contains(pos):
                continue
            if stroke_hit(item.outline_xy(), item.stroke.width, center, radius):
                if not self._erased_any:
                    if self._pending_snapshot is not None:
                        self._push_snapshot(self._pending_snapshot)
                    self._erased_any = True
                self.scene.removeItem(item)

    def _erase_segment(self, a: QPointF, b: QPointF):
        # a fast mouse jumps; check along the way so thin strokes are not skipped
        radius = max(3.0, self.pen_width / 2.0)
        distance = math.hypot(b.x() - a.x(), b.y() - a.y())
        steps = max(1, int(math.ceil(distance / max(1.0, radius / 2.0))))
        for i in range(steps + 1):
            t = i / steps
            self._erase_at(QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t))

    # ---------------------------------------------------------------- keyboard: R rotate, S scale, G move
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)

        if self._modal is not None:
            self._modal_key(event)
            return

        if ctrl and key == Qt.Key.Key_Z:
            self.redo() if (mods & Qt.KeyboardModifier.ShiftModifier) else self.undo()
            return
        if ctrl and key == Qt.Key.Key_Y:
            self.redo()
            return
        if ctrl and key == Qt.Key.Key_A:
            for item in self._stroke_items():
                item.setSelected(True)
            return
        if not ctrl and key == Qt.Key.Key_Delete:
            self.delete_selected()
            return
        if not ctrl and key in (Qt.Key.Key_R, Qt.Key.Key_S, Qt.Key.Key_G):
            self._start_modal({Qt.Key.Key_R: "rotate", Qt.Key.Key_S: "scale", Qt.Key.Key_G: "move"}[key])
            return
        super().keyPressEvent(event)

    def delete_selected(self):
        items = self._selected_items()
        if not items:
            return
        self._push_undo()
        for item in items:
            self.scene.removeItem(item)
        self.content_changed.emit()

    def _start_modal(self, kind: str):
        items = self._selected_items()
        if not items:
            return                                       # nothing selected: nothing to transform
        bounds = union_bounds([(i.outline_xy(), i.stroke.width / 2.0) for i in items])
        start = self._cursor_scene_pos()
        self._modal = {
            "kind": kind,
            "items": items,
            "originals": [(i.points_xy(), i.stroke.width, i.stroke.angle) for i in items],
            "pivot": bounds_center(bounds),
            "start": (start.x(), start.y()),
            "snapshot": self._get_all_strokes(),
            "typed": "",
            "label": "",
        }
        self._apply_modal((start.x(), start.y()), False)

    def _modal_key(self, event: QKeyEvent):
        key = event.key()
        m = self._modal
        if key == Qt.Key.Key_Escape:
            self._cancel_modal()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._commit_modal()
            return
        text = event.text()
        changed = False
        if key == Qt.Key.Key_Backspace:
            m["typed"] = m["typed"][:-1]
            changed = True
        elif text and (text.isdigit() or text == "." or (text == "-" and not m["typed"])):
            m["typed"] += text                           # type a number, like Blender: R 90 Enter
            changed = True
        if changed:
            cur = self._cursor_scene_pos()
            ctrl = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
            self._apply_modal((cur.x(), cur.y()), ctrl)

    def _apply_modal(self, cur, ctrl: bool):
        # always computed from the original points, so nothing builds up while the mouse moves
        m = self._modal
        kind, pivot, start = m["kind"], m["pivot"], m["start"]
        typed = parse_number(m["typed"]) if m["typed"] else None
        results = []
        if kind == "rotate":
            degrees = typed if typed is not None else angle_delta(pivot, start, cur)
            if typed is None and ctrl:
                degrees = snap_value(degrees, 15.0)
            for pts, width, angle in m["originals"]:
                results.append((rotate_points(pts, pivot, degrees), width, angle + degrees))
            m["label"] = f"Rotate {degrees:.1f}\u00b0" + (f"   [{m['typed']}]" if m["typed"] else "")
        elif kind == "scale":
            factor = typed if typed is not None else scale_ratio(pivot, start, cur)
            if typed is None and ctrl:
                factor = snap_value(factor, 0.1)
            factor = max(0.05, min(20.0, factor))
            for pts, width, angle in m["originals"]:
                results.append((scale_points(pts, pivot, factor), width * factor, angle))
            m["label"] = f"Scale \u00d7{factor:.2f}" + (f"   [{m['typed']}]" if m["typed"] else "")
        else:
            dx, dy = cur[0] - start[0], cur[1] - start[1]
            for pts, width, angle in m["originals"]:
                results.append((translate_points(pts, dx, dy), width, angle))
            m["label"] = f"Move {dx:.0f}, {dy:.0f}"
        for item, (pts, width, angle) in zip(m["items"], results):
            item.set_geometry(pts, width, angle)
        self.viewport().update()

    def _commit_modal(self):
        m = self._modal
        self._modal = None
        if m is not None:
            self._push_snapshot(m["snapshot"])
            self.content_changed.emit()
        self.viewport().update()

    def _cancel_modal(self):
        m = self._modal
        self._modal = None
        if m is not None:
            for item, (pts, width, angle) in zip(m["items"], m["originals"]):
                item.set_geometry(pts, width, angle)
        self.viewport().update()

    # ---------------------------------------------------------------- operations on the selection / glyph
    def _target_items(self) -> List[StrokeGraphicsItem]:
        return self._selected_items() or self._stroke_items()   # no selection: the whole glyph

    def _ink_bounds(self, items):
        return union_bounds([(i.outline_xy(), i.stroke.width / 2.0) for i in items])

    def _transform_items(self, items, point_fn, width_factor: float = 1.0, angle_delta: float = 0.0):
        # one undo step for the whole operation
        self._push_undo()
        for item in items:
            item.set_geometry(point_fn(item.points_xy()), item.stroke.width * width_factor,
                              item.stroke.angle + angle_delta)
        self.content_changed.emit()
        self.viewport().update()

    def rotate_selection(self, degrees: float):
        items = self._selected_items()
        if not items or not degrees:
            return
        pivot = bounds_center(self._ink_bounds(items))
        self._transform_items(items, lambda pts: rotate_points(pts, pivot, degrees), 1.0, degrees)

    def scale_selection(self, factor: float):
        items = self._selected_items()
        if not items or not factor or factor == 1.0:
            return
        factor = max(0.05, min(20.0, factor))
        pivot = bounds_center(self._ink_bounds(items))
        self._transform_items(items, lambda pts: scale_points(pts, pivot, factor), factor)

    def center_in_box(self):
        items = self._target_items()
        if not items:
            return
        dx, dy = center_offset(self._ink_bounds(items), self.CANVAS_SIZE)
        self._transform_items(items, lambda pts: translate_points(pts, dx, dy))

    def fit_to_box(self):
        items = self._target_items()
        if not items:
            return
        bounds = self._ink_bounds(items)
        factor, (dx, dy) = fit_transform(bounds, self.CANVAS_SIZE, self.GUIDE_MARGIN)
        pivot = bounds_center(bounds)
        self._transform_items(
            items, lambda pts: translate_points(scale_points(pts, pivot, factor), dx, dy), factor)

    # ---------------------------------------------------------------- thickness, brush and smoothing of the selection
    def has_selection(self) -> bool:
        return bool(self._selected_items())

    def selection_summary(self):
        # (width, brush) of the first selected stroke, or None when nothing is selected
        items = self._selected_items()
        if not items:
            return None
        return items[0].stroke.width, items[0].stroke.brush

    def begin_width_edit(self):
        # called when the thickness slider is grabbed: remember the strokes for one undo step
        self._width_snapshot = self._get_all_strokes() if self.has_selection() else None
        self._width_changed = False

    def set_selection_width(self, width: float):
        for item in self._selected_items():
            item.set_geometry(item.points_xy(), width, item.stroke.angle)
        self._width_changed = True
        self.viewport().update()

    def end_width_edit(self):
        if self._width_snapshot is not None and self._width_changed:
            self._push_snapshot(self._width_snapshot)
            self.content_changed.emit()
        self._width_snapshot = None
        self._width_changed = False

    def set_selection_brush(self, brush: str):
        items = [i for i in self._selected_items() if i.stroke.brush != brush]
        if not items or brush not in BRUSHES:
            return
        self._push_undo()
        for item in items:
            item.stroke.brush = brush
            item._update_from_stroke()
        self.content_changed.emit()
        self.viewport().update()

    def _smooth_item(self, item: StrokeGraphicsItem, tolerance: float) -> bool:
        # fit smooth cubic curves through the stroke (Schneider's algorithm, see bezier_fit.py)
        if item.stroke.is_eraser:
            return False
        chain = fit_chain(item.outline_xy(), tolerance)
        if not chain:
            return False
        item.set_chain(chain)
        return True

    def simplify_selection(self, tolerance: float) -> int:
        # smooth the selected strokes (or all of them) into fewer, smoother curves; returns how many changed
        items = [i for i in self._target_items() if len(i.outline_xy()) >= 3]
        if not items or tolerance <= 0:
            return 0
        snapshot = self._get_all_strokes()
        changed = sum(1 for item in items if self._smooth_item(item, tolerance))
        if changed:
            self._push_snapshot(snapshot)
            self.content_changed.emit()
            self.viewport().update()
        return changed

    # ---------------------------------------------------------------- drawing of the view itself
    def drawBackground(self, painter: QPainter, rect: QRectF):
        # Draw white background
        painter.fillRect(rect, QColor("#ffffff"))

        # Draw external SVG if present
        if self.external_svg_renderer and self.external_svg_renderer.isValid():
            self.external_svg_renderer.render(painter, QRectF(0, 0, self.CANVAS_SIZE, self.CANVAS_SIZE))

        if self.show_guides:
            size, margin = float(self.CANVAS_SIZE), float(self.GUIDE_MARGIN)
            painter.save()
            pen = QPen(QColor(0, 122, 204, 90), 1.0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(margin, margin, size - 2 * margin, size - 2 * margin))   # safe area
            painter.drawLine(QPointF(size / 2, 0), QPointF(size / 2, size))                  # centre cross
            painter.drawLine(QPointF(0, size / 2), QPointF(size, size / 2))
            painter.restore()

    def drawForeground(self, painter: QPainter, rect: QRectF):
        m = self._modal
        if m is None:
            return
        painter.save()
        pen = QPen(QColor("#007acc"), 1.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        px, py = m["pivot"]
        painter.drawLine(QPointF(px - 7, py), QPointF(px + 7, py))       # pivot
        painter.drawLine(QPointF(px, py - 7), QPointF(px, py + 7))
        text = f"{m['label']}    click / Enter = apply,  Esc = cancel,  type a number"
        if m["kind"] != "move":
            text += ",  Ctrl = snap"
        font = QFont(self.font())
        font.setPointSize(9)
        painter.setFont(font)
        box = QRectF(6, 6, 440, 22)
        painter.fillRect(box, QColor(255, 255, 255, 225))
        painter.drawText(QPointF(box.left() + 6, box.top() + 15), text)
        painter.restore()

    def to_svg(self) -> str:
        size = self.CANVAS_SIZE
        strokes = self._get_all_strokes()
        strokes_meta = json.dumps([s.to_dict() for s in strokes])
        
        path_elements = []
        for s in strokes:
            if s.is_eraser:
                continue
            if s.is_filled:
                # square / tip strokes are shapes: small polygons filled with the nonzero rule
                fill_d = s.to_svg_fill_data()
                if fill_d:
                    path_elements.append(f'  <path d="{fill_d}" fill="{s.color}" stroke="none" fill-rule="nonzero" />')
                continue
            d = s.to_svg_path_data()
            if d:
                path_elements.append(
                    f'  <path d="{d}" fill="none" stroke="{s.color}" stroke-width="{s.width:.1f}" '
                    f'stroke-linecap="round" stroke-linejoin="round" />'
                )

        svg_content = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">',
            f'  <metadata type="application/json"><![CDATA[{strokes_meta}]]></metadata>',
            "\n".join(path_elements),
            '</svg>'
        ]
        return "\n".join(svg_content)

    def load_svg(self, svg_str: str):
        self._modal = None
        self.temp_drawing_item = None
        self.current_stroke = None
        self.scene.clear()
        self._next_z = 0
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.external_svg_renderer = None

        if not svg_str or not svg_str.strip():
            return

        try:
            root = ET.fromstring(svg_str)
            meta = root.find(".//{*}metadata")
            if meta is None:
                meta = root.find(".//metadata")
            if meta is not None and meta.text:
                strokes_data = json.loads(meta.text.strip())
                dropped = 0
                for item in strokes_data:
                    stroke = VectorStroke.from_dict(item)
                    if stroke.is_eraser:
                        # the old eraser only hid strokes on screen; the font and exports never had it
                        dropped += 1
                        continue
                    self._add_stroke_item(stroke)
                if dropped:
                    self.legacy_erasers_removed.emit(dropped)
                return
        except Exception:
            pass

        try:
            svg_bytes = svg_str.encode("utf-8")
            self.external_svg_renderer = QSvgRenderer(svg_bytes)
            self.viewport().update()
        except Exception as e:
            print(f"[GlyphCanvasWidget] Error rendering external SVG: {e}")

    def render_thumbnail(self, size: int = 100) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        
        scale = size / float(self.CANVAS_SIZE)
        painter.scale(scale, scale)

        if self.external_svg_renderer and self.external_svg_renderer.isValid():
            self.external_svg_renderer.render(painter, QRectF(0, 0, self.CANVAS_SIZE, self.CANVAS_SIZE))

        strokes = self._get_all_strokes()
        for stroke in strokes:
            if stroke.is_filled:
                painter.setPen(QPen(Qt.PenStyle.NoPen))
                painter.setBrush(QBrush(QColor(stroke.color)))
                painter.drawPath(stroke.build_fill_path())
                continue
            path = stroke.build_path()
            if stroke.is_eraser:
                pen = QPen(QColor("#ffffff"), stroke.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            else:
                pen = QPen(QColor(stroke.color), stroke.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        painter.end()
        return pixmap


class CanvasStudioToolBar(QWidget):
    def __init__(self, canvas: GlyphCanvasWidget, parent=None):
        super().__init__(parent)
        self.canvas = canvas

        # groups of controls wrap onto new rows when the window is narrow
        flow = FlowLayout(self, margin=8, h_spacing=14, v_spacing=6)

        # tools
        self.btn_select = self._tool_button("Select", "select.svg", "Select strokes. Then R rotate, S scale, G move, Delete removes.")
        self.btn_pen = self._tool_button("Pen", "pen.svg", "Draw freehand")
        self.btn_line = self._tool_button("Line", "line.svg", "Drag to draw a straight line. Hold Shift to keep the angle on 15° steps.")
        self.btn_eraser = self._tool_button("Eraser", "eraser.svg", "Drag over a stroke to remove it. The Thickness slider sets the eraser size.")
        self.btn_pen.setChecked(True)
        self.tool_group = QButtonGroup(self)
        for tool, button in (("select", self.btn_select), ("pen", self.btn_pen),
                             ("line", self.btn_line), ("eraser", self.btn_eraser)):
            self.tool_group.addButton(button)
            button.clicked.connect(lambda _=False, t=tool: self._set_tool(t))
        flow.addWidget(self._group(self.btn_select, self.btn_pen, self.btn_line, self.btn_eraser))

        # brush
        self.combo_brush = QComboBox()
        for name in BRUSHES:
            self.combo_brush.addItem(BRUSH_LABELS[name], name)
        self.combo_brush.setToolTip("Round: a round pen. Square: a flat square tip. "
                                    "Tip: thick in the middle and thin at the end, like a brush.\\n"
                                    "Changes the selected strokes, or the next strokes when nothing is selected.")
        self.combo_brush.currentIndexChanged.connect(self._on_brush_changed)
        flow.addWidget(self._group(self._label("Brush:"), self.combo_brush))

        # thickness: of the selected strokes, or of new strokes (and the eraser) when nothing is selected
        self.lbl_width = self._label("Thickness:")
        self.slider_width = QSlider(Qt.Orientation.Horizontal)
        self.slider_width.setRange(1, 60)
        self.slider_width.setValue(6)
        self.slider_width.setFixedWidth(110)
        self.slider_width.setToolTip("Thickness of the selected strokes, or of the next strokes when nothing is selected")
        self.lbl_width_val = QLabel("6px")
        self.lbl_width_val.setFixedWidth(34)
        self.lbl_width_val.setStyleSheet("font-size: 11px; color: #333333;")
        self.slider_width.sliderPressed.connect(self._on_width_pressed)
        self.slider_width.sliderReleased.connect(self._on_width_released)
        self.slider_width.valueChanged.connect(self._on_width_changed)
        flow.addWidget(self._group(self.lbl_width, self.slider_width, self.lbl_width_val))

        # smoothing: curve fitting (Schneider's algorithm) for new pen strokes, and the Simplify button
        self.slider_smooth = QSlider(Qt.Orientation.Horizontal)
        self.slider_smooth.setRange(0, 10)
        self.slider_smooth.setValue(int(canvas.smoothing))
        self.slider_smooth.setFixedWidth(80)
        self.slider_smooth.setToolTip("How strongly new pen strokes are turned into smooth curves (0 = off)")
        self.lbl_smooth_val = QLabel("")
        self.lbl_smooth_val.setFixedWidth(34)
        self.lbl_smooth_val.setStyleSheet("font-size: 11px; color: #333333;")
        self.slider_smooth.valueChanged.connect(self._on_smooth_changed)
        self.btn_simplify = QPushButton("Simplify")
        self.btn_simplify.setToolTip("Fit smooth Bézier curves through the selected strokes (or the whole glyph)")
        self.btn_simplify.clicked.connect(self._on_simplify)
        flow.addWidget(self._group(self._label("Smooth:"), self.slider_smooth, self.lbl_smooth_val, self.btn_simplify))
        self._on_smooth_changed(self.slider_smooth.value())

        # history
        self.btn_undo = QPushButton("↺ Undo")
        self.btn_undo.setToolTip("Undo (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.canvas.undo)
        self.btn_redo = QPushButton("↻ Redo")
        self.btn_redo.setToolTip("Redo (Ctrl+Y)")
        self.btn_redo.clicked.connect(self.canvas.redo)
        self.btn_clear = QPushButton(" Clear")
        self.btn_clear.setIcon(asset_icon("Trash.svg"))
        self.btn_clear.setToolTip("Clear all strokes on canvas")
        self.btn_clear.setStyleSheet("color: #d9534f;")
        self.btn_clear.clicked.connect(self._confirm_clear)
        flow.addWidget(self._group(self.btn_undo, self.btn_redo, self.btn_clear))

        # transform the selection
        self.spin_rotate = QDoubleSpinBox()
        self.spin_rotate.setRange(-360, 360)
        self.spin_rotate.setSingleStep(5)
        self.spin_rotate.setSuffix("°")
        self.spin_rotate.setValue(0)
        self.spin_rotate.setKeyboardTracking(False)       # typed values apply on Enter, not on every digit
        self.spin_rotate.setFixedWidth(80)
        self.spin_rotate.setToolTip("Rotate the selected strokes by this many degrees (type a value and press Enter). "
                                    "Keyboard: R, move the mouse, click.")
        self.spin_rotate.valueChanged.connect(self._on_rotate_changed)
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(0.1, 10.0)
        self.spin_scale.setValue(1.0)
        self.spin_scale.setSingleStep(0.1)
        self.spin_scale.setPrefix("× ")
        self.spin_scale.setKeyboardTracking(False)
        self.spin_scale.setFixedWidth(80)
        self.spin_scale.setToolTip("Scale the selected strokes by this factor (type a value and press Enter). "
                                   "Keyboard: S, move the mouse, click.")
        self.spin_scale.valueChanged.connect(self._on_scale_changed)
        flow.addWidget(self._group(self._label("Rotate by:"), self.spin_rotate,
                                   self._label("Scale by:"), self.spin_scale))

        # place the drawing
        self.btn_center = QPushButton("Center")
        self.btn_center.setToolTip("Move the selection (or the whole glyph) to the middle of the canvas")
        self.btn_center.clicked.connect(self.canvas.center_in_box)
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.setToolTip("Scale the selection (or the whole glyph) to fill the safe area and center it")
        self.btn_fit.clicked.connect(self.canvas.fit_to_box)
        self.chk_guides = QCheckBox("Guides")
        self.chk_guides.setChecked(True)
        self.chk_guides.setStyleSheet("font-size: 12px; color: #333333;")
        self.chk_guides.setToolTip("Show the center cross and the safe area")
        self.chk_guides.toggled.connect(self.canvas.set_guides_visible)
        flow.addWidget(self._group(self.btn_center, self.btn_fit, self.chk_guides))

        hint = QLabel("R rotate · S scale · G move · Delete removes")
        hint.setStyleSheet("font-size: 11px; color: #777777;")
        flow.addWidget(hint)

        # clicking a toolbar button must not take the keyboard away from the canvas (R / S / G / Delete)
        for w in self.findChildren(QPushButton) + [self.chk_guides]:
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_brush.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._style_buttons()
        self.canvas.selection_changed.connect(self._sync_from_selection)

    # building blocks
    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 12px; color: #555555;")
        return lbl

    def _tool_button(self, text: str, icon_file: str, tip: str) -> QPushButton:
        button = QPushButton(" " + text)
        button.setIcon(asset_icon(icon_file))                    # simple black icon from assets/icons
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tip)
        button.setCheckable(True)
        return button

    def _group(self, *widgets) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for w in widgets:
            row.addWidget(w)
        return box

    # tools
    def _set_tool(self, tool: str):
        self.canvas.set_tool(tool)
        self.canvas.setFocus()

    # brush
    def _on_brush_changed(self, _index: int):
        brush = self.combo_brush.currentData()
        if self.canvas.has_selection():
            self.canvas.set_selection_brush(brush)
        else:
            self.canvas.brush = brush

    # thickness
    def _on_width_pressed(self):
        if self.canvas.has_selection():
            self.canvas.begin_width_edit()

    def _on_width_released(self):
        self.canvas.end_width_edit()

    def _on_width_changed(self, value: int):
        self.lbl_width_val.setText(f"{value}px")
        if self.canvas.has_selection():
            if self.slider_width.isSliderDown():
                self.canvas.set_selection_width(float(value))      # live while dragging, one undo step on release
            else:
                self.canvas.begin_width_edit()                      # a click or key press: one step at once
                self.canvas.set_selection_width(float(value))
                self.canvas.end_width_edit()
        else:
            self.canvas.pen_width = float(value)

    def _sync_from_selection(self):
        # the sliders show the selected stroke; with nothing selected they show the settings for new strokes
        info = self.canvas.selection_summary()
        self.slider_width.blockSignals(True)
        self.combo_brush.blockSignals(True)
        if info:
            width, brush = info
            self.slider_width.setValue(int(round(max(1, min(60, width)))))
            self.combo_brush.setCurrentIndex(max(0, self.combo_brush.findData(brush)))
            self.lbl_width.setText("Selected:")
        else:
            self.slider_width.setValue(int(round(max(1, min(60, self.canvas.pen_width)))))
            self.combo_brush.setCurrentIndex(max(0, self.combo_brush.findData(self.canvas.brush)))
            self.lbl_width.setText("Thickness:")
        self.lbl_width_val.setText(f"{self.slider_width.value()}px")
        self.slider_width.blockSignals(False)
        self.combo_brush.blockSignals(False)

    # smoothing
    def _on_smooth_changed(self, value: int):
        self.canvas.smoothing = float(value)
        self.lbl_smooth_val.setText("off" if value == 0 else f"{value}px")

    def _on_simplify(self):
        tolerance = float(self.slider_smooth.value()) or 3.0
        self.canvas.simplify_selection(tolerance)

    # transform
    def _on_rotate_changed(self, value: float):
        # relative: rotate the selection by `value` degrees, then the box goes back to 0
        if value:
            self.canvas.rotate_selection(value)
            self.spin_rotate.blockSignals(True)
            self.spin_rotate.setValue(0)
            self.spin_rotate.blockSignals(False)

    def _on_scale_changed(self, value: float):
        # relative: scale the selection by this factor, then the box goes back to 1
        if value != 1.0:
            self.canvas.scale_selection(value)
            self.spin_scale.blockSignals(True)
            self.spin_scale.setValue(1.0)
            self.spin_scale.blockSignals(False)

    def _confirm_clear(self):
        reply = QMessageBox.question(
            self, "Clear Canvas", "Are you sure you want to clear the canvas?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.canvas.clear_canvas()

    def _style_buttons(self):
        style = """
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                color: #222222;
            }
            QPushButton:hover { background-color: #f0f0f0; }
            QPushButton:checked {
                background-color: #d6ebff;
                color: #111111;
                border-color: #007acc;
                font-weight: bold;
            }
            QComboBox {
                background-color: #ffffff;
                color: #222222;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 3px 8px;
                min-width: 64px;
                font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #222222;
                selection-background-color: #d6ebff;
                selection-color: #111111;
            }
        """
        self.setStyleSheet(style)
