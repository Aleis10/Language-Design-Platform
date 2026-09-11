import json
from PySide6.QtWidgets import (
    QWidget, QTextEdit, QComboBox, QLineEdit, QVBoxLayout, QHBoxLayout, QFrame, QPushButton,
    QLabel, QScrollArea, QFormLayout, QMessageBox, QDialog, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon


class Overview_Page(QWidget):
    def __init__(self, overview_repo=None, language_id=None, parent=None):
        super().__init__(parent)
        self.overview_repo = overview_repo
        self.language_id = language_id
        self.custom_cards = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sticky Top Bar
        top_bar_widget = QWidget()
        top_bar_widget.setObjectName("StickyTopBar")
        top_bar = QHBoxLayout(top_bar_widget)
        top_bar.setContentsMargins(24, 16, 24, 16)

        status_label = QLabel("Project Status:")
        self.status_combo = QComboBox()
        self.status_combo.setObjectName("StatusCombo")
        self.status_combo.setEditable(True)
        self.status_combo.addItems(["Drafting", "Active / In Development", "Stable / Complete", "Archived"])

        self.btn_save = QPushButton("Save Overview")
        self.btn_save.setObjectName("BtnSaveOverview")
        self.btn_save.setStyleSheet("""
            QPushButton#BtnSaveOverview {
                background-color: #28a745;
                color: #ffffff;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 6px;
                border: none;
            }
            QPushButton#BtnSaveOverview:hover {
                background-color: #218838;
            }
        """)
        self.btn_save.clicked.connect(self.save_data)

        self.btn_add_section = QPushButton("+ Add Custom Section")
        self.btn_add_section.setObjectName("BtnAddSection")
        self.btn_add_section.clicked.connect(self.prompt_add_section)

        top_bar.addWidget(status_label)
        top_bar.addWidget(self.status_combo)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_save)
        top_bar.addWidget(self.btn_add_section)

        main_layout.addWidget(top_bar_widget, stretch=0)

        # Scrollable Container
        scroll_area = QScrollArea()
        scroll_area.setObjectName("OverviewScrollArea")
        scroll_area.setWidgetResizable(True)

        self.content_widget = QWidget()
        self.cards_layout = QVBoxLayout(self.content_widget)
        self.cards_layout.setContentsMargins(24, 20, 24, 24)
        self.cards_layout.setSpacing(16)

        # Section 1: Language Details
        details_card = QFrame()
        details_card.setProperty("class", "overview-card")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(16, 16, 16, 16)

        sec1_title = QLabel("Language Details")
        sec1_title.setProperty("class", "section-title")
        details_layout.addWidget(sec1_title)

        grid_layout = QHBoxLayout()
        col1 = QFormLayout()
        col2 = QFormLayout()

        self.input_exonym = QLineEdit()
        self.input_exonym.setPlaceholderText("e.g. English")
        self.input_endonym = QLineEdit()
        self.input_endonym.setPlaceholderText("e.g. Quenya")
        self.input_code = QLineEdit()
        self.input_code.setPlaceholderText("e.g. QYA")
        self.input_demonym = QLineEdit()
        self.input_demonym.setPlaceholderText("e.g. Global")

        col1.addRow("English Name (Exonym):", self.input_exonym)
        col1.addRow("Native Name (Endonym):", self.input_endonym)
        col1.addRow("Language Code / Abbr:", self.input_code)
        col1.addRow("Speaker Demonym:", self.input_demonym)

        self.input_pop = QLineEdit()
        self.input_pop.setPlaceholderText("e.g. 50,000 native speakers")
        self.input_family = QLineEdit()
        self.input_family.setPlaceholderText("Demo Family")

        self.combo_word_order = QComboBox()
        self.combo_word_order.setEditable(True)
        self.combo_word_order.addItems(["SVO", "SOV", "VSO", "VOS", "OSV", "OVS", "Free Word Order"])

        self.combo_morphology = QComboBox()
        self.combo_morphology.setEditable(True)
        self.combo_morphology.addItems(["Agglutinative", "Isolating", "Fusional", "Polysynthetic"])

        self.combo_script = QComboBox()
        self.combo_script.setEditable(True)
        self.combo_script.addItems(["Alphabet", "Abugida", "Abjad", "Logographic", "Unwritten / Oral"])

        col2.addRow("Speaker Population:", self.input_pop)
        col2.addRow("Language Family:", self.input_family)
        col2.addRow("Canonical Word Order:", self.combo_word_order)
        col2.addRow("Morphological Type:", self.combo_morphology)
        col2.addRow("Primary Script System:", self.combo_script)

        grid_layout.addLayout(col1, stretch=1)
        grid_layout.addSpacing(20)
        grid_layout.addLayout(col2, stretch=1)

        details_layout.addLayout(grid_layout)
        self.cards_layout.addWidget(details_card)

        # Section 2: History Section
        history_card = QFrame()
        history_card.setProperty("class", "overview-card")
        h_layout = QVBoxLayout(history_card)
        h_layout.setContentsMargins(16, 12, 16, 12)
        h_title = QLabel("History & Origins")
        h_title.setProperty("class", "section-title")
        self.text_history = AutoResizingTextEdit()
        self.text_history.setPlaceholderText("Describe the historical origins and evolution of the language...")
        self.text_history.setMaximumHeight(100)
        h_layout.addWidget(h_title)
        h_layout.addWidget(self.text_history)
        self.cards_layout.addWidget(history_card)

        # Section 3: Culture & Usage
        culture_card = QFrame()
        culture_card.setProperty("class", "overview-card")
        c_layout = QVBoxLayout(culture_card)
        c_layout.setContentsMargins(16, 12, 16, 12)
        c_title = QLabel("Cultural Background & Usage")
        c_title.setProperty("class", "section-title")
        self.text_culture = AutoResizingTextEdit()
        self.text_culture.setPlaceholderText("Describe cultural context, registers, societal usage, or idioms...")
        self.text_culture.setMaximumHeight(100)
        c_layout.addWidget(c_title)
        c_layout.addWidget(self.text_culture)
        self.cards_layout.addWidget(culture_card)

        self.cards_layout.addStretch()

        scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(scroll_area, stretch=1)

        # Load persisted database values if available
        self.load_data()

    def load_data(self):
        """Populates UI fields from the database."""
        if not self.overview_repo or not self.language_id:
            return

        data = self.overview_repo.get_overview_data(self.language_id)
        if data:
            if data.get("exonym"):
                self.input_exonym.setText(data["exonym"])
            if data.get("autonym"):
                self.input_endonym.setText(data["autonym"])
            if data.get("language_code"):
                self.input_code.setText(data["language_code"])
            if data.get("demonym"):
                self.input_demonym.setText(data["demonym"])
            if data.get("speaker_population"):
                self.input_pop.setText(data["speaker_population"])
            if data.get("genetic_classification"):
                self.input_family.setText(data["genetic_classification"])
            if data.get("word_order"):
                self.combo_word_order.setCurrentText(data["word_order"])
            if data.get("morphology"):
                self.combo_morphology.setCurrentText(data["morphology"])
            if data.get("script_system"):
                self.combo_script.setCurrentText(data["script_system"])
            if data.get("status"):
                self.status_combo.setCurrentText(data["status"])
            if data.get("history"):
                self.text_history.setPlainText(data["history"])
            if data.get("cultural_context"):
                self.text_culture.setPlainText(data["cultural_context"])

        # Load custom sections
        sections = self.overview_repo.get_custom_sections(self.language_id)
        for sec in sections:
            self._add_card_widget(
                title=sec["title"],
                card_type_idx=sec.get("section_type", 0),
                section_id=sec["id"],
                initial_content=sec.get("content", "")
            )

    def save_data(self):
        """Saves overview fields and custom sections back to the database."""
        if not self.overview_repo or not self.language_id:
            return

        payload = {
            "exonym": self.input_exonym.text().strip(),
            "autonym": self.input_endonym.text().strip(),
            "language_code": self.input_code.text().strip(),
            "demonym": self.input_demonym.text().strip(),
            "speaker_population": self.input_pop.text().strip(),
            "genetic_classification": self.input_family.text().strip(),
            "word_order": self.combo_word_order.currentText().strip(),
            "morphology": self.combo_morphology.currentText().strip(),
            "script_system": self.combo_script.currentText().strip(),
            "history": self.text_history.toPlainText().strip(),
            "cultural_context": self.text_culture.toPlainText().strip(),
            "status": self.status_combo.currentText().strip(),
        }
        self.overview_repo.save_overview_data(self.language_id, payload)

        for card in self.custom_cards:
            card.save_card_content()

    def _add_card_widget(self, title: str, card_type_idx: int, section_id: str = None, initial_content: str = ""):
        stretch_item = self.cards_layout.itemAt(self.cards_layout.count() - 1)
        if stretch_item and stretch_item.spacerItem():
            self.cards_layout.removeItem(stretch_item)

        new_card = Custom_Card(
            title=title,
            card_type_idx=card_type_idx,
            section_id=section_id,
            initial_content=initial_content,
            overview_repo=self.overview_repo,
            on_delete_callback=self._remove_card_widget
        )
        self.custom_cards.append(new_card)
        self.cards_layout.addWidget(new_card)
        self.cards_layout.addStretch()

    def _remove_card_widget(self, card):
        if card in self.custom_cards:
            self.custom_cards.remove(card)

    def prompt_add_section(self):
        dialog = Custom_Section_Dialog(self)
        if dialog.exec():
            title, type_idx = dialog.get_data()
            if title:
                section_id = None
                if self.overview_repo and self.language_id:
                    position = len(self.custom_cards)
                    section_id = self.overview_repo.add_custom_section(
                        language_id=self.language_id,
                        title=title,
                        section_type=type_idx,
                        content="",
                        position=position
                    )
                self._add_card_widget(title, type_idx, section_id=section_id)


