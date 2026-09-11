import uuid
from typing import Optional, Dict, Any, List
try:
    from database.db_Manager import Database_Manager
except ImportError:
    from .db_Manager import Database_Manager


class KeyboardRepository:
    def __init__(self, db_manager: Database_Manager):
        self.db_manager = db_manager
        self._ensure_tables()

    def _ensure_tables(self):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Named keyboard presets (layouts) per language
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS keyboard_presets (
                    id TEXT PRIMARY KEY,
                    language_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS keyboard_mappings (
                    id TEXT PRIMARY KEY,
                    preset_id TEXT NOT NULL,
                    language_id TEXT NOT NULL,
                    key_code TEXT NOT NULL,
                    key_label TEXT,
                    assignment TEXT,
                    ppua TEXT,
                    glyph_id TEXT,
                    position INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (preset_id) REFERENCES keyboard_presets (id) ON DELETE CASCADE,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_kb_preset_lang
                ON keyboard_mappings(preset_id, key_code);
            """)

            # Migration: older schema used language_id directly (no presets). Move rows into a default preset.
            cursor.execute("PRAGMA table_info(keyboard_mappings);")
            cols = {row["name"] for row in cursor.fetchall()}
            if "preset_id" not in cols:
                # Legacy table: rename/rebuild. Simplify — add col and backfill.
                cursor.execute("ALTER TABLE keyboard_mappings ADD COLUMN preset_id TEXT;")
                cursor.execute("PRAGMA table_info(keyboard_mappings);")
                cols = {row["name"] for row in cursor.fetchall()}
                if "preset_id" in cols:
                    cursor.execute("SELECT DISTINCT language_id FROM keyboard_mappings;")
                    for lang_row in cursor.fetchall():
                        lang_id = lang_row["language_id"]
                        preset_id = self._ensure_default_preset(cursor, lang_id)
                        cursor.execute(
                            "UPDATE keyboard_mappings SET preset_id = ? WHERE language_id = ? AND preset_id IS NULL;",
                            (preset_id, lang_id),
                        )

            expected = {
                "assignment": "TEXT",
                "ppua": "TEXT",
                "glyph_id": "TEXT",
                "key_label": "TEXT",
                "position": "INTEGER DEFAULT 0",
                "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            }
            for col, col_def in expected.items():
                if col not in cols:
                    cursor.execute(f"ALTER TABLE keyboard_mappings ADD COLUMN {col} {col_def};")

    def _ensure_default_preset(self, cursor, language_id: str) -> str:
        cursor.execute(
            "SELECT id FROM keyboard_presets WHERE language_id = ? AND name = 'Default';",
            (language_id,),
        )
        row = cursor.fetchone()
        if row:
            return row["id"]
        preset_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO keyboard_presets (id, language_id, name) VALUES (?, ?, 'Default');",
            (preset_id, language_id),
        )
        return preset_id

    # ---- Presets ----

    def get_presets(self, language_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM keyboard_presets WHERE language_id = ? ORDER BY created_at ASC;",
                (language_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_or_create_default_preset(self, language_id: str) -> str:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            preset_id = self._ensure_default_preset(cursor, language_id)
            return preset_id

    def create_preset(self, language_id: str, name: str) -> str:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM keyboard_presets WHERE language_id = ? AND name = ?;",
                (language_id, name),
            )
            row = cursor.fetchone()
            if row:
                return row["id"]
            preset_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO keyboard_presets (id, language_id, name) VALUES (?, ?, ?);",
                (preset_id, language_id, name),
            )
            return preset_id

    def rename_preset(self, preset_id: str, name: str):
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute(
                "UPDATE keyboard_presets SET name = ? WHERE id = ?;", (name, preset_id)
            )

    def delete_preset(self, preset_id: str):
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute(
                "DELETE FROM keyboard_presets WHERE id = ?;", (preset_id,)
            )

    # ---- Mappings ----

    def set_mapping(
        self,
        language_id: str,
        preset_id: str,
        key_code: str,
        assignment: str = "",
        ppua: str = "",
        glyph_id: Optional[str] = None,
        key_label: str = "",
    ) -> str:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM keyboard_mappings WHERE preset_id = ? AND key_code = ?;",
                (preset_id, key_code),
            )
            row = cursor.fetchone()
            if row:
                map_id = row["id"]
                cursor.execute(
                    """
                    UPDATE keyboard_mappings SET assignment = ?, ppua = ?, glyph_id = ?,
                           key_label = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """,
                    (assignment, ppua, glyph_id, key_label, map_id),
                )
                return map_id
            map_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO keyboard_mappings (id, preset_id, language_id, key_code, key_label,
                                               assignment, ppua, glyph_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (map_id, preset_id, language_id, key_code, key_label, assignment, ppua, glyph_id),
            )
            return map_id

    def get_mapping(self, preset_id: str, key_code: str) -> Optional[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM keyboard_mappings WHERE preset_id = ? AND key_code = ?;",
                (preset_id, key_code),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_mappings(self, preset_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM keyboard_mappings WHERE preset_id = ? ORDER BY key_code;",
                (preset_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def clear_mapping(self, preset_id: str, key_code: str):
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute(
                "DELETE FROM keyboard_mappings WHERE preset_id = ? AND key_code = ?;",
                (preset_id, key_code),
            )

    def clear_all_mappings(self, preset_id: str):
        with self.db_manager.get_connection() as conn:
            conn.cursor().execute(
                "DELETE FROM keyboard_mappings WHERE preset_id = ?;", (preset_id,)
            )

    def unassigned_glyphs(self, language_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, meaning, ipa_reading, svg_data FROM glyphs WHERE language_id = ? ORDER BY name;",
                (language_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_glyph(self, glyph_id: str) -> Optional[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, svg_data FROM glyphs WHERE id = ?;", (glyph_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None