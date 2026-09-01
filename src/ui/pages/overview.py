from PySide6.QtWidgets import (
    QWidget,QTextEdit,QComboBox,QLineEdit,QVBoxLayout,QHBoxLayout,QFrame,QPushButton,
    QLabel,QScrollArea,QFormLayout,QMessageBox,QDialog,QListWidget,QListWidgetItem
)
from PySide6.QtCore import Qt

class Overview_Page(QWidget):
    def __init__(self):
        super().__init__()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        #Sticky Top Bar
        top_bar_widget = QWidget()
        top_bar_widget.setObjectName("StickyTopBar")
        top_bar = QHBoxLayout(top_bar_widget)
        top_bar.setContentsMargins(24, 16, 24, 16)

        status_label = QLabel("Project Status:")
        self.status_combo = QComboBox()
        self.status_combo.setObjectName("StatusCombo")
        self.status_combo.setEditable(True)
        self.status_combo.addItems(["Drafting", "Active / In Development", "Stable / Complete", "Archived"])

        self.btn_add_section = QPushButton("+ Add Custom Section")
        self.btn_add_section.setObjectName("BtnAddSection")
        self.btn_add_section.clicked.connect(self.prompt_add_section)

        top_bar.addWidget(status_label)
        top_bar.addWidget(self.status_combo)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_add_section)

        main_layout.addWidget(top_bar_widget, stretch=0)

        #Scrollable Container
        scroll_area = QScrollArea()
        scroll_area.setObjectName("OverviewScrollArea")
        scroll_area.setWidgetResizable(True)

        self.content_widget = QWidget()
        self.cards_layout = QVBoxLayout(self.content_widget)
        self.cards_layout.setContentsMargins(24, 20, 24, 24)
        self.cards_layout.setSpacing(16)

        #Section 1: Language Details
        details_card = QFrame()
        details_card.setProperty("class", "overview-card")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(16, 16, 16, 16)

        sec1_title = QLabel("[icon:details] Language Details")
        sec1_title.setProperty("class", "section-title")
        details_layout.addWidget(sec1_title)

        #layout
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
        self.input_demonym.setPlaceholderText("e.g. Globle")

        col1.addRow("English Name (Exonym):", self.input_exonym)
        col1.addRow("Native Name (Endonym):", self.input_endonym)
        col1.addRow("Language Code / Abbr:", self.input_code)
        col1.addRow("Speaker Demonym:", self.input_demonym)

        self.input_pop = QLineEdit()
        self.input_pop.setPlaceholderText("e.g. 50,000 native speakers")
        self.input_family = QLineEdit()
        self.input_family.setPlaceholderText(" Demo Family")

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

        #Section 2: History Section
        history_card = QFrame()
        history_card.setProperty("class", "overview-card")
        h_layout = QVBoxLayout(history_card)
        h_layout.setContentsMargins(16, 12, 16, 12)
        h_title = QLabel("[icon:history] History & Origins")
        h_title.setProperty("class", "section-title")
        self.text_history = AutoResizingTextEdit()
        self.text_history.setPlaceholderText("Describe the historical origins and evolution of the language...")
        self.text_history.setMaximumHeight(100)
        h_layout.addWidget(h_title)
        h_layout.addWidget(self.text_history)
        self.cards_layout.addWidget(history_card)

        #Section 3: Culture & Usage
        culture_card = QFrame()
        culture_card.setProperty("class", "overview-card")
        c_layout = QVBoxLayout(culture_card)
        c_layout.setContentsMargins(16, 12, 16, 12)
        c_title = QLabel("[icon:culture] Cultural Background & Usage")
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

    #Call both Custom_Section_dialog() & Custom_card() function
    def prompt_add_section(self):

        dialog = Custom_Section_Dialog(self)
        if dialog.exec():
            title, type_idx = dialog.get_data()
            if title:
                stretch_item = self.cards_layout.itemAt(self.cards_layout.count() - 1)
                if stretch_item and stretch_item.spacerItem():
                    self.cards_layout.removeItem(stretch_item)

                new_card = Custom_Card(title, type_idx)
                self.cards_layout.addWidget(new_card)

                self.cards_layout.addStretch()
                

class Custom_Section_Dialog(QDialog):
    #Add Custom Section 
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
    # user-created custom card

    def __init__(self, title: str, card_type_idx: int):
        super().__init__()
        self.card_type_idx = card_type_idx
        self.is_collapsed = False

        self.setProperty("class", "overview-card")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 12, 16, 12)

        # Card Header
        header_layout = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setProperty("class", "section-title")

        # Header (Rename,Collapse & Delete)
        self.btn_rename = QPushButton("[icon:edit]")
        self.btn_collapse = QPushButton("[icon:collapse]")
        self.btn_delete = QPushButton("[icon:delete]")

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

        if card_type_idx == 0:  # Rich Text Area (Auto Resized added)
            self.input_field = AutoResizingTextEdit(f"Enter details for {title}...")
            content_layout.addWidget(self.input_field)

        elif card_type_idx == 1:  # Single Line Input
            self.input_field = QLineEdit()
            self.input_field.setPlaceholderText(f"Enter {title}...")
            content_layout.addWidget(self.input_field)

        elif card_type_idx == 2:  # List Box (Auto Resize added)
            list_controls = QHBoxLayout()
            self.item_input = QLineEdit()
            self.item_input.setPlaceholderText("Add item (e.g. dialect name, proverb)...")
            self.btn_add_item = QPushButton("+ Add")
            self.btn_add_item.setObjectName("BtnAddListItem")
            
            list_controls.addWidget(self.item_input)
            list_controls.addWidget(self.btn_add_item)

            self.list_widget = AutoResizingList()

            self.btn_add_item.clicked.connect(self.add_list_item)
            self.item_input.returnPressed.connect(self.add_list_item)

            content_layout.addLayout(list_controls)
            content_layout.addWidget(self.list_widget)

        self.main_layout.addWidget(self.content_widget)

    def add_list_item(self):
        text = self.item_input.text().strip()
        if text:
            self.list_widget.addItem(QListWidgetItem(text))
            self.item_input.clear()

    def rename_card(self):
        from PySide6.QtWidgets import QInputDialog
        new_title, ok = QInputDialog.getText(self, "Rename Section", "New Section Title:", text=self.title_label.text())
        if ok and new_title.strip():
            self.title_label.setText(new_title.strip())

    def toggle_collapse(self):
        self.is_collapsed = not self.is_collapsed
        self.content_widget.setVisible(not self.is_collapsed)
        self.btn_collapse.setText("[icon:expand]" if self.is_collapsed else "[icon:collapse]")

    def delete_card(self):
        reply = QMessageBox.question(
            self, "Delete Section",
            f"Are you sure you want to delete '{self.title_label.text()}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
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