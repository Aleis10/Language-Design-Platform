import json
from typing import Any, Dict
try:
    from database.db_Manager import Database_Manager
except ImportError:
    from .db_Manager import Database_Manager


class TypefaceRepository:
    # One row per language with the Typeface settings (scale, thickness, gaps). The values are stored as
    # plain JSON; the caller turns them into a complete style with normalize_style (digital_keyboard).
    def __init__(self, db_manager: Database_Manager):
        self.db_manager = db_manager
        self._ensure_tables()

    def _ensure_tables(self):
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute("""
                CREATE TABLE IF NOT EXISTS typeface_settings (
                    language_id TEXT PRIMARY KEY,
                    settings TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)

    def get(self, language_id: str) -> Dict[str, Any]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT settings FROM typeface_settings WHERE language_id = ?;", (language_id,))
            row = cursor.fetchone()
        if not row:
            return {}
        try:
            data = json.loads(row["settings"])
            return data if isinstance(data, dict) else {}
        except (TypeError, ValueError):
            return {}

    def save(self, language_id: str, settings: Dict[str, Any]) -> None:
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute(
                """
                INSERT INTO typeface_settings (language_id, settings) VALUES (?, ?)
                ON CONFLICT(language_id) DO UPDATE SET settings = excluded.settings,
                                                       updated_at = CURRENT_TIMESTAMP;
                """,
                (language_id, json.dumps(settings)),
            )

    def clear(self, language_id: str) -> None:
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute("DELETE FROM typeface_settings WHERE language_id = ?;", (language_id,))
