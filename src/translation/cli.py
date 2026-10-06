"""Try the engine on a real project from the command line.

    python -m translation.cli MyLanguage.langarc "The dogs chased the cat."
    python -m translation.cli MyLanguage.langarc            (interactive: type sentences)

Run it from the `src` folder. Options:
    --language ID     which language in the project (default: the first one)
    --ignore the,a    English words to drop when the lexicon has no entry for them
    --unknown MODE    bracket (default) | keep | skip
    --spacy           use spaCy for better part-of-speech / feature detection
    --raw             print real glyph characters instead of <E000> codes
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db_Manager import Database_Manager              # noqa: E402
from database.grammar_db import GrammarRepository             # noqa: E402
from database.lexicon_db import LexiconRepository             # noqa: E402
from translation import SimpleAnalyzer, SpacyAnalyzer, TranslationEngine   # noqa: E402


def _safe(text: str, raw: bool) -> str:
    """Terminals cannot draw your glyph font, so show private-use characters as <E000> unless --raw."""
    if raw:
        return text
    return re.sub(r"[\ue000-\uf8ff]", lambda m: f"<{ord(m.group(0)):04X}>", text)


def _open_db(path: str) -> str:
    if path.endswith(".db"):
        return path
    if not zipfile.is_zipfile(path):
        sys.exit(f"Not a .db file or a .langarc/.zip archive: {path}")
    out = tempfile.mkdtemp(prefix="translate_cli_")
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".db")]
        if not names:
            sys.exit("No database found inside the archive.")
        zf.extract(names[0], out)
    return os.path.join(out, names[0])


def _show(result, raw: bool) -> None:
    print(f"\n  English : {result.source_text}")
    print(f"  Conlang : {_safe(result.conlang_text, raw)}")
    print(f"  Gloss   : {result.gloss_text}")
    print()
    for w in result.words:
        if w.status in ("punct", "number"):
            continue
        shown = _safe(w.form, raw) if w.form else "(dropped)"
        extra = f"  {w.source}" if w.source != "stem" else ""
        flag = {"unknown": "  ?? unknown", "ambiguous": "  ~~ ambiguous"}.get(w.status, "")
        print(f"    {w.english:<14} -> {shown:<14} {w.gloss:<18}{extra}{flag}")
        for note in w.notes:
            print(f"        - {note}")
    if result.warnings:
        print("\n  Warnings:")
        for w in result.warnings:
            print(f"    * {w}")
    print()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Translate English with a project's lexicon and grammar.")
    ap.add_argument("project", help=".langarc / .zip archive, or a project.db file")
    ap.add_argument("text", nargs="?", help="English text (omit for interactive mode)")
    ap.add_argument("--language")
    ap.add_argument("--ignore", default="")
    ap.add_argument("--unknown", default="bracket", choices=["bracket", "keep", "skip"])
    ap.add_argument("--spacy", action="store_true")
    ap.add_argument("--raw", action="store_true")
    args = ap.parse_args(argv)

    dbm = Database_Manager(_open_db(args.project))
    lang = args.language
    if not lang:
        with dbm.get_connection() as conn:
            row = conn.execute("SELECT id FROM languages LIMIT 1;").fetchone()
        if not row:
            sys.exit("This project has no language yet.")
        lang = row[0]

    try:
        analyzer = SpacyAnalyzer() if args.spacy else SimpleAnalyzer()
    except Exception as exc:
        sys.exit(f"Could not start spaCy ({exc}).\nInstall:  pip install spacy  &&  python -m spacy download en_core_web_sm")

    engine = TranslationEngine.from_repos(
        LexiconRepository(dbm), GrammarRepository(dbm), lang,
        analyzer=analyzer, unknown=args.unknown, ignore=args.ignore.split(","),
    )
    print(f"Loaded {len(engine.index)} English glosses, {len(engine.rules)} rules, {len(engine.grids)} grids.")

    if args.text:
        _show(engine.translate(args.text), args.raw)
        return
    print("Type English and press Enter (empty line to quit).")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            break
        _show(engine.translate(line), args.raw)


if __name__ == "__main__":
    main()
