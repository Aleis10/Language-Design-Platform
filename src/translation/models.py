"""Plain data types shared by the translation engine (no Qt, no database)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Analysis:
    """One possible reading of an English word.

    `pos` uses Universal Dependencies tags (NOUN, VERB, ADJ, ADV, PRON, ...), or ""
    when unknown. `features` uses UD feature names, e.g. {"Number": "Plur"} or
    {"Tense": "Past", "VerbForm": "Fin"}.
    """
    lemma: str
    pos: str = ""
    features: Dict[str, str] = field(default_factory=dict)


@dataclass
class Token:
    text: str
    hypotheses: List[Analysis] = field(default_factory=list)   # best guess first
    is_punct: bool = False
    is_number: bool = False


@dataclass
class Candidate:
    """A lexicon entry that matches an English word."""
    entry: Dict[str, Any]
    gloss: str                       # the English gloss that matched
    source: str                      # "english_translation" or "meaning"
    pos_match: Optional[bool] = None  # None = part of speech unknown on either side


@dataclass
class WordResult:
    english: str
    lemma: str = ""
    pos: str = ""
    entry: Optional[Dict[str, Any]] = None
    stem: str = ""                   # dictionary form (headword)
    form: str = ""                   # final conlang form (after inflection)
    gloss: str = ""                  # e.g. "dog-PL"
    applied: List[str] = field(default_factory=list)   # gloss tags that were applied
    missing: List[str] = field(default_factory=list)   # needed but no rule/grid found
    source: str = "stem"             # "stem", "rule:<name>", "grid:<name>"
    status: str = "ok"               # ok | ambiguous | unknown | dropped | punct | number
    alternatives: List[Candidate] = field(default_factory=list)
    chosen: Optional[Candidate] = None             # the candidate that was used
    features: Dict[str, str] = field(default_factory=dict)   # English features, e.g. {'Number': 'Plur'}
    notes: List[str] = field(default_factory=list)
    span: Tuple[int, int] = (0, 0)   # token index range [start, end)


@dataclass
class Translation:
    source_text: str
    words: List[WordResult]
    conlang_text: str
    gloss_text: str
    warnings: List[str] = field(default_factory=list)
