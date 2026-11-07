from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .lookup import UD_TO_CLASS, pos_class
from .models import WordResult

# Word order for the translator: rearranges the finished word list. No Qt and no database in here.
#
# A setting has three parts:
#   sentence  the order of the Subject (S), Verb (V) and Object (O) blocks
#   np        the order inside a noun phrase: DET (the, a), ADJ (big), NOUN (dog)
#   adp       "before" (prepositions: in the house) or "after" (postpositions: the house in)
# The default is English order, which changes nothing.

DEFAULT_ORDER: Dict[str, Any] = {"sentence": ["S", "V", "O"], "np": ["DET", "ADJ", "NOUN"], "adp": "before"}

SENTENCE_LABELS = {"S": "Subject", "V": "Verb", "O": "Object"}

# the presets of the dropdown; "Keep English" is the default order
SENTENCE_PRESETS: List[Tuple[str, List[str]]] = [
    ("Keep English (SVO)", ["S", "V", "O"]),
    ("SOV", ["S", "O", "V"]),
    ("VSO", ["V", "S", "O"]),
    ("VOS", ["V", "O", "S"]),
    ("OVS", ["O", "V", "S"]),
    ("OSV", ["O", "S", "V"]),
]

# English function words, used when the lexicon entry has no part of speech
_DET = {"the", "a", "an", "this", "that", "these", "those", "my", "your", "his", "her", "its", "our", "their",
        "some", "any", "every", "each", "no", "all", "many", "few", "several"}
_ADP = {"in", "on", "at", "with", "to", "from", "of", "by", "for", "under", "over", "into", "onto", "near",
        "behind", "between", "through", "about", "without", "within", "above", "below", "across", "around",
        "beside", "toward", "towards", "inside", "outside", "beneath", "beyond", "against", "among", "along"}
_CONJ = {"and", "but", "or", "because", "while", "although", "so", "if", "when", "then"}


