"""Step 2: turn a dictionary form into the form the sentence needs.

For every word the engine works out which grammatical features English asked for
(plural, past, ...). It then finds a way to express each one in the conlang:

    1. a paradigm-grid cell that matches all the features   (exact, handles irregulars)
    2. otherwise the affix rules whose gloss tag matches    (regular morphology)
    3. otherwise the bare dictionary form, with a warning

Everything here is plain Python over plain dicts, so it is easy to test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from .lookup import UD_TO_CLASS, pos_class, split_glosses

Alias = Union[str, Tuple[str, ...]]


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def norm_tag(text: str) -> str:
    """'3.SG' / '3sg' / 'Pst' -> '3SG' / '3SG' / 'PST' (letters and digits only, upper case)."""
    return re.sub(r"[^A-Za-z0-9]", "", text or "").upper()


def label_tags(label: str) -> Set[str]:
    """Tags named by a grid label: 'NOM.SG' -> {NOM, SG, NOMSG}; 'Past tense' -> {PAST, TENSE, PASTTENSE}."""
    parts = [norm_tag(p) for p in re.split(r"[.\s/+:;,_\-]+", label or "") if norm_tag(p)]
    tags = set(parts)
    if len(parts) > 1:
        tags.add("".join(parts))
    return tags


@dataclass
class FeatureRequest:
    name: str                      # human name, e.g. "plural"
    aliases: List[Alias]           # tags that can express it, best first
    required: bool = True          # False = apply if the language has it, stay silent if not

    @property
    def display(self) -> str:
        first = self.aliases[0]
        return first if isinstance(first, str) else "".join(first)


PLURAL = ["PL", "PLUR", "PLURAL"]
SINGULAR = ["SG", "SING", "SINGULAR"]
PAST_TAGS = ["PST", "PAST", "PRET", "PRETERITE"]
PRESENT = ["PRS", "PRES", "PRESENT", "NPST", "NONPAST"]
THIRD_SG = ["3SG", "3S", "3SGPRS", "3SGPRES", ("3", "SG")]
PAST_PTCP = ["PSTP", "PASTP", "PTCPPST", "PSTPTCP", "PASTPTCP", "PPTCP", ("PTCP", "PST"),
             ("PTCP", "PAST")] + PAST_TAGS
PROGRESSIVE = ["PROG", "PROGRESSIVE", "IPFV", "IMPF", "IPFV", "PRSP", "PTCPPRS", "PRESPTCP",
               "GER", "GERUND", ("PTCP", "PRS"), ("PTCP", "PRES")]
COMPARATIVE = ["CMP", "COMP", "COMPARATIVE"]
SUPERLATIVE = ["SUP", "SUPL", "SUPERLATIVE"]


def requested_features(pos: str, feats: Dict[str, str]) -> List[FeatureRequest]:
    """What grammatical features does this English reading need the conlang to express?"""
    cls = UD_TO_CLASS.get(pos or "")
    f = feats or {}
    out: List[FeatureRequest] = []
    if cls in ("NOUN", "PRON", None):
        if f.get("Number") == "Plur" and cls != "VERB":
            out.append(FeatureRequest("plural", list(PLURAL)))
        elif f.get("Number") == "Sing" and cls in ("NOUN", "PRON"):
            out.append(FeatureRequest("singular", list(SINGULAR), required=False))
    if cls == "VERB":
        form, tense = f.get("VerbForm"), f.get("Tense")
        if form == "Part" and tense == "Past":
            out.append(FeatureRequest("past participle", list(PAST_PTCP)))
        elif f.get("Aspect") == "Prog" or (form in ("Part", "Ger") and tense == "Pres"):
            out.append(FeatureRequest("progressive", list(PROGRESSIVE)))
        elif tense == "Past":
            out.append(FeatureRequest("past", list(PAST_TAGS)))
        elif tense == "Pres" and form in (None, "Fin"):
            if f.get("Person") == "3" and f.get("Number") == "Sing":
                out.append(FeatureRequest("3rd person singular", list(THIRD_SG), required=False))
            out.append(FeatureRequest("present", list(PRESENT), required=False))
    if cls == "ADJ" or cls == "ADV":
        if f.get("Degree") == "Cmp":
            out.append(FeatureRequest("comparative", list(COMPARATIVE)))
        elif f.get("Degree") == "Sup":
            out.append(FeatureRequest("superlative", list(SUPERLATIVE)))
    return out


def alias_matches_rule(alias: Alias, rule_tag_norm: str) -> bool:
    joined = alias if isinstance(alias, str) else "".join(alias)
    return joined == rule_tag_norm


def alias_in_tags(alias: Alias, tags: Set[str]) -> bool:
    if isinstance(alias, str):
        return alias in tags
    return all(a in tags for a in alias)


# ---------------------------------------------------------------------------
# Affixes
# ---------------------------------------------------------------------------

_CIRCUM_SEPARATORS = ("...", "\u2026", "*", "/", "+")


def apply_affix(stem: str, pattern: str, affix_type: str = "") -> Tuple[Optional[str], str]:
    """Attach one affix to `stem`. Returns (new_form, note); new_form is None if it cannot be applied.

    Pattern syntax (typed the way linguists write it):
        -ya        suffix            un-        prefix
        -en-       infix (inserted after the 1st character; `-en-@2` = after the 2nd,
                   `-en-@-1` = before the last)
        ge-...-t   circumfix (also  ge-*-t  or  ge- -t)
        {stem}     anywhere: replaced by the stem, e.g. "{stem}{stem}" = reduplication

    The hyphen shape beats the "affix type" dropdown, because the dropdown defaults to
    "suffix" and is easy to leave unchanged. If they disagree a note is returned.
    """
    pattern = (pattern or "").strip()
    atype = (affix_type or "").strip().lower()
    if not pattern:
        return None, "rule has no affix pattern"

    if "{stem}" in pattern:
        return pattern.replace("{stem}", stem), ""

    # circumfix
    sep = next((s for s in _CIRCUM_SEPARATORS if s in pattern), None)
    parts = None
    if sep:
        parts = pattern.split(sep, 1)
    elif atype == "circumfix":
        pieces = pattern.split()
        if len(pieces) == 2:
            parts = pieces
        else:
            return None, "circumfix pattern needs a separator, e.g. ge-...-t"
    if parts is not None:
        pre, suf = parts[0].strip().strip("-"), parts[1].strip().strip("-")
        return pre + stem + suf, ""

    pos = 1
    m = re.search(r"@(-?\d+)$", pattern)
    if m:
        pos = int(m.group(1))
        pattern = pattern[: m.start()]
    starts, ends = pattern.startswith("-"), pattern.endswith("-")
    core = pattern.strip("-").strip()
    if not core:
        return None, "affix pattern is empty"

    if starts and ends:
        kind = "infix"
    elif starts:
        kind = "suffix"
    elif ends:
        kind = "prefix"
    elif atype in ("prefix", "suffix", "infix"):
        kind = atype
    else:
        return None, f"affix type '{atype or 'other'}' (tone, stress, other) cannot be applied automatically"

    note = ""
    if atype in ("prefix", "suffix", "infix") and atype != kind and (starts or ends):
        note = f"pattern '{pattern}' looks like a {kind} but the rule says {atype}; used {kind}"

    if kind == "prefix":
        return core + stem, note
    if kind == "suffix":
        return stem + core, note
    # infix
    index = pos if pos >= 0 else len(stem) + pos
    index = max(0, min(len(stem), index))
    return stem[:index] + core + stem[index:], note


# ---------------------------------------------------------------------------
# Prepared grammar data
# ---------------------------------------------------------------------------

def pos_hint(text: str) -> Optional[Set[str]]:
    """'Noun morphology' -> {'NOUN'}.  Lets a category or grid name restrict itself to a part of speech."""
    t = (text or "").lower()
    for pat, cls in ((r"\bnoun", "NOUN"), (r"\bverb", "VERB"), (r"\badj", "ADJ"),
                     (r"\badv", "ADV"), (r"\bpron", "PRON")):
        if re.search(pat, t):
            return {cls}
    return None


@dataclass
class PreparedRule:
    id: str
    name: str
    pattern: str
    affix_type: str
    gloss_tag: str
    tag_norm: str
    position: int
    hint: Optional[Set[str]]


def prepare_rules(rules: Sequence[Dict[str, Any]], categories: Sequence[Dict[str, Any]]) -> List[PreparedRule]:
    cat_names = {c.get("id"): c.get("name", "") for c in categories}
    prepared = []
    for r in rules:
        tag = (r.get("gloss_tag") or "").strip()
        if not tag:
            continue
        prepared.append(PreparedRule(
            id=str(r.get("id", "")),
            name=r.get("name", "") or tag,
            pattern=r.get("affix_pattern") or "",
            affix_type=r.get("affix_type") or "",
            gloss_tag=tag.upper(),
            tag_norm=norm_tag(tag),
            position=int(r.get("position") or 0),
            hint=pos_hint(cat_names.get(r.get("category_id"), "")),
        ))
    return sorted(prepared, key=lambda r: r.position)


@dataclass
class Cell:
    text: str
    tags: Set[str]


@dataclass
class PreparedGrid:
    name: str
    hint: Optional[Set[str]]
    cells: List[Cell] = field(default_factory=list)


def prepare_grids(grids: Sequence[Dict[str, Any]]) -> List[PreparedGrid]:
    """Read grids saved as headers=[corner, col1, ...] and rows=[[row_label, cell1, ...], ...]."""
    out = []
    for g in grids:
        headers = [str(h) for h in (g.get("headers") or [])]
        if not headers:
            continue
        n = len(headers)
        pg = PreparedGrid(name=g.get("name", ""), hint=pos_hint(g.get("name", "")))
        for row in g.get("rows") or []:
            row = [str(c) for c in row]
            if len(row) == n - 1:               # saved by the old dialog: no row label
                row = [""] + row
            row = (row + [""] * n)[:n]
            row_tags = label_tags(row[0])
            for ci in range(1, n):
                if row[ci].strip():
                    pg.cells.append(Cell(row[ci].strip(), row_tags | label_tags(headers[ci])))
        out.append(pg)
    return out


_GENERIC_GRID_WORDS = {
    "noun", "nouns", "verb", "verbs", "adjective", "adjectives", "adj", "adverb", "adverbs", "adv",
    "pronoun", "pronouns", "pron", "declension", "declensions", "conjugation", "conjugations",
    "paradigm", "paradigms", "inflection", "inflections", "forms", "form", "table", "grid", "endings",
    "regular", "the", "a", "of", "for", "all",
}


def _is_class_grid(name: str) -> bool:
    """'Noun declension' covers every noun; 'Verb: to go' is about one word, not a whole class."""
    words = re.findall(r"[^\W\d_]+", (name or "").lower())
    return all(w in _GENERIC_GRID_WORDS for w in words)


def _grid_specificity(grid: PreparedGrid, entry: Dict[str, Any], lemma: str, word_class: Optional[str]) -> int:
    """2 = grid is about this word, 1 = grid is about this kind of word, 0 = not applicable."""
    name = grid.name or ""
    headword = (entry.get("headword") or "").strip()
    if headword and headword in name:
        return 2
    keys = set(split_glosses(entry.get("english_translation")))
    if lemma:
        keys.add(lemma.lower())
    for k in keys:
        if k and re.search(rf"(?<![A-Za-z]){re.escape(k)}(?![A-Za-z])", name, re.IGNORECASE):
            return 2
    if grid.hint and word_class and word_class in grid.hint and _is_class_grid(name):
        return 1
    return 0


def find_grid_form(
    grids: Sequence[PreparedGrid], entry: Dict[str, Any], lemma: str,
    word_class: Optional[str], reqs: Sequence[FeatureRequest],
) -> Optional[Tuple[str, str, List[str]]]:
    """(cell text, grid name, tags as written in the grid) of the best cell covering every feature."""
    if not reqs:
        return None
    for level in (2, 1):
        for grid in grids:
            if _grid_specificity(grid, entry, lemma, word_class) != level:
                continue
            best: Optional[Cell] = None
            for cell in grid.cells:
                if all(any(alias_in_tags(a, cell.tags) for a in r.aliases) for r in reqs):
                    if best is None or len(cell.tags) < len(best.tags):
                        best = cell
            if best:
                shown = []
                for r in reqs:
                    alias = next(a for a in r.aliases if alias_in_tags(a, best.tags))
                    shown.append(alias if isinstance(alias, str) else "".join(alias))
                return best.text, grid.name, shown
    return None


def find_rule(req: FeatureRequest, rules: Sequence[PreparedRule], word_class: Optional[str]) -> Optional[PreparedRule]:
    for alias in req.aliases:
        matches = [r for r in rules if alias_matches_rule(alias, r.tag_norm)
                   and not (r.hint and word_class and word_class not in r.hint)]
        if matches:
            hinted = [r for r in matches if r.hint and word_class in r.hint]
            return (hinted or matches)[0]
    return None


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------

@dataclass
class InflectResult:
    form: str
    applied: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    source: str = "stem"
    notes: List[str] = field(default_factory=list)


def inflect(
    entry: Dict[str, Any], lemma: str, pos: str, feats: Dict[str, str],
    rules: Sequence[PreparedRule], grids: Sequence[PreparedGrid],
) -> InflectResult:
    stem = (entry.get("headword") or "").strip()
    reqs = requested_features(pos, feats)
    result = InflectResult(form=stem)
    if not reqs:
        return result

    entry_class = pos_class(entry.get("part_of_speech"))
    word_class = UD_TO_CLASS.get(pos or "") or entry_class
    if entry_class and word_class and entry_class != word_class:
        result.notes.append(f"English reads as {word_class} but the entry is {entry_class}")

    # 1) paradigm grid: all features, then only the required ones
    tries = [list(reqs)]
    required_only = [r for r in reqs if r.required]
    if required_only and len(required_only) != len(reqs):
        tries.append(required_only)
    for subset in tries:
        hit = find_grid_form(grids, entry, lemma, word_class, subset)
        if hit:
            text, grid_name, shown = hit
            if text.startswith("-") or text.endswith("-"):
                new, note = apply_affix(stem, text)
                if new is not None:
                    result.form, result.source = new, f"grid:{grid_name}"
                    result.applied = shown
                    if note:
                        result.notes.append(note)
                    return result
            else:
                result.form, result.source = text, f"grid:{grid_name}"
                result.applied = shown
                return result

    # 2) affix rules, in the order the rules are listed
    chosen: List[Tuple[PreparedRule, FeatureRequest]] = []
    for r in reqs:
        rule = find_rule(r, rules, word_class)
        if rule is None:
            if r.required:
                result.missing.append(r.display)
        elif all(rule.id != c[0].id for c in chosen):
            chosen.append((rule, r))
    form = stem
    names = []
    for rule, req in sorted(chosen, key=lambda c: c[0].position):
        new, note = apply_affix(form, rule.pattern, rule.affix_type)
        if new is None:
            result.missing.append(rule.gloss_tag)
            result.notes.append(f"{rule.name}: {note}")
            continue
        form = new
        result.applied.append(rule.gloss_tag)
        names.append(rule.name)
        if note:
            result.notes.append(f"{rule.name}: {note}")
    result.form = form
    if names:
        result.source = "rule:" + "+".join(names)
    return result
