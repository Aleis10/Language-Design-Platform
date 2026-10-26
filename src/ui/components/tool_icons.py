from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

# Simple black line icons for the canvas toolbar, drawn with QPainter so no image files are needed.
# Everything is drawn on a 20 x 20 grid and scaled to the requested size.

ICON_GRID = 20.0


def _canvas(size: int):
    scale = 2                                   # draw at twice the size so the lines stay sharp on small buttons
    pm = QPixmap(size * scale, size * scale)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    k = size / ICON_GRID
    p.scale(k, k)
    return pm, p


def _pen(color: str, width: float = 1.6) -> QPen:
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_select(p, color):
    p.setPen(_pen(color, 1.2))
    p.setBrush(QColor(color))
    p.drawPolygon(QPolygonF([QPointF(5, 3), QPointF(5, 16), QPointF(8.3, 12.8), QPointF(10.6, 17.5),
                             QPointF(12.6, 16.6), QPointF(10.3, 12), QPointF(14.6, 12)]))


def _draw_pen(p, color):
    # a pen lying at 45 degrees with its tip at the bottom left
    p.save()
    p.translate(10, 10)
    p.rotate(-45)
    p.setPen(_pen(color, 1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-3.5, -2.6, 12.5, 5.2), 1.4, 1.4)      # body
    p.setBrush(QColor(color))
    p.drawPolygon(QPolygonF([QPointF(-3.5, -2.6), QPointF(-3.5, 2.6), QPointF(-9.5, 0)]))   # nib
    p.drawLine(QPointF(4.5, -2.6), QPointF(4.5, 2.6))                # band near the cap
    p.restore()


def _draw_eraser(p, color):
    p.save()
    p.translate(10, 9.5)
    p.rotate(-40)
    p.setPen(_pen(color, 1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-8, -4.2, 16, 8.4), 1.6, 1.6)
    p.setBrush(QColor(color))
    p.drawRect(QRectF(0, -4.2, 8, 8.4))                              # the worn half is solid
    p.restore()
    p.setPen(_pen(color, 1.4))
    p.drawLine(QPointF(3, 17.5), QPointF(17, 17.5))


def _draw_line(p, color):
    p.setPen(_pen(color, 1.8))
    p.drawLine(QPointF(4.5, 15.5), QPointF(15.5, 4.5))
    p.setBrush(QColor(color))
    p.drawEllipse(QPointF(4.5, 15.5), 1.6, 1.6)
    p.drawEllipse(QPointF(15.5, 4.5), 1.6, 1.6)


def _draw_trash(p, color):
    p.setPen(_pen(color, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(4, 6), QPointF(16, 6))                        # lid
    p.drawLine(QPointF(8, 6), QPointF(8, 4))
    p.drawLine(QPointF(8, 4), QPointF(12, 4))
    p.drawLine(QPointF(12, 4), QPointF(12, 6))
    p.drawPolygon(QPolygonF([QPointF(5.5, 6), QPointF(6.5, 17), QPointF(13.5, 17), QPointF(14.5, 6)]))
    p.drawLine(QPointF(8.5, 8.5), QPointF(8.8, 14.5))
    p.drawLine(QPointF(11.5, 8.5), QPointF(11.2, 14.5))


_DRAWERS = {
    "select": _draw_select,
    "pen": _draw_pen,
    "eraser": _draw_eraser,
    "line": _draw_line,
    "trash": _draw_trash,
}


def tool_icon(name: str, size: int = 18, color: str = "#1a1a1a") -> QIcon:
    drawer = _DRAWERS.get(name)
    if drawer is None:
        return QIcon()
    pm, p = _canvas(size)
    drawer(p, color)
    p.end()
    return QIcon(pm)
