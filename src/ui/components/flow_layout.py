from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout

from .canvas_math import flow_positions

# A layout that places its widgets left to right and starts a new row when they no longer fit,
# so a toolbar stays usable when the window gets narrow. The row breaking itself is the plain
# function flow_positions in canvas_math.py. This follows the usual flow layout pattern from the Qt examples.


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 8, v_spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        try:
            return Qt.Orientation(0)                  # does not want to grow: the usual answer for a flow layout
        except (ValueError, TypeError):
            return Qt.Orientation.Horizontal          # some PySide6 versions do not accept an empty flag

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        width = height = 0
        for item in self._items:
            hint = item.minimumSize()
            width = max(width, hint.width())
            height = max(height, hint.height())
        m = self.contentsMargins()
        return QSize(width + m.left() + m.right(), height + m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        inner = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        items = [item for item in self._items if not item.isEmpty()]     # hidden widgets take no room
        sizes = [(item.sizeHint().width(), item.sizeHint().height()) for item in items]
        positions, total = flow_positions(sizes, inner.width(), self._h_spacing, self._v_spacing)
        if not test_only:
            for item, (x, y), (w, h) in zip(items, positions, sizes):
                item.setGeometry(QRect(QPoint(inner.x() + int(x), inner.y() + int(y)), QSize(int(w), int(h))))
        return int(total) + m.top() + m.bottom()
