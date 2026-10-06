"""Per-language settings for the Transcribe page, stored in the project database
(so they are saved inside the .langarc together with everything else)."""
import json
from typing import Any, Dict

try:
    from database.db_Manager import Database_Manager
except ImportError:                                   # pragma: no cover
    from .db_Manager import Database_Manager

DEFAULTS: Dict[str, Any] = {
    "ignore_words": ["the", "a", "an"],   # English words dropped when the lexicon has no entry for them
    "unknown": "bracket",                  # bracket -> [word] | keep -> word | skip -> omit
    "analyzer": "auto",                    # auto | builtin | spacy
    "whisper_model": "base.en",
    "auto_translate": True,                # translate straight after speech is transcribed
}


class TranscribeSettingsRepository:
    def __init__(self, db_manager: Database_Manager):
        self.db_manager = db_manager
        self._ensure_tables()

    def _ensure_tables(self):
        with self.db_manager.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transcribe_settings (
                    language_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (language_id, key),
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)

    def get_all(self, language_id: str) -> Dict[str, Any]:
        out = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
        with self.db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT key, value FROM transcribe_settings WHERE language_id = ?;", (language_id,)
            ).fetchall()
        for row in rows:
            try:
                out[row["key"]] = json.loads(row["value"])
            except (TypeError, ValueError):
                pass
        return out

    def set_many(self, language_id: str, values: Dict[str, Any]) -> None:
        with self.db_manager.get_connection() as conn:
            for key, value in values.items():
                conn.execute(
                    "INSERT INTO transcribe_settings (language_id, key, value) VALUES (?, ?, ?) "
                    "ON CONFLICT(language_id, key) DO UPDATE SET value = excluded.value;",
                    (language_id, key, json.dumps(value)),
                )
