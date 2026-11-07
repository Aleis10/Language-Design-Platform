import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)
from digital_keyboard import track_conlang_combo, track_conlang_widget
from translation.features import WORD_CLASSES, trigger_for_tag
from translation.word_order import (
    DEFAULT_ORDER, SENTENCE_PRESETS, normalize_order, np_choices, np_from_choices, sentence_example,
)

# widths of the rule columns: Form, Word type, Add, Only if, Letters (minimum)
RULE_COLS = (130, 110, 100, 160, 150)
RULE_MARGIN = 10
RULE_SPACING = 8
CONDITIONS = [
    ("", "(always)"),
    ("ends_with", "ends with"),
    ("starts_with", "starts with"),
    ("not_ends_with", "does not end with"),
    ("not_starts_with", "does not start with"),
]


def _label(text: str, name: str = "") -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    return lbl


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)


# ---------------------------------------------------------------------------------------------------------
class _RuleRow(QFrame):
    """One rule on one line: [Plural] [noun] [-ya] [ends with] [a e i o u]"""

    def __init__(self, page: "GrammarSimplePage", values: List[Dict[str, Any]], rule: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.setObjectName("GsRow")
        self.page = page
        self.rule_id: Optional[str] = rule["id"] if rule else None
        self._legacy_tag = ""
        self._class_touched = rule is not None     # once the word class is chosen by hand it is left alone
        self._loading = True

        row = QHBoxLayout(self)
        row.setContentsMargins(RULE_MARGIN, 6, RULE_MARGIN, 6)
        row.setSpacing(RULE_SPACING)
        self.setMinimumHeight(46)

        self.cmb_value = QComboBox()
        for v in values:
            self.cmb_value.addItem(v.get("label") or v.get("tag") or "?", v["id"])
        self.cmb_value.setFixedWidth(RULE_COLS[0])
        row.addWidget(self.cmb_value)

        self.cmb_class = QComboBox()
        self.cmb_class.addItem("any word", "")
        for key, label in WORD_CLASSES:
            self.cmb_class.addItem(label.lower(), key)
        self.cmb_class.setFixedWidth(RULE_COLS[1])
        row.addWidget(self.cmb_class)

        self.txt_affix = QLineEdit()
        self.txt_affix.setPlaceholderText("-ya  or  un-")
        self.txt_affix.setFixedWidth(RULE_COLS[2])
        row.addWidget(self.txt_affix)

        self.cmb_cond = QComboBox()
        for key, label in CONDITIONS:
            self.cmb_cond.addItem(label, key)
        self.cmb_cond.setFixedWidth(RULE_COLS[3])
        row.addWidget(self.cmb_cond)

        self.txt_cond = QLineEdit()
        self.txt_cond.setPlaceholderText("letters, e.g. a e i o u")
        self.txt_cond.setMinimumWidth(RULE_COLS[4])
        row.addWidget(self.txt_cond, 1)

        self.btn_remove = QPushButton("\u2715")
        self.btn_remove.setObjectName("GsRemove")
        self.btn_remove.setFixedSize(28, 28)
        self.btn_remove.setToolTip("Remove this rule")
        self.btn_remove.clicked.connect(lambda: page.remove_rule(self))
        row.addWidget(self.btn_remove)

        if rule:
            self._load(rule, values)
        self._sync_condition()
        self._loading = False

        self.cmb_value.currentIndexChanged.connect(self._on_value_changed)
        self.cmb_class.currentIndexChanged.connect(self._on_class_changed)
        self.cmb_cond.currentIndexChanged.connect(self._on_cond_changed)
        self.txt_affix.editingFinished.connect(self._changed)
        self.txt_cond.editingFinished.connect(self._changed)

    def _load(self, rule: Dict[str, Any], values: List[Dict[str, Any]]) -> None:
        ids = [v["id"] for v in values]
        idx = self.cmb_value.findData(rule.get("value_id")) if rule.get("value_id") in ids else -1
        if idx < 0:
            # an older rule without a feature value: find the value that listens for the same thing
            trig = trigger_for_tag(rule.get("gloss_tag") or "")
            match = next((v for v in values if trig and v.get("trigger") == trig), None)
            if match is not None:
                idx = self.cmb_value.findData(match["id"])
        if idx < 0:
            self._legacy_tag = rule.get("gloss_tag") or ""
            self.cmb_value.addItem(f"{self._legacy_tag or '?'} (older rule)", "")
            idx = self.cmb_value.count() - 1
        self.cmb_value.setCurrentIndex(idx)
        ci = self.cmb_class.findData((rule.get("word_class") or "").upper())
        self.cmb_class.setCurrentIndex(max(ci, 0))
        self.txt_affix.setText(rule.get("affix_pattern") or "")
        k = self.cmb_cond.findData((rule.get("condition_type") or "").lower())
        self.cmb_cond.setCurrentIndex(max(k, 0))
        self.txt_cond.setText(rule.get("condition_value") or "")

    def _sync_condition(self) -> None:
        # the letters box keeps its place (so the columns stay lined up) but is only usable with a condition
        on = bool(self.cmb_cond.currentData())
        self.txt_cond.setEnabled(on)
        self.txt_cond.setPlaceholderText("letters, e.g. a e i o u" if on else "")

    def _on_cond_changed(self) -> None:
        self._sync_condition()
        self._changed()

    def _on_class_changed(self) -> None:
        if not self._loading:
            self._class_touched = True
        self._changed()

    def _on_value_changed(self) -> None:
        if not self._loading and not self._class_touched:
            classes = self.page.value_classes(self.cmb_value.currentData())
            if classes:
                self.cmb_class.blockSignals(True)
                self.cmb_class.setCurrentIndex(max(self.cmb_class.findData(classes[0]), 0))
                self.cmb_class.blockSignals(False)
        self._changed()

    def _changed(self) -> None:
        if self._loading:
            return
        try:
            self.page.save_rule(self)
        except RuntimeError:
            pass                      # the row is being deleted (a widget emitted a last signal)

    def data(self) -> Dict[str, Any]:
        value_id = self.cmb_value.currentData() or None
        label = self.cmb_value.currentText()
        cls = self.cmb_class.currentData() or ""
        return {
            "value_id": value_id,
            "word_class": cls,
            "affix_pattern": self.txt_affix.text().strip(),
            "condition_type": self.cmb_cond.currentData() or "",
            "condition_value": self.txt_cond.text().strip() if self.cmb_cond.currentData() else "",
            "label": label,
            "legacy_tag": self._legacy_tag,
        }


class _ExceptionRow(QFrame):
    """'[word] + [Plural] = [form]'"""

    def __init__(self, page: "GrammarSimplePage", entries: List[Dict[str, Any]], values: List[Dict[str, Any]],
                 irregular: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.setObjectName("GsRow")
        self.page = page
        self.irregular_id: Optional[str] = irregular["id"] if irregular else None
        self._value_ids: List[str] = list(irregular["value_ids"]) if irregular else []
        self._loading = True

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        self.cmb_word = QComboBox()
        self.cmb_word.setMinimumWidth(170)
        self.cmb_word.addItem("(choose a word)", "")
        for e in entries:
            eng = (e.get("english_translation") or "").strip()
            head = e.get("headword") or "?"
            self.cmb_word.addItem(f"{head}  \u2014  {eng}" if eng else head, e["id"])
        track_conlang_combo(self.cmb_word, 12)
        lay.addWidget(self.cmb_word)
        lay.addWidget(_label("+"))
        self.cmb_value = QComboBox()
        self.cmb_value.addItem("(choose)", "")
        for v in values:
            self.cmb_value.addItem(v.get("label") or v.get("tag") or "?", v["id"])
        lay.addWidget(self.cmb_value)
        lay.addWidget(_label("="))
        self.txt_form = QLineEdit()
        self.txt_form.setPlaceholderText("exact form")
        self.txt_form.setMinimumWidth(130)
        lay.addWidget(self.txt_form)
        lay.addStretch(1)
        self.btn_remove = QPushButton("\u2715")
        self.btn_remove.setObjectName("GsRemove")
        self.btn_remove.setFixedSize(28, 28)
        self.btn_remove.setToolTip("Remove this exception")
        self.btn_remove.clicked.connect(lambda: page.remove_exception(self))
        lay.addWidget(self.btn_remove)

        if irregular:
            self.cmb_word.setCurrentIndex(max(self.cmb_word.findData(str(irregular.get("entry_id"))), 0))
            if self._value_ids:
                self.cmb_value.setCurrentIndex(max(self.cmb_value.findData(self._value_ids[0]), 0))
            self.txt_form.setText(irregular.get("form") or "")
        self._loading = False

        self.cmb_word.currentIndexChanged.connect(self._changed)
        self.cmb_value.currentIndexChanged.connect(self._changed)
        self.txt_form.editingFinished.connect(self._changed)

    def _changed(self) -> None:
        if self._loading:
            return
        try:
            self.page.save_exception(self)
        except RuntimeError:
            pass

    def data(self) -> Dict[str, Any]:
        value_id = self.cmb_value.currentData() or ""
        if self._value_ids and value_id == self._value_ids[0]:
            ids = list(self._value_ids)       # keep extra values an older irregular may have
        else:
            ids = [value_id] if value_id else []
        return {"entry_id": self.cmb_word.currentData() or "", "value_ids": ids, "form": self.txt_form.text().strip()}


# ---------------------------------------------------------------------------------------------------------
class GrammarSimplePage(QWidget):
    """Custom grammar on one page: word order and word forms (rules and exceptions)."""

    def __init__(self, grammar_repo, lexicon_repo, language_id: str, parent=None):
        super().__init__(parent)
        self.grammar_repo = grammar_repo
        self.lexicon_repo = lexicon_repo
        self.language_id = language_id
        self.on_saved = None
        self._values: List[Dict[str, Any]] = []
        self._entries: List[Dict[str, Any]] = []
        self._loading = True

        if grammar_repo is not None and hasattr(grammar_repo, "ensure_default_features"):
            try:
                grammar_repo.ensure_default_features(language_id)
            except Exception:
                pass

        self._build_ui()
        self._load_stylesheet()
        self.refresh()
        self._loading = False

    # -------------------------------------------------------------- build
    def _load_stylesheet(self) -> None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style", "grammar_simple_page.qss")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def _card(self, title: str, hint: str = ""):
        card = QFrame()
        card.setObjectName("GsCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(_label(title, "GsSection"))
        head.addStretch(1)
        lay.addLayout(head)
        if hint:
            lay.addWidget(_label(hint, "GsHint"))
        return card, lay, head

    def _labelled(self, caption: str, widget: QWidget, stretch: bool = True) -> QHBoxLayout:
        row = QHBoxLayout()
        cap = _label(caption, "GsCaption")
        cap.setFixedWidth(100)
        row.addWidget(cap)
        row.addWidget(widget)
        if stretch:
            row.addStretch(1)
        return row

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget()
        bar.setObjectName("GsTopBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(20, 8, 20, 8)
        bl.addWidget(_label("Grammar", "GsTitle"))
        bl.addStretch(1)
        root.addWidget(bar)

        scroll = QScrollArea()
        scroll.setObjectName("GsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("GsBody")
        bv = QVBoxLayout(body)
        bv.setContentsMargins(20, 16, 20, 16)
        bv.setSpacing(14)

        # 1. word order
        card, lay, head = self._card("1. Word order", "Choose the order your language uses. "
                                                      "Works best for short, simple sentences.")
        self.btn_reset_order = QPushButton("Reset to English")
        self.btn_reset_order.setToolTip("Back to English word order")
        self.btn_reset_order.clicked.connect(self._reset_order)
        head.addWidget(self.btn_reset_order)

        # sentence order: one button per order
        self.order_group = QButtonGroup(self)
        self.order_group.setExclusive(True)
        buttons = QWidget()
        bl2 = QHBoxLayout(buttons)
        bl2.setContentsMargins(0, 0, 0, 0)
        bl2.setSpacing(6)
        self._order_buttons: Dict[str, QPushButton] = {}
        for i, (name, seq) in enumerate(SENTENCE_PRESETS):
            btn = QPushButton("SVO (English)" if i == 0 else name)
            btn.setObjectName("GsChoice")
            btn.setCheckable(True)
            btn.setProperty("seq", "".join(seq))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.order_group.addButton(btn)
            bl2.addWidget(btn)
            self._order_buttons["".join(seq)] = btn
        bl2.addStretch(1)
        lay.addLayout(self._labelled("Sentence", buttons, stretch=False))
        self.lbl_example = _label("", "GsHint")
        ex = QHBoxLayout()
        pad = QLabel("")
        pad.setFixedWidth(100)
        ex.addWidget(pad)
        ex.addWidget(self.lbl_example)
        ex.addStretch(1)
        lay.addLayout(ex)

        self.cmb_adj = QComboBox()
        self.cmb_adj.addItem("Before the noun   (big dog)", True)
        self.cmb_adj.addItem("After the noun   (dog big)", False)
        lay.addLayout(self._labelled("Adjective", self.cmb_adj))
        self.cmb_det = QComboBox()
        self.cmb_det.addItem("Before the noun   (the dog)", True)
        self.cmb_det.addItem("After the noun   (dog the)", False)
        lay.addLayout(self._labelled("Determiner", self.cmb_det))
        self.cmb_adp = QComboBox()
        self.cmb_adp.addItem("Before the noun   (in the house)", "before")
        self.cmb_adp.addItem("After the noun   (the house in)", "after")
        lay.addLayout(self._labelled("Adposition", self.cmb_adp))
        bv.addWidget(card)

        self.order_group.buttonClicked.connect(self._on_order_changed)
        for cmb in (self.cmb_adj, self.cmb_det, self.cmb_adp):
            cmb.currentIndexChanged.connect(self._on_order_changed)

        # 2. word forms
        card, lay, _head = self._card(
            "2. Word forms",
            "Pick the form, the kind of word, and what to add. Write -ya to add at the end, un- at the start.")
        header = QHBoxLayout()
        header.setContentsMargins(RULE_MARGIN + 1, 0, RULE_MARGIN + 1, 0)
        header.setSpacing(RULE_SPACING)
        for text, width in zip(("Form", "Word type", "Add", "Only if"), RULE_COLS[:4]):
            cap = _label(text, "GsColumn")
            cap.setFixedWidth(width)
            header.addWidget(cap)
        header.addWidget(_label("Letters", "GsColumn"), 1)
        header.addSpacing(28)
        self.rules_header = QWidget()
        self.rules_header.setLayout(header)
        lay.addWidget(self.rules_header)

        self.rules_box = QVBoxLayout()
        self.rules_box.setSpacing(6)
        lay.addLayout(self.rules_box)
        self.lbl_no_rules = _label("No rules yet.", "GsHint")
        lay.addWidget(self.lbl_no_rules)
        self.lbl_notice = _label("", "GsWarn")
        lay.addWidget(self.lbl_notice)
        row = QHBoxLayout()
        self.btn_add_rule = QPushButton("+ Add rule")
        self.btn_add_rule.clicked.connect(self._add_rule)
        row.addWidget(self.btn_add_rule)
        row.addStretch(1)
        lay.addLayout(row)

        lay.addWidget(_label("Exceptions", "GsSubSection"))
        lay.addWidget(_label("A word that does not follow the rules, with its exact form.", "GsHint"))
        self.exc_box = QVBoxLayout()
        self.exc_box.setSpacing(6)
        lay.addLayout(self.exc_box)
        self.lbl_no_exc = _label("No exceptions yet.", "GsHint")
        lay.addWidget(self.lbl_no_exc)
        row = QHBoxLayout()
        self.btn_add_exc = QPushButton("+ Add exception")
        self.btn_add_exc.clicked.connect(self._add_exception)
        row.addWidget(self.btn_add_exc)
        row.addStretch(1)
        lay.addLayout(row)
        bv.addWidget(card)

        bv.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        self._apply_fonts(self)

    def _apply_fonts(self, root) -> None:
        # the conlang font goes on the typed fields
        for edit in root.findChildren(QLineEdit):
            track_conlang_widget(edit, 12)

    # -------------------------------------------------------------- data
    def value_classes(self, value_id) -> List[str]:
        for v in self._values:
            if v["id"] == value_id:
                return [c.upper() for c in (v.get("word_classes") or [])]
        return []

    def _usable_values(self) -> List[Dict[str, Any]]:
        return [v for v in self._values if v.get("trigger")]

    def refresh(self) -> None:
        was = self._loading
        self._loading = True
        repo = self.grammar_repo
        self._values = repo.get_feature_values(self.language_id) if repo is not None else []
        order = repo.get_word_order(self.language_id) if repo is not None else dict(DEFAULT_ORDER)
        self._show_order(order)

        _clear_layout(self.rules_box)
        usable = self._usable_values()
        rules = repo.get_rules(self.language_id) if repo is not None else []
        for rule in rules:
            self.rules_box.addWidget(_RuleRow(self, usable, rule))
        self.lbl_no_rules.setVisible(not rules)
        self.rules_header.setVisible(bool(rules))

        _clear_layout(self.exc_box)
        entries = self.lexicon_repo.get_all_entries(self.language_id) if self.lexicon_repo is not None else []
        self._entries = entries
        irregulars = repo.get_irregulars(self.language_id) if repo is not None else []
        for irr in irregulars:
            self.exc_box.addWidget(_ExceptionRow(self, entries, usable, irr))
        self.lbl_no_exc.setVisible(not irregulars)
        self._apply_fonts(self)
        self._loading = was

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loading:
            self.refresh()          # words or features may have changed on other pages

    # -------------------------------------------------------------- word order
    def _show_order(self, order: Dict[str, Any]) -> None:
        order = normalize_order(order)
        key = "".join(order["sentence"])
        btn = self._order_buttons.get(key) or self._order_buttons["SVO"]
        btn.setChecked(True)
        det_before, adj_before = np_choices(order["np"])
        for cmb, value in ((self.cmb_det, det_before), (self.cmb_adj, adj_before), (self.cmb_adp, order["adp"])):
            cmb.blockSignals(True)
            cmb.setCurrentIndex(max(cmb.findData(value), 0))
            cmb.blockSignals(False)
        self.lbl_example.setText("Example:  " + sentence_example(order["sentence"]))

    def current_order(self) -> Dict[str, Any]:
        checked = self.order_group.checkedButton()
        key = checked.property("seq") if checked is not None else "SVO"
        return {
            "sentence": list(key),
            "np": np_from_choices(bool(self.cmb_det.currentData()), bool(self.cmb_adj.currentData())),
            "adp": self.cmb_adp.currentData() or "before",
        }

    def _reset_order(self) -> None:
        self._show_order(DEFAULT_ORDER)
        self._on_order_changed()

    def _on_order_changed(self, *_args) -> None:
        if self._loading:
            return
        order = self.current_order()
        self.lbl_example.setText("Example:  " + sentence_example(order["sentence"]))
        if self.grammar_repo is not None:
            self.grammar_repo.set_word_order(self.language_id, order)
        self._saved()

    # -------------------------------------------------------------- rules
    def _add_rule(self) -> None:
        if not self._usable_values():
            self.lbl_notice.setText("There are no word forms to attach a rule to.")
            return
        self.lbl_notice.setText("")
        row = _RuleRow(self, self._usable_values())
        self.rules_box.addWidget(row)
        self.lbl_no_rules.setVisible(False)
        self.rules_header.setVisible(True)
        self._apply_fonts(row)
        row._on_value_changed()          # picks the word type of the first form
        row.txt_affix.setFocus()

    def save_rule(self, row: _RuleRow) -> None:
        d = row.data()
        if self.grammar_repo is None or not d["affix_pattern"]:
            return
        value = next((v for v in self._values if v["id"] == d["value_id"]), None)
        tag = (value.get("tag") if value else d["legacy_tag"]) or "?"
        name = f"{d['label']}" + (f" ({d['word_class'].lower()})" if d["word_class"] else "")
        fields = dict(
            name=name, gloss_tag=tag, affix_pattern=d["affix_pattern"], affix_type="suffix",
            value_id=d["value_id"] or "", word_class=d["word_class"],
            condition_type=d["condition_type"], condition_value=d["condition_value"],
        )
        position = self._index_of(self.rules_box, row)
        if row.rule_id is None:
            row.rule_id = self.grammar_repo.add_rule(
                self.language_id, fields["name"], fields["gloss_tag"], affix_pattern=fields["affix_pattern"],
                affix_type="suffix", position=position, value_id=fields["value_id"] or None,
                word_class=fields["word_class"], condition_type=fields["condition_type"],
                condition_value=fields["condition_value"],
            )
        else:
            # empty strings are stored too, so a cleared condition is saved
            self.grammar_repo.update_rule(row.rule_id, position=position, **fields)
        self._saved()

    def remove_rule(self, row: _RuleRow) -> None:
        if row.rule_id and self.grammar_repo is not None:
            self.grammar_repo.delete_rule(row.rule_id)
        self.rules_box.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        empty = self.rules_box.count() == 0
        self.lbl_no_rules.setVisible(empty)
        self.rules_header.setVisible(not empty)
        self._saved()

    # -------------------------------------------------------------- exceptions
    def _add_exception(self) -> None:
        if not self._usable_values():
            self.lbl_notice.setText("There are no word forms to attach an exception to.")
            return
        self.lbl_notice.setText("")
        row = _ExceptionRow(self, self._entries, self._usable_values())
        self.exc_box.addWidget(row)
        self.lbl_no_exc.setVisible(False)
        self._apply_fonts(row)

    def save_exception(self, row: _ExceptionRow) -> None:
        d = row.data()
        if self.grammar_repo is None or not (d["entry_id"] and d["value_ids"] and d["form"]):
            return
        if row.irregular_id is None:
            row.irregular_id = self.grammar_repo.add_irregular(self.language_id, d["entry_id"], d["value_ids"], d["form"])
        else:
            # the word of an existing exception cannot be edited in place: replace it
            self.grammar_repo.delete_irregular(row.irregular_id)
            row.irregular_id = self.grammar_repo.add_irregular(self.language_id, d["entry_id"], d["value_ids"], d["form"])
        row._value_ids = list(d["value_ids"])
        self._saved()

    def remove_exception(self, row: _ExceptionRow) -> None:
        if row.irregular_id and self.grammar_repo is not None:
            self.grammar_repo.delete_irregular(row.irregular_id)
        self.exc_box.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self.lbl_no_exc.setVisible(self.exc_box.count() == 0)
        self._saved()

    @staticmethod
    def _index_of(box: QVBoxLayout, widget: QWidget) -> int:
        for i in range(box.count()):
            if box.itemAt(i).widget() is widget:
                return i
        return 0

    def _saved(self) -> None:
        if callable(self.on_saved):
            self.on_saved()