class Custom_Section_Dialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Custom Section")
        self.setMinimumWidth(360)
        
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("e.g., Dialects, Honorifics, Proverbs...")

        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "Rich Text Box (Multi-line)",
            "Short Property Field (Single-line)",
            "Tag / List Box (Items/List)"
        ])

        form_layout.addRow("Section Title:", self.title_input)
        form_layout.addRow("Section Type:", self.type_combo)
        layout.addLayout(form_layout)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_ok = QPushButton("Add Section")
        self.btn_ok.setObjectName("BtnAddSection")
        self.btn_ok.clicked.connect(self.accept)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)

    def get_data(self):
        return self.title_input.text().strip(), self.type_combo.currentIndex()


class Custom_Card(QFrame):
    def __init__(self, title: str, card_type_idx: int, section_id: str = None,
                 initial_content: str = "", overview_repo=None, on_delete_callback=None):
        super().__init__()
        self.card_type_idx = card_type_idx
        self.section_id = section_id
        self.overview_repo = overview_repo
        self.on_delete_callback = on_delete_callback
        self.is_collapsed = False

        self.setProperty("class", "overview-card")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 12, 16, 12)

        # Card Header
        header_layout = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setProperty("class", "section-title")

        # Header (Rename, Collapse & Delete)
        self.btn_rename = QPushButton()
        self.btn_rename.setIcon(QIcon("/home/pranav/Documents/Collage_R/code/Python/Lexicography/Language-Design-Platform/assets/icons/edit.svg"))
        self.btn_collapse = QPushButton("▼")
        self.btn_delete = QPushButton()
        self.btn_delete.setIcon(QIcon("/home/pranav/Documents/Collage_R/code/Python/Lexicography/Language-Design-Platform/assets/icons/Trash.svg"))

        for btn in (self.btn_rename, self.btn_collapse, self.btn_delete):
            btn.setFixedSize(28, 28)
            btn.setProperty("class", "card-control-btn")

        self.btn_rename.clicked.connect(self.rename_card)
        self.btn_collapse.clicked.connect(self.toggle_collapse)
        self.btn_delete.clicked.connect(self.delete_card)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_rename)
        header_layout.addWidget(self.btn_collapse)
        header_layout.addWidget(self.btn_delete)
        self.main_layout.addLayout(header_layout)

        # Content Body 
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 6, 0, 0)

        if card_type_idx == 0:  # Rich Text Area
            self.input_field = AutoResizingTextEdit(f"Enter details for {title}...")
            if initial_content:
                self.input_field.setPlainText(initial_content)
            self.input_field.textChanged.connect(self.save_card_content)
            content_layout.addWidget(self.input_field)

        elif card_type_idx == 1:  # Single Line Input
            self.input_field = QLineEdit()
            self.input_field.setPlaceholderText(f"Enter {title}...")
            if initial_content:
                self.input_field.setText(initial_content)
            self.input_field.textChanged.connect(self.save_card_content)
            content_layout.addWidget(self.input_field)

        elif card_type_idx == 2:  # List Box
            list_controls = QHBoxLayout()
            self.item_input = QLineEdit()
            self.item_input.setPlaceholderText("Add item (e.g. dialect name, proverb)...")
            self.btn_add_item = QPushButton("+ Add")
            self.btn_add_item.setObjectName("BtnAddListItem")
            
            list_controls.addWidget(self.item_input)
            list_controls.addWidget(self.btn_add_item)

            self.list_widget = AutoResizingList()

            if initial_content:
                try:
                    items = json.loads(initial_content)
                    for it in items:
                        self.list_widget.addItem(QListWidgetItem(str(it)))
                except Exception:
                    for line in initial_content.splitlines():
                        if line.strip():
                            self.list_widget.addItem(QListWidgetItem(line.strip()))

            self.btn_add_item.clicked.connect(self.add_list_item)
            self.item_input.returnPressed.connect(self.add_list_item)

            content_layout.addLayout(list_controls)
            content_layout.addWidget(self.list_widget)

        self.main_layout.addWidget(self.content_widget)

    def get_content_str(self) -> str:
        if self.card_type_idx == 0:
            return self.input_field.toPlainText().strip()
        elif self.card_type_idx == 1:
            return self.input_field.text().strip()
        elif self.card_type_idx == 2:
            items = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
            return json.dumps(items)
        return ""

    def save_card_content(self):
        if self.overview_repo and self.section_id:
            content = self.get_content_str()
            self.overview_repo.update_custom_section(self.section_id, content=content)

    def add_list_item(self):
        text = self.item_input.text().strip()
        if text:
            self.list_widget.addItem(QListWidgetItem(text))
            self.item_input.clear()
            self.save_card_content()

    def rename_card(self):
        from PySide6.QtWidgets import QInputDialog
        new_title, ok = QInputDialog.getText(self, "Rename Section", "New Section Title:", text=self.title_label.text())
        if ok and new_title.strip():
            cleaned_title = new_title.strip()
            self.title_label.setText(cleaned_title)
            if self.overview_repo and self.section_id:
                self.overview_repo.update_custom_section(self.section_id, title=cleaned_title)

    def toggle_collapse(self):
        self.is_collapsed = not self.is_collapsed
        self.content_widget.setVisible(not self.is_collapsed)
        self.btn_collapse.setText("▲" if self.is_collapsed else "▼")

    def delete_card(self):
        reply = QMessageBox.question(
            self, "Delete Section",
            f"Are you sure you want to delete '{self.title_label.text()}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if self.overview_repo and self.section_id:
                self.overview_repo.delete_custom_section(self.section_id)
            if self.on_delete_callback:
                self.on_delete_callback(self)
            self.setParent(None)
            self.deleteLater()


class AutoResizingTextEdit(QTextEdit):
    def __init__(self, placeholder=""):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(80)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.textChanged.connect(self.adjust_height)

    def adjust_height(self):
        doc_height = int(self.document().size().height())
        margins = self.contentsMargins()
        total_height = doc_height + margins.top() + margins.bottom() + 12
        self.setFixedHeight(max(80, total_height))


class AutoResizingList(QListWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(40)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def update_height(self):
        if self.count() == 0:
            self.setFixedHeight(40)
            return
        total_height = sum(self.sizeHintForRow(i) for i in range(self.count()))
        margins = self.contentsMargins()
        self.setFixedHeight(total_height + margins.top() + margins.bottom() + 6)

    def addItem(self, item):
        super().addItem(item)
        self.update_height()