def normalize_order(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Make any stored value into a valid setting (unknown or repeated parts fall back to the default)."""
    out = copy.deepcopy(DEFAULT_ORDER)
    data = data or {}
    for key, allowed in (("sentence", DEFAULT_ORDER["sentence"]), ("np", DEFAULT_ORDER["np"])):
        value = data.get(key)
        if isinstance(value, (list, tuple)) and sorted(map(str, value)) == sorted(allowed):
            out[key] = [str(v) for v in value]
    if data.get("adp") in ("before", "after"):
        out["adp"] = data["adp"]
    return out


def is_default(order: Optional[Dict[str, Any]]) -> bool:
    return normalize_order(order) == DEFAULT_ORDER


def preset_name(sentence: Sequence[str]) -> Optional[str]:
    for name, seq in SENTENCE_PRESETS:
        if list(sentence) == seq:
            return name
    return None


def np_from_choices(det_before: bool, adj_before: bool) -> List[str]:
    """Noun phrase order from two before/after choices. Items on the same side keep a fixed order:
    before the noun: determiner, adjective, noun; after the noun: noun, adjective, determiner."""
    before = [r for r, on in (("DET", det_before), ("ADJ", adj_before)) if on]
    after = [r for r, on in (("ADJ", not adj_before), ("DET", not det_before)) if on]
    return before + ["NOUN"] + after


def np_choices(np: Sequence[str]) -> Tuple[bool, bool]:
    """(determiner before noun, adjective before noun) for a stored noun phrase order."""
    order = normalize_order({"np": list(np)})["np"]
    noun = order.index("NOUN")
    return order.index("DET") < noun, order.index("ADJ") < noun


def sentence_example(sentence: Sequence[str]) -> str:
    words = {"S": "dog", "V": "sees", "O": "cat"}
    return " ".join(words[k] for k in normalize_order({"sentence": list(sentence)})["sentence"])


def word_class(word: WordResult) -> str:
    """NOUN, VERB, ADJ, ADV, PRON, DET, ADP, CONJ, NUM, ... or "" when nothing is known."""
    if word.status == "number":
        return "NUM"
    if word.pos and word.pos in UD_TO_CLASS:
        return UD_TO_CLASS[word.pos]
    if word.entry is not None:
        cls = pos_class(word.entry.get("part_of_speech") or word.entry.get("pos"))
        if cls:
            return cls
    english = (word.lemma or word.english or "").lower()
    if english in _DET:
        return "DET"
    if english in _ADP:
        return "ADP"
    if english in _CONJ:
        return "CONJ"
    return ""


def unclassified(words: Sequence[WordResult]) -> List[WordResult]:
    """Words that were found in the lexicon but whose part of speech cannot be told."""
    return [w for w in words if w.entry is not None and w.status != "dropped" and not word_class(w)]


# ---------------------------------------------------------------------------------------------------------
class _Chunk:
    def __init__(self, kind: str, words: List[WordResult]):
        self.kind = kind      # NP | PP | V | X
        self.words = words


def _noun_phrase(words: List[WordResult], classes: List[str], np_order: Sequence[str]) -> List[WordResult]:
    slots: Dict[str, List[WordResult]] = {"DET": [], "ADJ": [], "NOUN": []}
    for w, c in zip(words, classes):
        slots["DET" if c in ("DET", "NUM") else "ADJ" if c == "ADJ" else "NOUN"].append(w)
    return [w for role in np_order for w in slots[role]]


def _chunks(run: List[WordResult], order: Dict[str, Any]) -> List[_Chunk]:
    chunks: List[_Chunk] = []
    np_words: List[WordResult] = []
    np_classes: List[str] = []
    np_has_head = False
    pending_adp: Optional[WordResult] = None

    def close_np():
        nonlocal np_words, np_classes, np_has_head, pending_adp
        if not np_words:
            return
        phrase = _noun_phrase(np_words, np_classes, order["np"])
        if pending_adp is not None:
            phrase = ([pending_adp] + phrase) if order["adp"] == "before" else (phrase + [pending_adp])
            chunks.append(_Chunk("PP", phrase))
            pending_adp = None
        else:
            chunks.append(_Chunk("NP", phrase))
        np_words, np_classes, np_has_head = [], [], False

    def flush_adp():
        nonlocal pending_adp
        if pending_adp is not None:       # an adposition with nothing after it stays where it is
            chunks.append(_Chunk("X", [pending_adp]))
            pending_adp = None

    for w in run:
        c = word_class(w)
        if c in ("DET", "NUM"):
            if np_has_head:
                close_np()
            np_words.append(w)
            np_classes.append(c)
        elif c == "ADJ":
            if np_has_head:
                close_np()
            np_words.append(w)
            np_classes.append(c)
        elif c in ("NOUN", "PRON"):
            if np_has_head:
                close_np()
            np_words.append(w)
            np_classes.append("NOUN")
            np_has_head = True
        elif c == "ADP":
            close_np()
            flush_adp()
            pending_adp = w
        elif c == "VERB":
            close_np()
            flush_adp()
            if chunks and chunks[-1].kind == "V":
                chunks[-1].words.append(w)
            else:
                chunks.append(_Chunk("V", [w]))
        else:
            close_np()
            flush_adp()
            chunks.append(_Chunk("X", [w]))
    close_np()
    flush_adp()
    return chunks


def _clause(run: List[WordResult], order: Dict[str, Any]) -> List[WordResult]:
    chunks = _chunks(run, order)
    verb = next((i for i, ch in enumerate(chunks) if ch.kind == "V"), None)
    if verb is None or order["sentence"] == DEFAULT_ORDER["sentence"]:
        return [w for ch in chunks for w in ch.words]

    subject = [w for ch in chunks[:verb] for w in ch.words]
    after = chunks[verb + 1:]
    obj_at = next((i for i, ch in enumerate(after) if ch.kind == "NP"), None)
    verb_block = list(chunks[verb].words)
    if obj_at is None:
        # no object: the extra phrases stay with the verb
        verb_block += [w for ch in after for w in ch.words]
        object_block: List[WordResult] = []
    else:
        verb_block += [w for ch in after[:obj_at] for w in ch.words]
        object_block = [w for ch in after[obj_at:] for w in ch.words]   # the object and what follows it
    blocks = {"S": subject, "V": verb_block, "O": object_block}
    return [w for key in order["sentence"] for w in blocks[key]]


def reorder(words: Sequence[WordResult], order: Optional[Dict[str, Any]]) -> List[WordResult]:
    """Return the words in the order of the language. Punctuation and conjunctions split the text into
    clauses; each clause is arranged on its own. Words that have no part of speech stay in English order."""
    order = normalize_order(order)
    if order == DEFAULT_ORDER:
        return list(words)
    out: List[WordResult] = []
    run: List[WordResult] = []
    skipped: List[WordResult] = []

    def flush():
        nonlocal run, skipped
        if run:
            out.extend(_clause(run, order))
        out.extend(skipped)
        run, skipped = [], []

    for w in words:
        if w.status == "punct" or word_class(w) == "CONJ":
            flush()
            out.append(w)
        elif w.status == "dropped" or (w.status == "unknown" and not w.form):
            skipped.append(w)
        else:
            run.append(w)
    flush()
    return out
