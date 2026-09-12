import json
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider,
    QLabel, QToolButton, QButtonGroup, QFrame, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QPointF, Signal, QRectF, QSize
from PySide6.QtGui import (
    QPainter, QPen, QColor, QPainterPath, QPaintEvent,
    QMouseEvent, QPixmap, QBrush
)
from PySide6.QtSvg import QSvgRenderer

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

class GlyphCanvasWidget(QWidget):
    content_changed = Signal()

    CANVAS_SIZE = 500  # Logical coordinate size (SVG viewBox reference)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(self.CANVAS_SIZE, self.CANVAS_SIZE)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.strokes: List[VectorStroke] = []
        self.undo_stack: List[List[VectorStroke]] = []
        self.redo_stack: List[List[VectorStroke]] = []
        self.current_stroke: Optional[VectorStroke] = None

        self.current_tool = "pen"  # "pen" or "eraser"
        self.pen_width = 6.0
        self.pen_color = "#111111"
        self.external_svg_renderer: Optional[QSvgRenderer] = None

        self.setStyleSheet("background-color: #ffffff; border: 1px solid #dcdcdc; border-radius: 6px;")

    def _push_undo(self):
        snapshot = [
            VectorStroke(points=[QPointF(p.x(), p.y()) for p in s.points], width=s.width, color=s.color, is_eraser=s.is_eraser)
            for s in self.strokes
        ]
        self.undo_stack.append(snapshot)
        self.redo_stack.clear()
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo(self):
        if not self.undo_stack:
            return
        snapshot = [
            VectorStroke(points=[QPointF(p.x(), p.y()) for p in s.points], width=s.width, color=s.color, is_eraser=s.is_eraser)
            for s in self.strokes
        ]
        self.redo_stack.append(snapshot)
        self.strokes = self.undo_stack.pop()
        self.update()
        self.content_changed.emit()

    def redo(self):
        if not self.redo_stack:
            return
        snapshot = [
            VectorStroke(points=[QPointF(p.x(), p.y()) for p in s.points], width=s.width, color=s.color, is_eraser=s.is_eraser)
            for s in self.strokes
        ]
        self.undo_stack.append(snapshot)
        self.strokes = self.redo_stack.pop()
        self.update()
        self.content_changed.emit()

    def clear_canvas(self):
        if not self.strokes and not self.external_svg_renderer:
            return
        self._push_undo()
        self.strokes.clear()
        self.external_svg_renderer = None
        self.update()
        self.content_changed.emit()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._push_undo()
            pos = event.position()
            self.current_stroke = VectorStroke(
                points=[QPointF(pos.x(), pos.y())],
                width=self.pen_width,
                color=self.pen_color,
                is_eraser=(self.current_tool == "eraser")
            )
            self.strokes.append(self.current_stroke)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if (event.buttons() & Qt.MouseButton.LeftButton) and self.current_stroke:
            pos = event.position()
            last_p = self.current_stroke.points[-1]
            dx = pos.x() - last_p.x()
            dy = pos.y() - last_p.y()
            if dx * dx + dy * dy >= 4.0:  # Distance >= 2px
                self.current_stroke.points.append(QPointF(pos.x(), pos.y()))
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.current_stroke:
            self.current_stroke = None
            self.update()
            self.content_changed.emit()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        painter.fillRect(self.rect(), QColor("#ffffff"))

        if self.external_svg_renderer and self.external_svg_renderer.isValid():
            self.external_svg_renderer.render(painter, QRectF(0, 0, self.CANVAS_SIZE, self.CANVAS_SIZE))

        for stroke in self.strokes:
            path = stroke.build_path()
            if stroke.is_eraser:
                pen = QPen(QColor("#ffffff"), stroke.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            else:
                pen = QPen(QColor(stroke.color), stroke.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

    def to_svg(self) -> str:
        size = self.CANVAS_SIZE
        strokes_meta = json.dumps([s.to_dict() for s in self.strokes])
        
        path_elements = []
        for s in self.strokes:
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
        self.strokes.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.external_svg_renderer = None

        if not svg_str or not svg_str.strip():
            self.update()
            return

        try:
            root = ET.fromstring(svg_str)
            meta = root.find(".//{*}metadata")
            if meta is None:
                meta = root.find(".//metadata")
            if meta is not None and meta.text:
                strokes_data = json.loads(meta.text.strip())
                for item in strokes_data:
                    self.strokes.append(VectorStroke.from_dict(item))
                self.update()
                return
        except Exception as e:
            pass

        try:
            svg_bytes = svg_str.encode("utf-8")
            self.external_svg_renderer = QSvgRenderer(svg_bytes)
            self.update()
        except Exception as e:
            print(f"[GlyphCanvasWidget] Error rendering external SVG: {e}")

    def render_thumbnail(self, size: int = 100) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.white)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        
        scale = size / float(self.CANVAS_SIZE)
        painter.scale(scale, scale)

        if self.external_svg_renderer and self.external_svg_renderer.isValid():
            self.external_svg_renderer.render(painter, QRectF(0, 0, self.CANVAS_SIZE, self.CANVAS_SIZE))

        for stroke in self.strokes:
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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        self.btn_pen = QPushButton("✏️ Pen")
        self.btn_pen.setCheckable(True)
        self.btn_pen.setChecked(True)
        self.btn_pen.clicked.connect(lambda: self._set_tool("pen"))

        self.btn_eraser = QPushButton("🧹 Eraser")
        self.btn_eraser.setCheckable(True)
        self.btn_eraser.clicked.connect(lambda: self._set_tool("eraser"))

        self.tool_group = QButtonGroup(self)
        self.tool_group.addButton(self.btn_pen)
        self.tool_group.addButton(self.btn_eraser)

        layout.addWidget(self.btn_pen)
        layout.addWidget(self.btn_eraser)

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
        self.btn_undo.setToolTip("Undo stroke (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.canvas.undo)

        self.btn_redo = QPushButton("↻ Redo")
        self.btn_redo.setToolTip("Redo stroke (Ctrl+Y)")
        self.btn_redo.clicked.connect(self.canvas.redo)

        self.btn_clear = QPushButton("🗑 Clear")
        self.btn_clear.setToolTip("Clear all strokes on canvas")
        self.btn_clear.setStyleSheet("color: #d9534f;")
        self.btn_clear.clicked.connect(self._confirm_clear)

        layout.addWidget(self.btn_undo)
        layout.addWidget(self.btn_redo)
        layout.addWidget(self.btn_clear)

        self._style_buttons()

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

    def _set_tool(self, tool: str):
        self.canvas.current_tool = tool

    def _on_width_changed(self, val: int):
        self.canvas.pen_width = float(val)
        self.lbl_width_val.setText(f"{val}px")

    def _confirm_clear(self):
        self.canvas.clear_canvas()
