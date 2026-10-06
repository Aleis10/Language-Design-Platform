"""English analysis: turn text into tokens, each with one or more candidate readings.

Two analyzers share one interface (`analyze(text) -> List[Token]`):

* SimpleAnalyzer  - no dependencies. It does not guess a single answer; it lists every
  plausible reading ("dogs" -> dog+plural, dog+3sg verb, ...) and the engine keeps the
  first reading whose base form actually exists in the lexicon.
* SpacyAnalyzer   - optional. spaCy's reading comes first (better part-of-speech and
  features), with SimpleAnalyzer's readings behind it as a fallback.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .models import Analysis, Token

_TOKEN_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*|\d+(?:[.,]\d+)*|[^\sA-Za-z\d]")
_VOWELS = set("aeiou")

PAST = {"Tense": "Past", "VerbForm": "Fin"}
PAST_PART = {"Tense": "Past", "VerbForm": "Part"}

# surface form -> (lemma, pos, features)
IRREGULAR: Dict[str, Tuple[str, str, Dict[str, str]]] = {}


def _irr(lemma: str, past: str = "", part: str = "", pos: str = "VERB") -> None:
    for form in filter(None, past.split("/")):
        IRREGULAR.setdefault(form, (lemma, pos, dict(PAST)))
    for form in filter(None, part.split("/")):
        IRREGULAR.setdefault(form, (lemma, pos, dict(PAST_PART)))


for _lemma, _past, _part in [
    ("be", "was/were", "been"), ("have", "had", "had"), ("do", "did", "done"),
    ("go", "went", "gone"), ("see", "saw", "seen"), ("eat", "ate", "eaten"),
    ("take", "took", "taken"), ("give", "gave", "given"), ("come", "came", ""),
    ("make", "made", "made"), ("say", "said", "said"), ("get", "got", "gotten/got"),
    ("know", "knew", "known"), ("think", "thought", "thought"), ("bring", "brought", "brought"),
    ("buy", "bought", "bought"), ("catch", "caught", "caught"), ("teach", "taught", "taught"),
    ("find", "found", "found"), ("tell", "told", "told"), ("sell", "sold", "sold"),
    ("hold", "held", "held"), ("keep", "kept", "kept"), ("leave", "left", "left"),
    ("feel", "felt", "felt"), ("begin", "began", "begun"), ("run", "ran", ""),
    ("sit", "sat", "sat"), ("stand", "stood", "stood"), ("write", "wrote", "written"),
    ("speak", "spoke", "spoken"), ("break", "broke", "broken"), ("choose", "chose", "chosen"),
    ("drive", "drove", "driven"), ("fly", "flew", "flown"), ("grow", "grew", "grown"),
    ("throw", "threw", "thrown"), ("wear", "wore", "worn"), ("sing", "sang", "sung"),
    ("drink", "drank", "drunk"), ("swim", "swam", "swum"), ("fall", "fell", "fallen"),
    ("lose", "lost", "lost"), ("meet", "met", "met"), ("pay", "paid", "paid"),
    ("hear", "heard", "heard"), ("sleep", "slept", "slept"), ("build", "built", "built"),
    ("send", "sent", "sent"), ("spend", "spent", "spent"), ("win", "won", "won"),
    ("fight", "fought", "fought"), ("forget", "forgot", "forgotten"), ("rise", "rose", "risen"),
    ("ride", "rode", "ridden"), ("hide", "hid", "hidden"), ("bite", "bit", "bitten"),
    ("lead", "led", "led"), ("understand", "understood", "understood"),
    ("wake", "woke", "woken"), ("draw", "drew", "drawn"), ("shake", "shook", "shaken"),
    ("steal", "stole", "stolen"), ("swear", "swore", "sworn"), ("tear", "tore", "torn"),
]:
    _irr(_lemma, _past, _part)

IRREGULAR_PRESENT = {
    "is": ("be", {"Tense": "Pres", "Person": "3", "Number": "Sing", "VerbForm": "Fin"}),
    "are": ("be", {"Tense": "Pres", "Number": "Plur", "VerbForm": "Fin"}),
    "am": ("be", {"Tense": "Pres", "Person": "1", "Number": "Sing", "VerbForm": "Fin"}),
    "has": ("have", {"Tense": "Pres", "Person": "3", "Number": "Sing", "VerbForm": "Fin"}),
    "does": ("do", {"Tense": "Pres", "Person": "3", "Number": "Sing", "VerbForm": "Fin"}),
}

IRREGULAR_NOUNS = {
    "children": "child", "men": "man", "women": "woman", "feet": "foot", "teeth": "tooth",
    "mice": "mouse", "geese": "goose", "people": "person", "oxen": "ox", "lice": "louse",
}

IRREGULAR_ADJ = {
    "better": ("good", "Cmp"), "best": ("good", "Sup"), "worse": ("bad", "Cmp"),
    "worst": ("bad", "Sup"), "more": ("much", "Cmp"), "most": ("much", "Sup"),
    "less": ("little", "Cmp"), "least": ("little", "Sup"),
}


def _undouble(stem: str) -> str:
    """stopped -> stopp -> stop"""
    if len(stem) >= 3 and stem[-1] == stem[-2] and stem[-1] not in _VOWELS:
        return stem[:-1]
    return stem


class SimpleAnalyzer:
    """Dependency-free analyzer that lists every plausible reading of each word."""

    def analyze(self, text: str) -> List[Token]:
        return [self._token(m) for m in _TOKEN_RE.findall(text or "")]

    def _token(self, raw: str) -> Token:
        if re.fullmatch(r"\d+(?:[.,]\d+)*", raw):
            return Token(raw, [Analysis(raw)], is_number=True)
        if not re.search(r"[A-Za-z]", raw):
            return Token(raw, [Analysis(raw)], is_punct=True)
        return Token(raw, self.hypotheses(raw.lower()))

    # -- readings ----------------------------------------------------------
    def hypotheses(self, w: str) -> List[Analysis]:
        out: List[Analysis] = [Analysis(w)]            # the word exactly as written

        if w in IRREGULAR:
            lemma, pos, feats = IRREGULAR[w]
            out.append(Analysis(lemma, pos, dict(feats)))
        if w in IRREGULAR_PRESENT:
            lemma, feats = IRREGULAR_PRESENT[w]
            out.append(Analysis(lemma, "VERB", dict(feats)))
        if w in IRREGULAR_NOUNS:
            out.append(Analysis(IRREGULAR_NOUNS[w], "NOUN", {"Number": "Plur"}))
        if w in IRREGULAR_ADJ:
            lemma, degree = IRREGULAR_ADJ[w]
            out.append(Analysis(lemma, "ADJ", {"Degree": degree}))

        # -s / -es / -ies / -ves : plural noun or 3rd-person verb
        stems: List[str] = []
        if w.endswith("ies") and len(w) > 4:
            stems.append(w[:-3] + "y")
        if w.endswith("ves") and len(w) > 4:
            stems += [w[:-3] + "f", w[:-3] + "fe"]
        if w.endswith("s") and not w.endswith("ss") and len(w) > 2:
            stems.append(w[:-1])
        if w.endswith("es") and len(w) > 3:
            stems.append(w[:-2])
        for s in dict.fromkeys(stems):
            out.append(Analysis(s, "NOUN", {"Number": "Plur"}))
        for s in dict.fromkeys(stems):
            out.append(Analysis(s, "VERB", {"Tense": "Pres", "Person": "3", "Number": "Sing", "VerbForm": "Fin"}))

        # -ed : past tense / past participle
        if w.endswith("ed") and len(w) > 3:
            stems = [w[:-2], w[:-1], _undouble(w[:-2])]
            if w.endswith("ied"):
                stems.insert(0, w[:-3] + "y")
            for s in dict.fromkeys(stems):
                out.append(Analysis(s, "VERB", dict(PAST)))

        # -ing : progressive / present participle
        if w.endswith("ing") and len(w) > 4:
            base = w[:-3]
            stems = [base, base + "e", _undouble(base)]
            if w.endswith("ying"):
                stems.insert(0, w[:-4] + "ie")
            for s in dict.fromkeys(stems):
                out.append(Analysis(s, "VERB", {"Aspect": "Prog", "Tense": "Pres", "VerbForm": "Part"}))

        # -er / -est : comparative / superlative
        for suffix, degree in (("est", "Sup"), ("er", "Cmp")):
            if w.endswith(suffix) and len(w) > len(suffix) + 2:
                base = w[: -len(suffix)]
                stems = [base, base + "e", _undouble(base)]
                if base.endswith("i"):
                    stems.insert(0, base[:-1] + "y")
                for s in dict.fromkeys(stems):
                    out.append(Analysis(s, "ADJ", {"Degree": degree}))

        seen, unique = set(), []
        for a in out:
            key = (a.lemma, a.pos, tuple(sorted(a.features.items())))
            if key not in seen:
                seen.add(key)
                unique.append(a)
        return unique


class SpacyAnalyzer:
    """spaCy-backed analyzer. Needs `pip install spacy` and `python -m spacy download en_core_web_sm`."""

    def __init__(self, model: str = "en_core_web_sm"):
        import spacy                      # imported lazily so the engine works without it
        self._nlp = spacy.load(model)
        self._fallback = SimpleAnalyzer()

    def analyze(self, text: str) -> List[Token]:
        tokens: List[Token] = []
        for t in self._nlp(text or ""):
            if t.is_space:
                continue
            raw = t.text
            if t.is_punct or not re.search(r"[A-Za-z\d]", raw):
                tokens.append(Token(raw, [Analysis(raw)], is_punct=True))
                continue
            if t.like_num and re.fullmatch(r"\d+(?:[.,]\d+)*", raw):
                tokens.append(Token(raw, [Analysis(raw)], is_number=True))
                continue
            primary = Analysis(t.lemma_.lower() or raw.lower(), t.pos_, t.morph.to_dict())
            hyps = [primary]
            for h in self._fallback.hypotheses(raw.lower()):
                if not any(h.lemma == x.lemma and h.pos == x.pos for x in hyps):
                    hyps.append(h)
            # the word exactly as written is still worth trying (idioms, proper nouns)
            tokens.append(Token(raw, hyps))
        return tokens
