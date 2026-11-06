from typing import Dict, List, Optional

from .inflect import (
    COMPARATIVE, PAST_PTCP, PAST_TAGS, PLURAL, PRESENT, PROGRESSIVE, SINGULAR, SUPERLATIVE, THIRD_SG,
    alias_matches_rule, norm_tag,
)

# Grammatical features the user defines for their language (Number, Tense ...), and what the translator can
# detect on its own. A feature value can listen for one English "trigger", for example the value "Plural"
# listens for the trigger "plural". A value with no trigger is never applied automatically.
# No Qt and no database in here.

# what the English side can ask for: (key, label). These keys are exactly the ones inflect.requested_features uses.
TRIGGERS = [
    ("plural", "Plural noun"),
    ("singular", "Singular noun"),
    ("present", "Present tense"),
    ("past", "Past tense"),
    ("past_participle", "Past participle"),
    ("progressive", "Progressive (-ing)"),
    ("3sg", "3rd person singular (he runs)"),
    ("comparative", "Comparative (bigger)"),
    ("superlative", "Superlative (biggest)"),
]
TRIGGER_KEYS = [key for key, _label in TRIGGERS]
TRIGGER_LABELS = dict(TRIGGERS)

WORD_CLASSES = [("NOUN", "Noun"), ("VERB", "Verb"), ("ADJ", "Adjective"), ("ADV", "Adverb"), ("PRON", "Pronoun")]
WORD_CLASS_KEYS = [key for key, _label in WORD_CLASSES]

# how people usually spell the tag of each trigger (the older way rules were matched), most specific first
TRIGGER_ALIASES = [
    ("plural", PLURAL),
    ("singular", SINGULAR),
    ("present", PRESENT),
    ("past", PAST_TAGS),
    ("past_participle", PAST_PTCP),
    ("progressive", PROGRESSIVE),
    ("3sg", THIRD_SG),
    ("comparative", COMPARATIVE),
    ("superlative", SUPERLATIVE),
]

# the starter set every language gets, to be edited freely
DEFAULT_FEATURES: List[Dict] = [
    {"name": "Number", "word_classes": ["NOUN", "PRON"], "values": [
        {"tag": "SG", "label": "Singular", "trigger": "singular"},
        {"tag": "PL", "label": "Plural", "trigger": "plural"},
    ]},
    {"name": "Tense", "word_classes": ["VERB"], "values": [
        {"tag": "PRS", "label": "Present", "trigger": "present"},
        {"tag": "PST", "label": "Past", "trigger": "past"},
    ]},
    {"name": "Verb form", "word_classes": ["VERB"], "values": [
        {"tag": "PROG", "label": "Progressive", "trigger": "progressive"},
        {"tag": "PSTP", "label": "Past participle", "trigger": "past_participle"},
    ]},
    {"name": "Person", "word_classes": ["VERB"], "values": [
        {"tag": "3SG", "label": "Third person singular", "trigger": "3sg"},
    ]},
    {"name": "Degree", "word_classes": ["ADJ", "ADV"], "values": [
        {"tag": "CMP", "label": "Comparative", "trigger": "comparative"},
        {"tag": "SUP", "label": "Superlative", "trigger": "superlative"},
    ]},
]


def trigger_for_tag(tag: str) -> Optional[str]:
    """The trigger a tag such as 'PLUR' or 'PAST' usually stands for, or None when it is not a familiar one."""
    n = norm_tag(tag or "")
    if not n:
        return None
    for key, aliases in TRIGGER_ALIASES:
        if any(alias_matches_rule(a, n) for a in aliases):
            return key
    return None
