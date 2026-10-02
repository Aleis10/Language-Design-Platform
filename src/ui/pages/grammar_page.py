import os
import json
from typing import Optional, Dict, Any, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFrame, QStackedWidget, QDialog,
    QFormLayout, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QComboBox, QPlainTextEdit,
    QGridLayout, QSpinBox,
)
from PySide6.QtCore import Qt
from digital_keyboard import (
    apply_conlang_to_fields, install_conlang_delegate, track_conlang_widget, ConlangLabel,
)

try:
    from database.grammar_db import GrammarRepository
except ImportError:
    from ..database.grammar_db import GrammarRepository

AFFIX_TYPES = ["prefix", "suffix", "infix", "circumfix", "suprafix", "other"]

class _RuleDialog(QDialog):
    def __init__(self, parent=None, data: Optional[dict] = None, categories: Optional[List[dict]] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Rule" if data else "Add Grammar Rule")
        self.setMinimumWidth(480)
        self.categories = categories or []

        form = QFormLayout(self)

        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("e.g., Plural Marker, Past Tense")
        form.addRow("Rule Name:", self.input_name)

        self.input_pattern = QLineEdit()
        self.input_pattern.setPlaceholderText("e.g., -ya, un-, -en-")
        form.addRow("Affix Pattern:", self.input_pattern)

        self.input_type = QComboBox()
        self.input_type.addItems(AFFIX_TYPES)
        form.addRow("Affix Type:", self.input_type)

        self.input_gloss = QLineEdit()
        self.input_gloss.setPlaceholderText("e.g., PL, PAST, NEG, 1SG")
        form.addRow("Leipzig Gloss Tag:", self.input_gloss)

        self.input_desc = QLineEdit()
        self.input_desc.setPlaceholderText("e.g., marks plural noun forms")
        form.addRow("Description:", self.input_desc)

        self.input_category = QComboBox()
        self.input_category.addItem("(Uncategorized)", None)
        for cat in self.categories:
            self.input_category.addItem(cat["name"], cat["id"])
        form.addRow("Category:", self.input_category)

        btns_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save Rule")
        btn_save.setObjectName("GrammarBtnSave")
        btn_save.clicked.connect(self._validate)
        btns_row.addStretch()
        btns_row.addWidget(btn_cancel)
        btns_row.addWidget(btn_save)
        form.addRow(btns_row)

        if data:
            self.input_name.setText(data.get("name", ""))
            self.input_pattern.setText(data.get("affix_pattern", ""))
            idx_type = self.input_type.findText(data.get("affix_type", "suffix"))
            if idx_type >= 0:
                self.input_type.setCurrentIndex(idx_type)
            self.input_gloss.setText(data.get("gloss_tag", ""))
            self.input_desc.setText(data.get("gloss_description", ""))
            cat_id = data.get("category_id")
            if cat_id:
                idx_cat = self.input_category.findData(cat_id)
                if idx_cat >= 0:
                    self.input_category.setCurrentIndex(idx_cat)
        apply_conlang_to_fields(self, 12)

    def _validate(self):
        if not self.input_name.text().strip():
            QMessageBox.warning(self, "Missing", "Rule name is required.")
            return
        if not self.input_gloss.text().strip():
            QMessageBox.warning(self, "Missing", "Gloss tag is required.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self.input_name.text().strip(),
            "affix_pattern": self.input_pattern.text().strip(),
            "affix_type": self.input_type.currentText(),
            "gloss_tag": self.input_gloss.text().strip(),
            "gloss_description": self.input_desc.text().strip(),
            "category_id": self.input_category.currentData(),
        }

class _CategoryDialog(QDialog):
    def __init__(self, parent=None, data: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Category" if data else "Add Category")
        self.setMinimumWidth(380)

        form = QFormLayout(self)
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("e.g., Noun Classes, Tense, Negation")
        form.addRow("Category Name:", self.input_name)

        self.input_desc = QLineEdit()
        self.input_desc.setPlaceholderText("Optional description")
        form.addRow("Description:", self.input_desc)

        btns_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save Category")
        btn_save.setObjectName("GrammarBtnSave")
        btn_save.clicked.connect(self._validate)
        btns_row.addStretch()
        btns_row.addWidget(btn_cancel)
        btns_row.addWidget(btn_save)
        form.addRow(btns_row)

        if data:
            self.input_name.setText(data.get("name", ""))
            self.input_desc.setText(data.get("description", ""))
        apply_conlang_to_fields(self, 12)

    def _validate(self):
        if not self.input_name.text().strip():
            QMessageBox.warning(self, "Missing", "Category name is required.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self.input_name.text().strip(),
            "description": self.input_desc.text().strip(),
        }

class _ParadigmDialog(QDialog):
    def __init__(self, parent=None, data: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Paradigm" if data else "Add Paradigm Grid")
        self.setMinimumSize(600, 450)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("e.g., Verb Conjugation: To Be")
        form.addRow("Grid Name:", self.input_name)

        self.input_desc = QLineEdit()
        self.input_desc.setPlaceholderText("Optional description")
        form.addRow("Description:", self.input_desc)

        dim_row = QHBoxLayout()
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 20)
        self.spin_cols.setValue(4)
        self.spin_cols.valueChanged.connect(self._rebuild_preview)
        dim_row.addWidget(QLabel("Columns:"))
        dim_row.addWidget(self.spin_cols)

        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 50)
        self.spin_rows.setValue(4)
        self.spin_rows.valueChanged.connect(self._rebuild_preview)
        dim_row.addWidget(QLabel("Rows:"))
        dim_row.addWidget(self.spin_rows)
        dim_row.addStretch()
        form.addRow("Dimensions:", dim_row)

        layout.addLayout(form)

        lbl_hint = QLabel("Fill in the paradigm cells below:")
        lbl_hint.setObjectName("GrammarLabelHint")
        layout.addWidget(lbl_hint)

        self.table = QTableWidget()
        install_conlang_delegate(self.table, 16)
        self.table.setObjectName("GrammarParadigmTable")
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, stretch=1)

        btns_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save Paradigm")
        btn_save.setObjectName("GrammarBtnSave")
        btn_save.clicked.connect(self._validate)
        btns_row.addStretch()
        btns_row.addWidget(btn_cancel)
        btns_row.addWidget(btn_save)
        layout.addLayout(btns_row)

        if data:
            self.input_name.setText(data.get("name", ""))
            self.input_desc.setText(data.get("description", ""))
            hdrs = data.get("headers", [])
            rows = data.get("rows", [])
            if hdrs:
                self.spin_cols.setValue(max(len(hdrs), 1))
            if rows:
                self.spin_rows.setValue(max(len(rows), 1))
            self._rebuild_preview()
            for ci, h in enumerate(hdrs):
                if ci < self.table.columnCount():
                    self.table.setItem(0, ci, QTableWidgetItem(str(h)))
            for ri, row_data in enumerate(rows):
                for ci, cell in enumerate(row_data):
                    if ri + 1 < self.table.rowCount() and ci < self.table.columnCount():
                        self.table.setItem(ri + 1, ci, QTableWidgetItem(str(cell)))
        else:
            self._rebuild_preview()
        apply_conlang_to_fields(self, 12)

    def _rebuild_preview(self):
        cols = self.spin_cols.value()
        rows = self.spin_rows.value()
        self.table.setColumnCount(cols + 1)  # +1 for row-header column
        self.table.setRowCount(rows + 1)     # +1 for header row

        self.table.setItem(0, 0, QTableWidgetItem("Form \\ Feature"))
        for ci in range(cols):
            self.table.setItem(0, ci + 1, QTableWidgetItem(f"Col {ci + 1}"))
        for ri in range(rows):
            self.table.setItem(ri + 1, 0, QTableWidgetItem(f"Row {ri + 1}"))

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)

    def _validate(self):
        if not self.input_name.text().strip():
            QMessageBox.warning(self, "Missing", "Grid name is required.")
            return
        self.accept()

    def get_data(self) -> dict:
        cols = self.spin_cols.value()
        rows = self.spin_rows.value()
        headers = []
        for ci in range(cols):
            item = self.table.item(0, ci + 1)
            headers.append(item.text().strip() if item and item.text().strip() else f"Col {ci + 1}")
        grid_rows = []
        for ri in range(rows):
            row_data = []
            for ci in range(cols):
                item = self.table.item(ri + 1, ci + 1)
                row_data.append(item.text().strip() if item else "")
            grid_rows.append(row_data)
        return {
            "name": self.input_name.text().strip(),
            "description": self.input_desc.text().strip(),
            "headers": ["Form \\ Feature"] + headers,
            "rows": grid_rows,
        }

