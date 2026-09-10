import os
import re
from typing import Optional, Dict, Any, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFrame, QStackedWidget, QDialog,
    QFormLayout, QMessageBox, QFileDialog, QListWidget, QListWidgetItem,
    QSizePolicy, QGridLayout
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QFont
from PySide6.QtSvg import QSvgRenderer

try:
    from database.glyph_db import GlyphRepository
    from ui.components.glyph_canvas import GlyphCanvasWidget, CanvasStudioToolBar
    from ui.components.glyph_audio import GlyphAudioWidget
    from ui.components.ipa_picker import IPAPickerDialog
except (ImportError, ValueError):
    from ...database.glyph_db import GlyphRepository
    from ..components.glyph_canvas import GlyphCanvasWidget, CanvasStudioToolBar
    from ..components.glyph_audio import GlyphAudioWidget
    from ..components.ipa_picker import IPAPickerDialog


def get_base_data_dir() -> str:
    """Find or create the canonical data root folder."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    data_dir = os.path.join(root, "data")
    os.makedirs(os.path.join(data_dir, "images", "svg"), exist_ok=True)
    os.makedirs(os.path.join(data_dir, "audio", "glyphs"), exist_ok=True)
    return data_dir


class AddGroupDialog(QDialog):
    """Dialog to create or edit a glyph group."""
    def __init__(self, group_name: str = "", group_desc: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Glyph Group" if not group_name else "Edit Group")
        self.setFixedSize(380, 200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        self.input_name = QLineEdit(group_name)
        self.input_name.setPlaceholderText("e.g., Radicals, Consonants, Logograms")
        self.input_desc = QLineEdit(group_desc)
        self.input_desc.setPlaceholderText("Optional description or semantic class")

        form.addRow("Group Name:", self.input_name)
        form.addRow("Description:", self.input_desc)
        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Save Group")
        btn_save.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_save.clicked.connect(self._validate_and_accept)

        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def _validate_and_accept(self):
        if not self.input_name.text().strip():
            QMessageBox.warning(self, "Validation Error", "Group Name cannot be empty.")
            return
        self.accept()

    def get_data(self):
        return self.input_name.text().strip(), self.input_desc.text().strip()


class Glyphs_Page(QWidget):
    """Dual-view Logograms & Script Workspace: Gallery View and Canvas Studio Mode."""
    def __init__(self, glyph_repo: GlyphRepository, language_id: str, db_path: str = "", session_dir: str = "", parent=None):
        super().__init__(parent)
        self.glyph_repo = glyph_repo
        self.language_id = language_id
        self.db_path = db_path
        self.session_dir = session_dir
        
        if self.session_dir:
            self.data_dir = self.session_dir
        elif self.db_path:
            possible_root = os.path.dirname(os.path.dirname(os.path.abspath(self.db_path)))
            if os.path.exists(os.path.join(possible_root, "audio")):
                self.data_dir = possible_root
            else:
                self.data_dir = get_base_data_dir()
        else:
            self.data_dir = get_base_data_dir()

        os.makedirs(os.path.join(self.data_dir, "images", "svg"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "audio", "glyphs"), exist_ok=True)

        # Active state in Canvas Studio
        self.active_glyph_id: Optional[str] = None
        self.active_group_id: Optional[str] = None
        self.active_glyph_data: Optional[Dict[str, Any]] = None

        self._load_stylesheet()

        # Main Stacked Layout (0 = Gallery, 1 = Studio)
        self.stack = QStackedWidget(self)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.stack)

        self._build_gallery_view()
        self._build_studio_view()

        self.stack.setCurrentIndex(0)
        self.refresh_gallery()

    def _load_stylesheet(self):
        style_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style", "glyphs_page.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    # Group Overview

    def _build_gallery_view(self):
        self.gallery_widget = QWidget()
        gallery_layout = QVBoxLayout(self.gallery_widget)
        gallery_layout.setContentsMargins(0, 0, 0, 0)
        gallery_layout.setSpacing(0)

        # 1. Top Bar
        top_bar = QWidget()
        top_bar.setObjectName("GlyphsTopBar")
        tb_layout = QHBoxLayout(top_bar)
        tb_layout.setContentsMargins(24, 12, 24, 12)
        tb_layout.setSpacing(12)

        lbl_title = QLabel("Logograms & Script Workspace")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #111111;")

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("🔍 Filter symbols by name, meaning, or IPA...")
        self.input_search.setFixedWidth(280)
        self.input_search.textChanged.connect(self._filter_glyphs)

        btn_add_group = QPushButton("+ Add Group")
        btn_add_group.setObjectName("BtnAddGroup")
        btn_add_group.clicked.connect(self.prompt_add_group)

        tb_layout.addWidget(lbl_title)
        tb_layout.addSpacing(16)
        tb_layout.addWidget(self.input_search)
        tb_layout.addStretch()
        tb_layout.addWidget(btn_add_group)

        gallery_layout.addWidget(top_bar)

        # 2. Scrollable Gallery Cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("GlyphsScrollArea")
        self.scroll_area.setWidgetResizable(True)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(24, 20, 24, 24)
        self.cards_layout.setSpacing(18)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.cards_container)
        gallery_layout.addWidget(self.scroll_area)

        self.stack.addWidget(self.gallery_widget)

    def refresh_gallery(self):
        """Reload all group cards and glyph tiles from SQLite."""
        # Clear existing cards layout
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        groups = self.glyph_repo.get_groups(self.language_id)
        if not groups:
            # Empty state
            empty = QFrame()
            empty.setStyleSheet("background-color: #ffffff; border: 1px dashed #cccccc; border-radius: 8px; padding: 40px;")
            elayout = QVBoxLayout(empty)
            elayout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            elbl1 = QLabel("No Script Groups Yet")
            elbl1.setStyleSheet("font-size: 18px; font-weight: bold; color: #555555;")
            elbl2 = QLabel("Organize your logograms, radicals, and custom glyphs into classified sets.")
            elbl2.setStyleSheet("font-size: 13px; color: #888888; margin-top: 4px; margin-bottom: 12px;")
            ebtn = QPushButton("+ Create First Group")
            ebtn.setObjectName("BtnAddGroup")
            ebtn.clicked.connect(self.prompt_add_group)
            elayout.addWidget(elbl1, alignment=Qt.AlignmentFlag.AlignCenter)
            elayout.addWidget(elbl2, alignment=Qt.AlignmentFlag.AlignCenter)
            elayout.addWidget(ebtn, alignment=Qt.AlignmentFlag.AlignCenter)
            self.cards_layout.addWidget(empty)
            return

        for group in groups:
            card = self._create_group_card(group)
            self.cards_layout.addWidget(card)

    def _create_group_card(self, group: Dict[str, Any]) -> QFrame:
        card = QFrame()
        card.setProperty("class", "group-card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 12)
        card_layout.setSpacing(10)

        # Header
        header = QFrame()
        header.setObjectName("GroupHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(14, 10, 14, 10)
        h_layout.setSpacing(10)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title_row = QHBoxLayout()
        lbl_name = QLabel(group["name"])
        lbl_name.setProperty("class", "group-title")
        
        glyphs = self.glyph_repo.get_glyphs_by_group(group["id"])
        badge = QLabel(f"{len(glyphs)} symbols")
        badge.setProperty("class", "badge-count")

        title_row.addWidget(lbl_name)
        title_row.addWidget(badge)
        title_row.addStretch()

        desc_text = group.get("description", "")
        lbl_desc = QLabel(desc_text) if desc_text else None
        if lbl_desc:
            lbl_desc.setProperty("class", "group-desc")

        title_col.addLayout(title_row)
        if lbl_desc:
            title_col.addWidget(lbl_desc)

        # Actions in header
        btn_add = QPushButton("+ Add Glyph")
        btn_add.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; padding: 4px 10px; border-radius: 4px;")
        btn_add.clicked.connect(lambda _, gid=group["id"], gname=group["name"]: self.create_new_glyph(gid, gname))

        btn_rename = QPushButton("✏️")
        btn_rename.setToolTip("Rename Group")
        btn_rename.clicked.connect(lambda _, g=group: self.prompt_edit_group(g))

        btn_del = QPushButton("🗑")
        btn_del.setToolTip("Delete Group")
        btn_del.setStyleSheet("color: #d9534f;")
        btn_del.clicked.connect(lambda _, gid=group["id"], gname=group["name"]: self.confirm_delete_group(gid, gname))

        h_layout.addLayout(title_col)
        h_layout.addStretch()
        h_layout.addWidget(btn_add)
        h_layout.addWidget(btn_rename)
        h_layout.addWidget(btn_del)

        card_layout.addWidget(header)

        # Glyph Tiles Grid
        tiles_container = QWidget()
        grid = QGridLayout(tiles_container)
        grid.setContentsMargins(14, 6, 14, 6)
        grid.setSpacing(12)

        cols = 5
        idx = 0
        for glyph in glyphs:
            tile = self._create_glyph_tile(glyph, group)
            grid.addWidget(tile, idx // cols, idx % cols)
            idx += 1

        # Add New Glyph Tile placeholder
        add_tile = self._create_add_tile(group["id"], group["name"])
        grid.addWidget(add_tile, idx // cols, idx % cols)

        card_layout.addWidget(tiles_container)
        return card

    def _create_glyph_tile(self, glyph: Dict[str, Any], group: Dict[str, Any]) -> QFrame:
        tile = QFrame()
        tile.setProperty("class", "glyph-tile")
        t_layout = QVBoxLayout(tile)
        t_layout.setContentsMargins(10, 10, 10, 10)
        t_layout.setSpacing(4)
        t_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Vector Thumbnail Preview
        lbl_preview = QLabel()
        lbl_preview.setFixedSize(90, 90)
        lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_preview.setStyleSheet("background-color: #fafafa; border: 1px solid #eeeeee; border-radius: 4px;")

        svg_str = glyph.get("svg_data", "")
        if svg_str and svg_str.strip():
            temp_canvas = GlyphCanvasWidget()
            temp_canvas.load_svg(svg_str)
            pixmap = temp_canvas.render_thumbnail(86)
            lbl_preview.setPixmap(pixmap)
        else:
            lbl_preview.setText("[Empty]")
            lbl_preview.setStyleSheet("color: #aaaaaa; font-size: 11px;")

        # Glyph Name & Gloss
        lbl_name = QLabel(glyph["name"])
        lbl_name.setStyleSheet("font-weight: bold; font-size: 13px; color: #111111;")
        lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_meaning = QLabel(glyph.get("meaning", "") or "—")
        lbl_meaning.setStyleSheet("font-size: 11px; color: #666666;")
        lbl_meaning.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Badges row: IPA pill & Audio indicator
        badges_row = QHBoxLayout()
        badges_row.setSpacing(4)
        badges_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if glyph.get("ipa_reading"):
            ipa_lbl = QLabel(f"/{glyph['ipa_reading']}/")
            ipa_lbl.setStyleSheet("font-family: monospace; font-size: 10px; background: #eef4ff; color: #005999; padding: 1px 5px; border-radius: 3px;")
            badges_row.addWidget(ipa_lbl)

        if glyph.get("audio_path"):
            audio_lbl = QLabel("🔊")
            audio_lbl.setToolTip("Pronunciation audio attached")
            badges_row.addWidget(audio_lbl)

        # Tile Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_edit = QPushButton("Edit")
        btn_edit.setStyleSheet("background-color: #007acc; color: white; padding: 3px 10px; font-size: 11px; border-radius: 3px;")
        btn_edit.clicked.connect(lambda _, g=glyph, grp=group: self.open_studio_mode(g, grp))

        btn_del = QPushButton("🗑")
        btn_del.setStyleSheet("border: none; color: #888888; font-size: 11px;")
        btn_del.setToolTip("Delete Glyph")
        btn_del.clicked.connect(lambda _, gid=glyph["id"], gname=glyph["name"]: self.confirm_delete_glyph(gid, gname))

        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_del)

        t_layout.addWidget(lbl_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        t_layout.addWidget(lbl_name, alignment=Qt.AlignmentFlag.AlignCenter)
        t_layout.addWidget(lbl_meaning, alignment=Qt.AlignmentFlag.AlignCenter)
        t_layout.addLayout(badges_row)
        t_layout.addLayout(btn_row)

        return tile

    def _create_add_tile(self, group_id: str, group_name: str) -> QFrame:
        tile = QFrame()
        tile.setProperty("class", "glyph-tile-add")
        t_layout = QVBoxLayout(tile)
        t_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t_layout.setSpacing(6)

        lbl_plus = QLabel("+")
        lbl_plus.setStyleSheet("font-size: 28px; color: #007acc; font-weight: bold;")
        lbl_txt = QLabel("New Glyph")
        lbl_txt.setStyleSheet("font-size: 12px; color: #555555; font-weight: bold;")

        t_layout.addWidget(lbl_plus, alignment=Qt.AlignmentFlag.AlignCenter)
        t_layout.addWidget(lbl_txt, alignment=Qt.AlignmentFlag.AlignCenter)

        # Clickable frame
        tile.mousePressEvent = lambda e: self.create_new_glyph(group_id, group_name)
        tile.setCursor(Qt.CursorShape.PointingHandCursor)
        return tile

    # Canvas Area (Studio Mode)

    def _build_studio_view(self):
        self.studio_widget = QWidget()
        studio_layout = QVBoxLayout(self.studio_widget)
        studio_layout.setContentsMargins(0, 0, 0, 0)
        studio_layout.setSpacing(0)

        # 1. Studio Header Top Bar
        header = QWidget()
        header.setObjectName("StudioHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 10, 20, 10)
        h_layout.setSpacing(12)

        btn_back = QPushButton("← Back to Gallery")
        btn_back.setObjectName("BtnBackGallery")
        btn_back.clicked.connect(self.back_to_gallery)

        self.lbl_breadcrumb = QLabel("Groups > Radicals > Sun")
        self.lbl_breadcrumb.setStyleSheet("font-size: 14px; font-weight: bold; color: #333333;")

        self.btn_export_single_svg = QPushButton("⤓ Export SVG")
        self.btn_export_single_svg.setStyleSheet("padding: 6px 14px; border: 1px solid #cccccc; border-radius: 4px; background: white;")
        self.btn_export_single_svg.clicked.connect(self.export_active_svg)

        btn_save = QPushButton("💾 Save Glyph")
        btn_save.setObjectName("BtnSaveGlyph")
        btn_save.clicked.connect(self.save_active_glyph)

        h_layout.addWidget(btn_back)
        h_layout.addSpacing(8)
        h_layout.addWidget(self.lbl_breadcrumb)
        h_layout.addStretch()
        h_layout.addWidget(self.btn_export_single_svg)
        h_layout.addWidget(btn_save)

        studio_layout.addWidget(header)

        # 2. Main Studio Workspace Area (Left Drawer + Center Canvas + Right Meta Panel)
        workspace = QWidget()
        w_layout = QHBoxLayout(workspace)
        w_layout.setContentsMargins(12, 12, 12, 12)
        w_layout.setSpacing(12)

        # CENTER: Vector Drawing Canvas
        canvas_col = QVBoxLayout()
        canvas_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_col.setSpacing(8)

        self.canvas = GlyphCanvasWidget()
        self.toolbar = CanvasStudioToolBar(self.canvas)

        canvas_col.addWidget(self.toolbar)
        canvas_col.addWidget(self.canvas)
        canvas_col.addStretch()

        w_layout.addLayout(canvas_col, stretch=1)

        # RIGHT: Linguistic Metadata & Audio Panel
        self.meta_panel = QFrame()
        self.meta_panel.setObjectName("StudioMetadataPanel")
        self.meta_panel.setFixedWidth(300)
        m_layout = QVBoxLayout(self.meta_panel)
        m_layout.setContentsMargins(16, 16, 16, 16)
        m_layout.setSpacing(12)

        lbl_meta_head = QLabel("Linguistic Metadata")
        lbl_meta_head.setStyleSheet("font-weight: bold; font-size: 14px; color: #111111; margin-bottom: 4px;")
        m_layout.addWidget(lbl_meta_head)

        # Glyph Name
        lbl_name = QLabel("Symbol Name:")
        self.input_glyph_name = QLineEdit()
        self.input_glyph_name.setPlaceholderText("e.g., Sun, Rad_01, Ka")
        m_layout.addWidget(lbl_name)
        m_layout.addWidget(self.input_glyph_name)

        # Meaning / Gloss
        lbl_meaning = QLabel("Semantic Gloss / Meaning:")
        self.input_meaning = QLineEdit()
        self.input_meaning.setPlaceholderText("e.g., celestial light, day")
        m_layout.addWidget(lbl_meaning)
        m_layout.addWidget(self.input_meaning)

        # Phonetic IPA
        lbl_ipa = QLabel("Phonetic Reading (IPA):")
        ipa_row = QHBoxLayout()
        self.input_ipa = QLineEdit()
        self.input_ipa.setPlaceholderText("e.g., /kʰa/")
        btn_ipa_picker = QPushButton("🔤 IPA")
        btn_ipa_picker.setToolTip("Open IPA Phonetic Helper")
        btn_ipa_picker.setStyleSheet("padding: 5px 8px; font-weight: bold;")
        btn_ipa_picker.clicked.connect(self._open_ipa_picker)
        ipa_row.addWidget(self.input_ipa)
        ipa_row.addWidget(btn_ipa_picker)
        m_layout.addWidget(lbl_ipa)
        m_layout.addLayout(ipa_row)

        # Native Pronunciation Audio
        lbl_audio = QLabel("Pronunciation Audio:")
        m_layout.addWidget(lbl_audio)
        self.audio_widget = GlyphAudioWidget(base_audio_dir=os.path.join(self.data_dir, "audio", "glyphs"))
        m_layout.addWidget(self.audio_widget)

        # External SVG File Importer
        m_layout.addSpacing(8)
        lbl_ext = QLabel("External Assets:")
        btn_import_svg = QPushButton("📂 Import SVG File")
        btn_import_svg.setStyleSheet("padding: 6px 12px; border: 1px solid #cccccc; border-radius: 4px; background: white;")
        btn_import_svg.clicked.connect(self._import_external_svg)
        m_layout.addWidget(lbl_ext)
        m_layout.addWidget(btn_import_svg)

        m_layout.addStretch()
        w_layout.addWidget(self.meta_panel)

        studio_layout.addWidget(workspace)
        self.stack.addWidget(self.studio_widget)

    # Canvas stdio model

    def open_studio_mode(self, glyph: Dict[str, Any], group: Dict[str, Any]):
        """Transition into Canvas Studio Mode for a specific glyph."""
        self.active_glyph_id = glyph["id"]
        self.active_group_id = group["id"]
        self.active_glyph_data = glyph

        # Set breadcrumb
        self.lbl_breadcrumb.setText(f"Groups > {group['name']} > {glyph['name']}")

        # Populate metadata inputs
        self.input_glyph_name.setText(glyph["name"])
        self.input_meaning.setText(glyph.get("meaning", "") or "")
        self.input_ipa.setText(glyph.get("ipa_reading", "") or "")

        # Set canvas strokes
        self.canvas.load_svg(glyph.get("svg_data", "") or "")

        # Set audio
        self.audio_widget.set_glyph(glyph["id"], glyph.get("audio_path", "") or "")

        self.stack.setCurrentIndex(1)

    def _open_ipa_picker(self):
        picker = IPAPickerDialog(target_line_edit=self.input_ipa, parent=self)
        picker.exec()

    def _import_external_svg(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Vector SVG File", "", "Scalable Vector Graphics (*.svg)")
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.canvas.load_svg(content)

    def save_active_glyph(self, notify: bool = True):
        if not self.active_glyph_id:
            return

        name = self.input_glyph_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Glyph Name cannot be empty.")
            return

        meaning = self.input_meaning.text().strip()
        ipa = self.input_ipa.text().strip()
        svg_data = self.canvas.to_svg()
        audio_path = self.audio_widget.current_audio_rel

        # Update in database
        self.glyph_repo.update_glyph(
            self.active_glyph_id,
            name=name,
            meaning=meaning,
            ipa_reading=ipa,
            svg_data=svg_data,
            audio_path=audio_path
        )

        # Also write standalone SVG file into data/images/svg/
        clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name.lower())
        svg_filename = f"{clean_name}_{self.active_glyph_id[:8]}.svg"
        svg_full_path = os.path.join(self.data_dir, "images", "svg", svg_filename)
        try:
            with open(svg_full_path, "w", encoding="utf-8") as f:
                f.write(svg_data)
        except Exception as e:
            print(f"[Glyphs_Page] Error saving standalone SVG: {e}")

        # Update active data
        self.active_glyph_data = self.glyph_repo.get_glyph(self.active_glyph_id)

        if notify:
            QMessageBox.information(self, "Saved", f"Glyph '{name}' saved successfully!")

    def export_active_svg(self):
        svg_data = self.canvas.to_svg()
        name = self.input_glyph_name.text().strip() or "glyph"
        clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', name.lower())
        path, _ = QFileDialog.getSaveFileName(self, "Export Standalone SVG", f"{clean}.svg", "SVG (*.svg)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg_data)
            QMessageBox.information(self, "Exported", f"Exported vector file to:\n{path}")

    def back_to_gallery(self):
        # Auto-save changes
        if self.active_glyph_id:
            self.save_active_glyph(notify=False)
        self.refresh_gallery()
        self.stack.setCurrentIndex(0)

    # Group and Glyph managemert
    def prompt_add_group(self):
        dialog = AddGroupDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, desc = dialog.get_data()
            self.glyph_repo.add_group(self.language_id, name, desc)
            self.refresh_gallery()

    def prompt_edit_group(self, group: Dict[str, Any]):
        dialog = AddGroupDialog(group_name=group["name"], group_desc=group.get("description", ""), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, desc = dialog.get_data()
            self.glyph_repo.update_group(group["id"], name=name, description=desc)
            self.refresh_gallery()

    def confirm_delete_group(self, group_id: str, group_name: str):
        res = QMessageBox.question(
            self, "Delete Group",
            f"Are you sure you want to delete group '{group_name}' and all its glyphs?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self.glyph_repo.delete_group(group_id)
            self.refresh_gallery()

    def create_new_glyph(self, group_id: str, group_name: str):
        # Count existing
        existing = self.glyph_repo.get_glyphs_by_group(group_id)
        default_name = f"Glyph_{len(existing) + 1}"
        
        glyph_id = self.glyph_repo.create_glyph(
            language_id=self.language_id,
            group_id=group_id,
            name=default_name,
            meaning="",
            ipa_reading="",
            svg_data="",
            audio_path=""
        )
        new_glyph = self.glyph_repo.get_glyph(glyph_id)
        group = {"id": group_id, "name": group_name}
        self.open_studio_mode(new_glyph, group)

    def confirm_delete_glyph(self, glyph_id: str, glyph_name: str):
        res = QMessageBox.question(
            self, "Delete Glyph",
            f"Are you sure you want to delete '{glyph_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self.glyph_repo.delete_glyph(glyph_id)
            self.refresh_gallery()

    def _filter_glyphs(self, text: str):
        query = text.strip().lower()
        if not query:
            self.refresh_gallery()
            return
        
        # When filtering, rebuild tiles that match
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        groups = self.glyph_repo.get_groups(self.language_id)
        for group in groups:
            all_glyphs = self.glyph_repo.get_glyphs_by_group(group["id"])
            matched = [
                g for g in all_glyphs
                if query in g["name"].lower()
                or query in (g.get("meaning") or "").lower()
                or query in (g.get("ipa_reading") or "").lower()
            ]
            if matched:
                card = self._create_filtered_group_card(group, matched)
                self.cards_layout.addWidget(card)

    def _create_filtered_group_card(self, group: Dict[str, Any], glyphs: List[Dict[str, Any]]) -> QFrame:
        card = QFrame()
        card.setProperty("class", "group-card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 12)
        card_layout.setSpacing(10)

        header = QFrame()
        header.setObjectName("GroupHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(14, 10, 14, 10)
        lbl_name = QLabel(f"{group['name']} (Filtered: {len(glyphs)} matches)")
        lbl_name.setProperty("class", "group-title")
        h_layout.addWidget(lbl_name)
        h_layout.addStretch()
        card_layout.addWidget(header)

        tiles_container = QWidget()
        grid = QGridLayout(tiles_container)
        grid.setContentsMargins(14, 6, 14, 6)
        grid.setSpacing(12)

        cols = 5
        for idx, glyph in enumerate(glyphs):
            tile = self._create_glyph_tile(glyph, group)
            grid.addWidget(tile, idx // cols, idx % cols)

        card_layout.addWidget(tiles_container)
        return card
