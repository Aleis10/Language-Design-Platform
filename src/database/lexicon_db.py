import uuid
from typing import Optional, Dict, Any, List
try:
    from database.db_Manager import Database_Manager
except ImportError:
    from .db_Manager import Database_Manager

class LexiconRepository:
    def __init__(self, db_manager: Database_Manager):
        self.db_manager = db_manager
        self._ensure_tables()

    def _ensure_tables(self):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lexicon (
                    id TEXT PRIMARY KEY,
                    language_id TEXT NOT NULL,
                    headword TEXT NOT NULL,
                    ipa_reading TEXT,
                    part_of_speech TEXT,
                    meaning TEXT NOT NULL,
                    english_translation TEXT,
                    description TEXT,
                    audio_path TEXT,
                    glyph_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_lexicon_lang_headword
                ON lexicon(language_id, headword);
            """)

 # Migration: add missing columns for existing .langarc projects
            cursor.execute("PRAGMA table_info(lexicon);")
            existing = {row["name"] for row in cursor.fetchall()}
            migrations = {
                "ipa_reading": "TEXT",
                "part_of_speech": "TEXT",
                "english_translation": "TEXT",
                "description": "TEXT",
                "audio_path": "TEXT",
                "glyph_id": "TEXT",
                "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            }
            for col, col_def in migrations.items():
                if col not in existing:
                    cursor.execute(f"ALTER TABLE lexicon ADD COLUMN {col} {col_def};")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS lexicon_audio (
                    id TEXT PRIMARY KEY,
                    entry_id TEXT NOT NULL,
                    variant_label TEXT DEFAULT '',
                    ipa_reading TEXT,
                    audio_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (entry_id) REFERENCES lexicon (id) ON DELETE CASCADE
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lexicon_audio_entry
                ON lexicon_audio(entry_id);
                """
            )

 # Migration: bring over any legacy single audio_path -> lexicon_audio row
            cursor.execute(
                "SELECT id, audio_path, ipa_reading FROM lexicon "
                "WHERE audio_path IS NOT NULL AND audio_path != '';"
            )
            legacy_rows = cursor.fetchall()
            if legacy_rows:
                cursor.execute("SELECT entry_id FROM lexicon_audio;")
                migrated = {r[0] for r in cursor.fetchall()}
                if not migrated:
                    for entry_id, audio_path, ipa in legacy_rows:
                        cursor.execute(
                            "INSERT INTO lexicon_audio (id, entry_id, variant_label, ipa_reading, audio_path) "
                            "VALUES (?, ?, '', ?, ?);",
                            (str(uuid.uuid4()), entry_id, ipa or "", audio_path),
                        )

    def find_by_headword(self, headword: str, language_id: str) -> Optional[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT headword, ipa_reading, part_of_speech, meaning, english_translation, "
                "description, audio_path, glyph_id "
                "FROM lexicon WHERE language_id = ? AND headword = ?;",
                (language_id, headword.strip()),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_headwords(self, language_id: str) -> List[str]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT headword FROM lexicon WHERE language_id = ? ORDER BY headword;",
                (language_id,),
            )
            return [row[0] for row in cursor.fetchall()]

    def add_entry(
        self,
        language_id: str,
        headword: str,
        meaning: str,
        ipa_reading: str = "",
        part_of_speech: str = "",
        english_translation: str = "",
        description: str = "",
        audio_path: str = "",
        glyph_id: Optional[str] = None,
    ) -> str:
        entry_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO lexicon (id, language_id, headword, meaning, ipa_reading,
                                     part_of_speech, english_translation, description,
                                     audio_path, glyph_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    entry_id, language_id, headword.strip(), meaning.strip(),
                    ipa_reading.strip(), part_of_speech.strip(), english_translation.strip(),
                    description.strip(), audio_path.strip(), glyph_id,
                ),
            )
        return entry_id

    def update_entry(self, entry_id: str, **fields):
        allowed = {"headword", "meaning", "ipa_reading", "part_of_speech",
                   "english_translation", "description", "audio_path", "glyph_id"}
        updates = []
        params = []
        for key, val in fields.items():
            if key in allowed and val is not None:
                updates.append(f"{key} = ?")
                params.append(val.strip() if isinstance(val, str) else val)
        if not updates:
            return
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(entry_id)
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute(f"UPDATE lexicon SET {', '.join(updates)} WHERE id = ?;", params)

    def delete_entry(self, entry_id: str):
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute("DELETE FROM lexicon WHERE id = ?;", (entry_id,))

    def get_all_entries(self, language_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM lexicon WHERE language_id = ? ORDER BY headword ASC;",
                (language_id,),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            for entry in rows:
                entry["audio_variants"] = self.get_entry_audio(entry["id"])
            return rows

    def get_entry_audio(self, entry_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, variant_label, ipa_reading, audio_path "
                "FROM lexicon_audio WHERE entry_id = ? ORDER BY created_at ASC;",
                (entry_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def add_entry_audio(self, entry_id: str, audio_path: str, ipa_reading: str = "", variant_label: str = "") -> str:
        audio_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute(
                "INSERT INTO lexicon_audio (id, entry_id, variant_label, ipa_reading, audio_path) "
                "VALUES (?, ?, ?, ?, ?);",
                (audio_id, entry_id, variant_label.strip(), ipa_reading.strip(), audio_path.strip()),
            )
        return audio_id

    def update_entry_audio(self, audio_id: str, **fields):
        allowed = {"variant_label", "ipa_reading", "audio_path"}
        updates = []
        params = []
        for key, val in fields.items():
            if key in allowed and val is not None:
                updates.append(f"{key} = ?")
                params.append(val.strip() if isinstance(val, str) else val)
        if not updates:
            return
        params.append(audio_id)
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute(f"UPDATE lexicon_audio SET {', '.join(updates)} WHERE id = ?;", params)

    def delete_entry_audio(self, audio_id: str):
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute("DELETE FROM lexicon_audio WHERE id = ?;", (audio_id,))

    def delete_all_entry_audio(self, entry_id: str):
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute("DELETE FROM lexicon_audio WHERE entry_id = ?;", (entry_id,))

    def search(self, language_id: str, query: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            like = f"%{query.strip()}%"
            cursor.execute(
                """
                SELECT * FROM lexicon
                WHERE language_id = ?
                  AND (headword LIKE ? OR meaning LIKE ? OR ipa_reading LIKE ?)
                ORDER BY headword ASC;
                """,
                (language_id, like, like, like),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            for entry in rows:
                entry["audio_variants"] = self.get_entry_audio(entry["id"])
            return rows