class _TemplateDialog(QDialog):
    def __init__(self, parent=None, data: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Template" if data else "Add Phrase Template")
        self.setMinimumWidth(480)

        form = QFormLayout(self)
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("e.g., Past Tense Declarative")
        form.addRow("Template Name:", self.input_name)

        self.input_pattern = QLineEdit()
        self.input_pattern.setPlaceholderText("e.g., S-O-V  or  AUX-ROOT-SUF-OBJ")
        form.addRow("Word Order / Pattern:", self.input_pattern)

        self.input_gloss = QLineEdit()
        self.input_gloss.setPlaceholderText("e.g., SBJ-OBJ-PRS-VERB")
        form.addRow("Gloss Pattern:", self.input_gloss)

        self.input_translation = QLineEdit()
        self.input_translation.setPlaceholderText("e.g., The man sees the woman")
        form.addRow("Example Translation:", self.input_translation)

        self.input_notes = QPlainTextEdit()
        self.input_notes.setPlaceholderText("Notes about usage, register, dialectal variation...")
        self.input_notes.setFixedHeight(70)
        form.addRow("Notes:", self.input_notes)

        btns_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save Template")
        btn_save.setObjectName("GrammarBtnSave")
        btn_save.clicked.connect(self._validate)
        btns_row.addStretch()
        btns_row.addWidget(btn_cancel)
        btns_row.addWidget(btn_save)
        form.addRow(btns_row)

        if data:
            self.input_name.setText(data.get("name", ""))
            self.input_pattern.setText(data.get("pattern", ""))
            self.input_gloss.setText(data.get("gloss", ""))
            self.input_translation.setText(data.get("translation", ""))
            self.input_notes.setPlainText(data.get("notes", ""))
        apply_conlang_to_fields(self, 12)

    def _validate(self):
        if not self.input_name.text().strip():
            QMessageBox.warning(self, "Missing", "Template name is required.")
            return
        if not self.input_pattern.text().strip():
            QMessageBox.warning(self, "Missing", "Pattern is required.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self.input_name.text().strip(),
            "pattern": self.input_pattern.text().strip(),
            "gloss": self.input_gloss.text().strip(),
            "translation": self.input_translation.text().strip(),
            "notes": self.input_notes.toPlainText().strip(),
        }

class GrammarPage(QWidget):
    def __init__(self, grammar_repo: GrammarRepository, language_id: str, parent=None):
        super().__init__(parent)
        self.grammar_repo = grammar_repo
        self.language_id = language_id
        self._current_category_filter: Optional[str] = None

        self._build_ui()
        self._load_stylesheet()
        self.refresh_rules()
        self.refresh_paradigms()
        self.refresh_templates()
        apply_conlang_to_fields(self, 12)

    def _load_stylesheet(self):
        style_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style", "grammar_page.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tab_bar = QWidget()
        tab_bar.setObjectName("GrammarTabBar")
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(20, 10, 20, 0)
        tab_layout.setSpacing(0)

        self._tab_buttons: list[QPushButton] = []
        tab_labels = ["Affix Rules", "Paradigm Grids", "Phrase Templates"]
        for i, label in enumerate(tab_labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            tab_layout.addWidget(btn)
            self._tab_buttons.append(btn)
        tab_layout.addStretch()
        root.addWidget(tab_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #e0e0e0;")
        root.addWidget(sep)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, stretch=1)

        self._build_rules_tab()
        self._build_paradigms_tab()
        self._build_templates_tab()

    def _switch_tab(self, idx: int):
        for i, btn in enumerate(self._tab_buttons):
            btn.setChecked(i == idx)
        self.stack.setCurrentIndex(idx)

    def _build_rules_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("GrammarTopBar")
        top = QHBoxLayout(top_bar)
        top.setContentsMargins(20, 12, 20, 12)
        top.setSpacing(12)

        lbl = QLabel("Affix & Grammar Rules")
        lbl.setObjectName("GrammarTitle")
        top.addWidget(lbl)
        top.addSpacing(12)

        btn_add_cat = QPushButton("+ Category")
        btn_add_cat.setObjectName("GrammarBtnAdd")
        btn_add_cat.clicked.connect(self._add_category)
        top.addWidget(btn_add_cat)

        btn_add = QPushButton("+ Add Rule")
        btn_add.setObjectName("GrammarBtnAdd")
        btn_add.clicked.connect(self._add_rule)
        top.addWidget(btn_add)

        btn_edit = QPushButton("Edit")
        btn_edit.clicked.connect(self._edit_rule)
        top.addWidget(btn_edit)

        btn_delete = QPushButton("Delete")
        btn_delete.setObjectName("GrammarBtnDelete")
        btn_delete.clicked.connect(self._delete_rule)
        top.addWidget(btn_delete)

        top.addStretch()

        lbl_filter = QLabel("Filter:")
        lbl_filter.setStyleSheet("font-size: 12px; color: #666666;")
        top.addWidget(lbl_filter)

        self.combo_category_filter = QComboBox()
        self.combo_category_filter.setMinimumWidth(160)
        self.combo_category_filter.currentIndexChanged.connect(self._on_category_filter_changed)
        top.addWidget(self.combo_category_filter)

        layout.addWidget(top_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(12)

        hint = QLabel("Organize grammar rules by category. Used by the interlinear parser for morphological stripping.")
        hint.setObjectName("GrammarHint")
        body_layout.addWidget(hint)

        self.categories_scroll = QScrollArea()
        self.categories_scroll.setObjectName("GrammarScroll")
        self.categories_scroll.setWidgetResizable(True)
        self.categories_container = QWidget()
        self.categories_layout = QVBoxLayout(self.categories_container)
        self.categories_layout.setContentsMargins(0, 0, 0, 0)
        self.categories_layout.setSpacing(10)
        self.categories_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.categories_scroll.setWidget(self.categories_container)
        body_layout.addWidget(self.categories_scroll, stretch=1)

        self.rules_table = QTableWidget()
        install_conlang_delegate(self.rules_table, 16)
        self.rules_table.setObjectName("GrammarRulesTable")
        self.rules_table.setColumnCount(7)
        self.rules_table.setHorizontalHeaderLabels([
            "Name", "Pattern", "Type", "Gloss Tag", "Description", "Category", "ID"
        ])
        self.rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.rules_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.rules_table.setAlternatingRowColors(True)
        self.rules_table.verticalHeader().setVisible(False)
        self.rules_table.setColumnHidden(6, True)
        body_layout.addWidget(self.rules_table, stretch=2)

        self.lbl_rules_count = QLabel("0 rules")
        self.lbl_rules_count.setObjectName("GrammarCount")
        body_layout.addWidget(self.lbl_rules_count)

        layout.addWidget(body, stretch=1)
        self.stack.addWidget(page)

    def _build_paradigms_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("GrammarTopBar")
        top = QHBoxLayout(top_bar)
        top.setContentsMargins(20, 12, 20, 12)
        top.setSpacing(12)

        lbl = QLabel("Paradigm Grids")
        lbl.setObjectName("GrammarTitle")
        top.addWidget(lbl)
        top.addSpacing(12)

        btn_add = QPushButton("+ Add Grid")
        btn_add.setObjectName("GrammarBtnAdd")
        btn_add.clicked.connect(self._add_paradigm)
        top.addWidget(btn_add)

        btn_edit = QPushButton("Edit")
        btn_edit.clicked.connect(self._edit_paradigm)
        top.addWidget(btn_edit)

        btn_delete = QPushButton("Delete")
        btn_delete.setObjectName("GrammarBtnDelete")
        btn_delete.clicked.connect(self._delete_paradigm)
        top.addWidget(btn_delete)

        top.addStretch()
        layout.addWidget(top_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(12)

        hint = QLabel("Build morphological paradigm tables (verb conjugations, noun declensions, etc.)")
        hint.setObjectName("GrammarHint")
        body_layout.addWidget(hint)

        self.paradigms_scroll = QScrollArea()
        self.paradigms_scroll.setObjectName("GrammarScroll")
        self.paradigms_scroll.setWidgetResizable(True)
        self.paradigms_container = QWidget()
        self.paradigms_layout = QVBoxLayout(self.paradigms_container)
        self.paradigms_layout.setContentsMargins(0, 0, 0, 0)
        self.paradigms_layout.setSpacing(16)
        self.paradigms_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.paradigms_scroll.setWidget(self.paradigms_container)
        body_layout.addWidget(self.paradigms_scroll, stretch=1)

        layout.addWidget(body, stretch=1)
        self.stack.addWidget(page)

    def _build_templates_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("GrammarTopBar")
        top = QHBoxLayout(top_bar)
        top.setContentsMargins(20, 12, 20, 12)
        top.setSpacing(12)

        lbl = QLabel("Phrase Templates")
        lbl.setObjectName("GrammarTitle")
        top.addWidget(lbl)
        top.addSpacing(12)

        btn_add = QPushButton("+ Add Template")
        btn_add.setObjectName("GrammarBtnAdd")
        btn_add.clicked.connect(self._add_template)
        top.addWidget(btn_add)

        btn_edit = QPushButton("Edit")
        btn_edit.clicked.connect(self._edit_template)
        top.addWidget(btn_edit)

        btn_delete = QPushButton("Delete")
        btn_delete.setObjectName("GrammarBtnDelete")
        btn_delete.clicked.connect(self._delete_template)
        top.addWidget(btn_delete)

        top.addStretch()
        layout.addWidget(top_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(12)

        hint = QLabel("Document sentence patterns, word order templates, and interlinear gloss structures.")
        hint.setObjectName("GrammarHint")
        body_layout.addWidget(hint)

        self.templates_table = QTableWidget()
        install_conlang_delegate(self.templates_table, 16)
        self.templates_table.setObjectName("GrammarTemplatesTable")
        self.templates_table.setColumnCount(6)
        self.templates_table.setHorizontalHeaderLabels([
            "Name", "Pattern", "Gloss", "Translation", "Notes", "ID"
        ])
        self.templates_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.templates_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.templates_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.templates_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.templates_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.templates_table.setAlternatingRowColors(True)
        self.templates_table.verticalHeader().setVisible(False)
        self.templates_table.setColumnHidden(5, True)
        body_layout.addWidget(self.templates_table, stretch=1)

        self.lbl_templates_count = QLabel("0 templates")
        self.lbl_templates_count.setObjectName("GrammarCount")
        body_layout.addWidget(self.lbl_templates_count)

        layout.addWidget(body, stretch=1)
        self.stack.addWidget(page)

    def refresh_rules(self):
        self._refresh_category_filter()
        self._refresh_rules_table()
        self._refresh_category_cards()

    def _refresh_category_filter(self):
        categories = self.grammar_repo.get_categories(self.language_id)
        self.combo_category_filter.blockSignals(True)
        prev = self.combo_category_filter.currentData()
        self.combo_category_filter.clear()
        self.combo_category_filter.addItem("All Rules", None)
        for cat in categories:
            self.combo_category_filter.addItem(cat["name"], cat["id"])
        if prev:
            idx = self.combo_category_filter.findData(prev)
            if idx >= 0:
                self.combo_category_filter.setCurrentIndex(idx)
        self.combo_category_filter.blockSignals(False)

    def _refresh_rules_table(self):
        rules = self.grammar_repo.get_rules(self.language_id, self._current_category_filter)
        categories = {c["id"]: c["name"] for c in self.grammar_repo.get_categories(self.language_id)}

        self.rules_table.setRowCount(len(rules))
        for ri, rule in enumerate(rules):
            self.rules_table.setItem(ri, 0, QTableWidgetItem(rule.get("name", "")))
            affix_item = QTableWidgetItem(rule.get("affix_pattern", ""))
            gloss_item = QTableWidgetItem(rule.get("gloss_tag", ""))
            self.rules_table.setItem(ri, 1, affix_item)
            self.rules_table.setItem(ri, 2, QTableWidgetItem(rule.get("affix_type", "")))
            self.rules_table.setItem(ri, 3, gloss_item)
            self.rules_table.setItem(ri, 4, QTableWidgetItem(rule.get("gloss_description", "")))
            cat_name = categories.get(rule.get("category_id"), "—")
            self.rules_table.setItem(ri, 5, QTableWidgetItem(cat_name))
            self.rules_table.setItem(ri, 6, QTableWidgetItem(rule.get("id", "")))
        self.lbl_rules_count.setText(f"{len(rules)} rule{'s' if len(rules) != 1 else ''}")

    def _refresh_category_cards(self):
        while self.categories_layout.count():
            item = self.categories_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        categories = self.grammar_repo.get_categories(self.language_id)
        if not categories:
            empty = QLabel("No categories yet. Use '+ Category' to organize rules.")
            empty.setStyleSheet("color: #999999; font-size: 12px; padding: 8px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.categories_layout.addWidget(empty)
            return

        for cat in categories:
            card = QFrame()
            card.setProperty("class", "GrammarCategoryCard")
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            card_layout.setSpacing(10)

            rules_in_cat = self.grammar_repo.get_rules(self.language_id, cat["id"])
            count_badge = QLabel(f"{len(rules_in_cat)}")
            count_badge.setObjectName("GrammarCatBadge")
            card_layout.addWidget(count_badge)

            name_lbl = ConlangLabel(cat["name"])
            name_lbl.setObjectName("GrammarCatName")
            card_layout.addWidget(name_lbl)

            if cat.get("description"):
                desc_lbl = ConlangLabel(cat["description"])
                desc_lbl.setObjectName("GrammarCatDesc")
                card_layout.addWidget(desc_lbl)

            card_layout.addStretch()

            btn_edit = QPushButton("Edit")
            btn_edit.setObjectName("GrammarCatBtn")
            btn_edit.clicked.connect(lambda _, c=cat: self._edit_category(c))
            card_layout.addWidget(btn_edit)

            btn_del = QPushButton("Delete")
            btn_del.setObjectName("GrammarBtnDelete")
            btn_del.clicked.connect(lambda _, c=cat: self._delete_category(c))
            card_layout.addWidget(btn_del)

            self.categories_layout.addWidget(card)

    def refresh_paradigms(self):
        while self.paradigms_layout.count():
            item = self.paradigms_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        paradigms = self.grammar_repo.get_paradigms(self.language_id)
        if not paradigms:
            empty = QLabel("No paradigm grids yet. Use '+ Add Grid' to create verb conjugation or noun declension tables.")
            empty.setStyleSheet("color: #999999; font-size: 12px; padding: 8px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.paradigms_layout.addWidget(empty)
            return

        for grid in paradigms:
            card = QFrame()
            card.setProperty("class", "GrammarParadigmCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 12, 12, 12)
            card_layout.setSpacing(8)

            header = QHBoxLayout()
            title_lbl = ConlangLabel(grid["name"])
            title_lbl.setObjectName("GrammarParadigmTitle")
            header.addWidget(title_lbl)

            if grid.get("description"):
                desc_lbl = ConlangLabel(grid["description"])
                desc_lbl.setObjectName("GrammarParadigmDesc")
                header.addWidget(desc_lbl)

            header.addStretch()

            card.setProperty("paradigm_id", grid["id"])

            card_layout.addLayout(header)

            headers = grid.get("headers", [])
            rows = grid.get("rows", [])
            if headers:
                tbl = QTableWidget(len(rows) + 1, len(headers))
                install_conlang_delegate(tbl, 16)
                tbl.setObjectName("GrammarParadigmTable")
                tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                tbl.verticalHeader().setVisible(False)
                tbl.setAlternatingRowColors(True)

                for ci, h in enumerate(headers):
                    tbl.setItem(0, ci, QTableWidgetItem(str(h)))

                for ri, row_data in enumerate(rows):
                    for ci, cell in enumerate(row_data):
                        tbl.setItem(ri + 1, ci, QTableWidgetItem(str(cell)))

                tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                tbl.setMinimumHeight(min(len(rows) + 2, 12) * 32)
                card_layout.addWidget(tbl)

            self.paradigms_layout.addWidget(card)

    def refresh_templates(self):
        templates = self.grammar_repo.get_templates(self.language_id)
        self.templates_table.setRowCount(len(templates))
        for ri, tpl in enumerate(templates):
            self.templates_table.setItem(ri, 0, QTableWidgetItem(tpl.get("name", "")))
            t_item = QTableWidgetItem(tpl.get("pattern", ""))
            g_item = QTableWidgetItem(tpl.get("gloss", ""))
            translation_item = QTableWidgetItem(tpl.get("translation", ""))
            tbl = self.templates_table
            tbl.setItem(ri, 1, t_item)
            tbl.setItem(ri, 2, g_item)
            tbl.setItem(ri, 3, translation_item)
            self.templates_table.setItem(ri, 4, QTableWidgetItem(tpl.get("notes", "")))
            self.templates_table.setItem(ri, 5, QTableWidgetItem(tpl.get("id", "")))
        self.lbl_templates_count.setText(f"{len(templates)} template{'s' if len(templates) != 1 else ''}")

    def _on_category_filter_changed(self):
        self._current_category_filter = self.combo_category_filter.currentData()
        self._refresh_rules_table()

    def _selected_rule_id(self) -> Optional[str]:
        rows = self.rules_table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.rules_table.item(rows[0].row(), 6).text()

    def _selected_template_id(self) -> Optional[str]:
        rows = self.templates_table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.templates_table.item(rows[0].row(), 5).text()

    def _selected_paradigm_id(self) -> Optional[str]:
        rows = self.paradigms_scroll.widget().findChildren(QFrame)
        for card in self.paradigms_container.findChildren(QFrame):
            if card.property("paradigm_id") and card.property("paradigm_id") != "":
                tables = card.findChildren(QTableWidget)
                for tbl in tables:
                    if tbl.selectionModel().selectedRows():
                        return card.property("paradigm_id")
        return None

    def _add_rule(self):
        categories = self.grammar_repo.get_categories(self.language_id)
        dlg = _RuleDialog(self, categories=categories)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.grammar_repo.add_rule(
                language_id=self.language_id,
                name=data["name"],
                gloss_tag=data["gloss_tag"],
                category_id=data["category_id"],
                affix_pattern=data["affix_pattern"],
                affix_type=data["affix_type"],
                gloss_description=data["gloss_description"],
            )
            self.refresh_rules()

    def _edit_rule(self):
        rule_id = self._selected_rule_id()
        if not rule_id:
            QMessageBox.information(self, "No selection", "Select a rule to edit.")
            return
        rule = self.grammar_repo.get_rule(rule_id)
        if not rule:
            return
        categories = self.grammar_repo.get_categories(self.language_id)
        dlg = _RuleDialog(self, data=rule, categories=categories)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.grammar_repo.update_rule(
                rule_id,
                name=data["name"],
                gloss_tag=data["gloss_tag"],
                category_id=data["category_id"],
                affix_pattern=data["affix_pattern"],
                affix_type=data["affix_type"],
                gloss_description=data["gloss_description"],
            )
            self.refresh_rules()

    def _delete_rule(self):
        rule_id = self._selected_rule_id()
        if not rule_id:
            QMessageBox.information(self, "No selection", "Select a rule to delete.")
            return
        res = QMessageBox.question(
            self, "Delete Rule", "Delete this grammar rule?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self.grammar_repo.delete_rule(rule_id)
            self.refresh_rules()

    def _add_category(self):
        dlg = _CategoryDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            cats = self.grammar_repo.get_categories(self.language_id)
            self.grammar_repo.add_category(
                self.language_id,
                name=data["name"],
                description=data["description"],
                position=len(cats),
            )
            self.refresh_rules()

    def _edit_category(self, cat: dict):
        dlg = _CategoryDialog(self, data=cat)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.grammar_repo.update_category(cat["id"], name=data["name"], description=data["description"])
            self.refresh_rules()

    def _delete_category(self, cat: dict):
        res = QMessageBox.question(
            self, "Delete Category",
            f"Delete category '{cat['name']}'? Rules in this category will become uncategorized.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self.grammar_repo.delete_category(cat["id"])
            self.refresh_rules()

    def _add_paradigm(self):
        dlg = _ParadigmDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            grids = self.grammar_repo.get_paradigms(self.language_id)
            self.grammar_repo.add_paradigm(
                language_id=self.language_id,
                name=data["name"],
                description=data["description"],
                headers=data["headers"],
                rows=data["rows"],
                position=len(grids),
            )
            self.refresh_paradigms()

    def _edit_paradigm(self):
        grid_id = self._selected_paradigm_id()
        if not grid_id:
            QMessageBox.information(self, "No selection", "Click a paradigm grid table to select it, then click Edit.")
            return
        paradigms = self.grammar_repo.get_paradigms(self.language_id)
        grid_data = None
        for p in paradigms:
            if p["id"] == grid_id:
                grid_data = p
                break
        if not grid_data:
            return
        dlg = _ParadigmDialog(self, data=grid_data)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.grammar_repo.update_paradigm(
                grid_id,
                name=data["name"],
                description=data["description"],
                headers=data["headers"],
                rows=data["rows"],
            )
            self.refresh_paradigms()

    def _delete_paradigm(self):
        grid_id = self._selected_paradigm_id()
        if not grid_id:
            QMessageBox.information(self, "No selection", "Click a paradigm grid to select it, then click Delete.")
            return
        res = QMessageBox.question(
            self, "Delete Paradigm", "Delete this paradigm grid?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self.grammar_repo.delete_paradigm(grid_id)
            self.refresh_paradigms()

    def _add_template(self):
        dlg = _TemplateDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            templates = self.grammar_repo.get_templates(self.language_id)
            self.grammar_repo.add_template(
                language_id=self.language_id,
                name=data["name"],
                pattern=data["pattern"],
                gloss=data["gloss"],
                translation=data["translation"],
                notes=data["notes"],
                position=len(templates),
            )
            self.refresh_templates()

    def _edit_template(self):
        tpl_id = self._selected_template_id()
        if not tpl_id:
            QMessageBox.information(self, "No selection", "Select a template to edit.")
            return
        row = None
        for ri in range(self.templates_table.rowCount()):
            item = self.templates_table.item(ri, 5)
            if item and item.text() == tpl_id:
                row = ri
                break
        if row is None:
            return
        data = {
            "name": self.templates_table.item(row, 0).text() if self.templates_table.item(row, 0) else "",
            "pattern": self.templates_table.item(row, 1).text() if self.templates_table.item(row, 1) else "",
            "gloss": self.templates_table.item(row, 2).text() if self.templates_table.item(row, 2) else "",
            "translation": self.templates_table.item(row, 3).text() if self.templates_table.item(row, 3) else "",
            "notes": self.templates_table.item(row, 4).text() if self.templates_table.item(row, 4) else "",
        }
        dlg = _TemplateDialog(self, data=data)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_data = dlg.get_data()
            self.grammar_repo.update_template(tpl_id, **new_data)
            self.refresh_templates()

    def _delete_template(self):
        tpl_id = self._selected_template_id()
        if not tpl_id:
            QMessageBox.information(self, "No selection", "Select a template to delete.")
            return
        res = QMessageBox.question(
            self, "Delete Template", "Delete this phrase template?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self.grammar_repo.delete_template(tpl_id)
            self.refresh_templates()
