import json
import math
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider,
    QLabel, QToolButton, QButtonGroup, QFrame, QFileDialog, QMessageBox,
    QGraphicsView, QGraphicsScene, QGraphicsPathItem, QGraphicsItem,
    QDoubleSpinBox, QCheckBox, QApplication
)
from PySide6.QtCore import Qt, QPointF, Signal, QRectF, QSize
from PySide6.QtGui import (
    QPainter, QPen, QColor, QPainterPath, QPaintEvent, QKeyEvent, QCursor,
    QMouseEvent, QPixmap, QBrush, QTransform, QFont
)
from PySide6.QtSvg import QSvgRenderer

from .canvas_math import (
    stroke_hit, rotate_points, scale_points, translate_points, union_bounds, bounds_center,
    angle_delta, snap_value, snap_angle, scale_ratio, center_offset, fit_transform, parse_number,
)


class VectorStroke:
    def __init__(self, points: Optional[List[QPointF]] = None, width: float = 6.0, color: str = "#111111", is_eraser: bool = False):
        self.points: List[QPointF] = points or []
        self.width: float = width
        self.color: str = color
        self.is_eraser: bool = is_eraser

    def build_path(self) -> QPainterPath:
        path = QPainterPath()
        if not self.points:
            return path
        
        if len(self.points) == 1:
            pt = self.points[0]
            path.addEllipse(pt, self.width / 2.0, self.width / 2.0)
            return path

        path.moveTo(self.points[0])
        for i in range(1, len(self.points) - 1):
            p0 = self.points[i]
            p1 = self.points[i + 1]
            mid = QPointF((p0.x() + p1.x()) / 2.0, (p0.y() + p1.y()) / 2.0)
            path.quadTo(p0, mid)
        
        path.lineTo(self.points[-1])
        return path

    def to_svg_path_data(self) -> str:
        if not self.points:
            return ""
        if len(self.points) == 1:
            p = self.points[0]
            r = self.width / 2.0
            return f"M {p.x()-r} {p.y()} A {r} {r} 0 1 0 {p.x()+r} {p.y()} A {r} {r} 0 1 0 {p.x()-r} {p.y()}"

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
            "is_eraser": self.is_eraser
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VectorStroke":
        pts = [QPointF(x, y) for x, y in data.get("points", [])]
        return cls(
            points=pts,
            width=data.get("width", 6.0),
            color=data.get("color", "#111111"),
            is_eraser=data.get("is_eraser", False)
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
        path = self.stroke.build_path()
        self.setPath(path)

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
        return [(p.x(), p.y()) for p in self.stroke.points]

    def set_geometry(self, points_xy, width: float):
        self.stroke.points = [QPointF(x, y) for x, y in points_xy]
        self.stroke.width = max(0.5, float(width))
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
        return VectorStroke(new_points, self.stroke.width * factor, self.stroke.color, self.stroke.is_eraser)


class GlyphCanvasWidget(QGraphicsView):
    content_changed = Signal()
    legacy_erasers_removed = Signal(int)   # old eraser strokes found while loading a glyph

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
        self.show_guides = True
        self.current_stroke: Optional[VectorStroke] = None
        self.temp_drawing_item: Optional[StrokeGraphicsItem] = None
        self._next_z = 0                                     # stacking order = drawing order
        self._pending_snapshot: Optional[List[VectorStroke]] = None
        self._erasing = False
        self._erased_any = False
        self._erase_last: Optional[QPointF] = None
        self._modal: Optional[Dict[str, Any]] = None         # R / S / G in progress

        # External SVG renderer (for imported SVGs without metadata)
        self.external_svg_renderer: Optional[QSvgRenderer] = None

        self.setStyleSheet("background-color: #ffffff; border: 1px solid #dcdcdc; border-radius: 6px;")
        self.set_tool("pen")

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
            self.current_stroke = VectorStroke(points=[pos], width=self.pen_width, color=self.pen_color)
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
            if stroke_hit(item.points_xy(), item.stroke.width, center, radius):
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
        bounds = union_bounds([(i.points_xy(), i.stroke.width / 2.0) for i in items])
        start = self._cursor_scene_pos()
        self._modal = {
            "kind": kind,
            "items": items,
            "originals": [(i.points_xy(), i.stroke.width) for i in items],
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
            for pts, width in m["originals"]:
                results.append((rotate_points(pts, pivot, degrees), width))
            m["label"] = f"Rotate {degrees:.1f}\u00b0" + (f"   [{m['typed']}]" if m["typed"] else "")
        elif kind == "scale":
            factor = typed if typed is not None else scale_ratio(pivot, start, cur)
            if typed is None and ctrl:
                factor = snap_value(factor, 0.1)
            factor = max(0.05, min(20.0, factor))
            for pts, width in m["originals"]:
                results.append((scale_points(pts, pivot, factor), width * factor))
            m["label"] = f"Scale \u00d7{factor:.2f}" + (f"   [{m['typed']}]" if m["typed"] else "")
        else:
            dx, dy = cur[0] - start[0], cur[1] - start[1]
            for pts, width in m["originals"]:
                results.append((translate_points(pts, dx, dy), width))
            m["label"] = f"Move {dx:.0f}, {dy:.0f}"
        for item, (pts, width) in zip(m["items"], results):
            item.set_geometry(pts, width)
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
            for item, (pts, width) in zip(m["items"], m["originals"]):
                item.set_geometry(pts, width)
        self.viewport().update()

    # ---------------------------------------------------------------- operations on the selection / glyph
    def _target_items(self) -> List[StrokeGraphicsItem]:
        return self._selected_items() or self._stroke_items()   # no selection: the whole glyph

    def _transform_items(self, items, point_fn, width_factor: float = 1.0):
        # one undo step for the whole operation
        self._push_undo()
        for item in items:
            item.set_geometry(point_fn(item.points_xy()), item.stroke.width * width_factor)
        self.content_changed.emit()
        self.viewport().update()

    def rotate_selection(self, degrees: float):
        items = self._selected_items()
        if not items or not degrees:
            return
        pivot = bounds_center(union_bounds([(i.points_xy(), i.stroke.width / 2.0) for i in items]))
        self._transform_items(items, lambda pts: rotate_points(pts, pivot, degrees))

    def scale_selection(self, factor: float):
        items = self._selected_items()
        if not items or not factor or factor == 1.0:
            return
        factor = max(0.05, min(20.0, factor))
        pivot = bounds_center(union_bounds([(i.points_xy(), i.stroke.width / 2.0) for i in items]))
        self._transform_items(items, lambda pts: scale_points(pts, pivot, factor), factor)

    def center_in_box(self):
        items = self._target_items()
        if not items:
            return
        bounds = union_bounds([(i.points_xy(), i.stroke.width / 2.0) for i in items])
        dx, dy = center_offset(bounds, self.CANVAS_SIZE)
        self._transform_items(items, lambda pts: translate_points(pts, dx, dy))

    def fit_to_box(self):
        items = self._target_items()
        if not items:
            return
        bounds = union_bounds([(i.points_xy(), i.stroke.width / 2.0) for i in items])
        factor, (dx, dy) = fit_transform(bounds, self.CANVAS_SIZE, self.GUIDE_MARGIN)
        pivot = bounds_center(bounds)
        self._transform_items(
            items, lambda pts: translate_points(scale_points(pts, pivot, factor), dx, dy), factor)

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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(6)

        # first row: tools, stroke size, undo / redo / clear
        layout = QHBoxLayout()
        layout.setSpacing(10)

        self.btn_select = QPushButton("⭘ Select")
        self.btn_select.setToolTip("Select strokes. Then R rotate, S scale, G move, Delete removes.")
        self.btn_select.setCheckable(True)
        self.btn_select.clicked.connect(lambda: self._set_tool("select"))

        self.btn_pen = QPushButton("✏️ Pen")
        self.btn_pen.setCheckable(True)
        self.btn_pen.setChecked(True)
        self.btn_pen.clicked.connect(lambda: self._set_tool("pen"))

        self.btn_line = QPushButton("╱ Line")
        self.btn_line.setToolTip("Drag to draw a straight line. Hold Shift to keep the angle on 15° steps.")
        self.btn_line.setCheckable(True)
        self.btn_line.clicked.connect(lambda: self._set_tool("line"))

        self.btn_eraser = QPushButton("🧹 Eraser")
        self.btn_eraser.setToolTip("Drag over a stroke to remove it. The Stroke slider sets the eraser size.")
        self.btn_eraser.setCheckable(True)
        self.btn_eraser.clicked.connect(lambda: self._set_tool("eraser"))

        self.tool_group = QButtonGroup(self)
        for b in (self.btn_select, self.btn_pen, self.btn_line, self.btn_eraser):
            self.tool_group.addButton(b)
            layout.addWidget(b)

        layout.addSpacing(6)
        lbl_width = QLabel("Stroke:")
        lbl_width.setStyleSheet("font-size: 12px; color: #555555;")
        self.slider_width = QSlider(Qt.Orientation.Horizontal)
        self.slider_width.setRange(2, 32)
        self.slider_width.setValue(6)
        self.slider_width.setFixedWidth(100)
        self.lbl_width_val = QLabel("6px")
        self.lbl_width_val.setFixedWidth(30)
        self.lbl_width_val.setStyleSheet("font-size: 11px; color: #333333;")
        self.slider_width.valueChanged.connect(self._on_width_changed)

        layout.addWidget(lbl_width)
        layout.addWidget(self.slider_width)
        layout.addWidget(self.lbl_width_val)

        layout.addSpacing(10)

        self.btn_undo = QPushButton("↺ Undo")
        self.btn_undo.setToolTip("Undo (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.canvas.undo)

        self.btn_redo = QPushButton("↻ Redo")
        self.btn_redo.setToolTip("Redo (Ctrl+Y)")
        self.btn_redo.clicked.connect(self.canvas.redo)

        self.btn_clear = QPushButton("🗑 Clear")
        self.btn_clear.setToolTip("Clear all strokes on canvas")
        self.btn_clear.setStyleSheet("color: #d9534f;")
        self.btn_clear.clicked.connect(self._confirm_clear)

        layout.addWidget(self.btn_undo)
        layout.addWidget(self.btn_redo)
        layout.addWidget(self.btn_clear)
        layout.addStretch()
        outer.addLayout(layout)

        # second row: transform the selection, place the drawing, guides
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        lbl_rotate = QLabel("Rotate by:")
        lbl_rotate.setStyleSheet("font-size: 12px; color: #555555;")
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

        lbl_scale = QLabel("Scale by:")
        lbl_scale.setStyleSheet("font-size: 12px; color: #555555;")
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

        hint = QLabel("R rotate · S scale · G move · Delete removes")
        hint.setStyleSheet("font-size: 11px; color: #777777;")

        for w in (lbl_rotate, self.spin_rotate, lbl_scale, self.spin_scale, self.btn_center, self.btn_fit,
                  self.chk_guides):
            row2.addWidget(w)
        row2.addSpacing(10)
        row2.addWidget(hint)
        row2.addStretch()
        outer.addLayout(row2)

        # clicking a toolbar button must not take the keyboard away from the canvas (R / S / G / Delete)
        for w in self.findChildren(QPushButton) + [self.chk_guides]:
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._style_buttons()

    def _set_tool(self, tool: str):
        self.canvas.set_tool(tool)
        self.canvas.setFocus()

    def _on_width_changed(self, value: int):
        self.canvas.pen_width = float(value)
        self.lbl_width_val.setText(f"{value}px")

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
                background-color: #007acc;
                color: #ffffff;
                border-color: #005999;
                font-weight: bold;
            }
        """
        self.setStyleSheet(style)
