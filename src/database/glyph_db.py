import uuid
import os
from typing import Optional, Dict, Any, List
try:
    from database.db_Manager import Database_Manager
except ImportError:
    from .db_Manager import Database_Manager

class GlyphRepository:
    def __init__(self, db_manager: Database_Manager):
        self.db_manager = db_manager
        self._ensure_tables()

    def _ensure_tables(self):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS glyph_groups (
                    id TEXT PRIMARY KEY,
                    language_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    position INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS glyphs (
                    id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    language_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    meaning TEXT,
                    ipa_reading TEXT,
                    svg_data TEXT,
                    audio_path TEXT,
                    position INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (group_id) REFERENCES glyph_groups (id) ON DELETE CASCADE,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)

            cursor.execute("PRAGMA table_info(glyphs);")
            cols = {row["name"] for row in cursor.fetchall()}
            expected_cols = {
                "meaning": "TEXT",
                "ipa_reading": "TEXT",
                "svg_data": "TEXT",
                "audio_path": "TEXT",
                "position": "INTEGER DEFAULT 0",
                "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            }
            for col, col_def in expected_cols.items():
                if col not in cols:
                    cursor.execute(f"ALTER TABLE glyphs ADD COLUMN {col} {col_def};")

    def get_groups(self, language_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM glyph_groups WHERE language_id = ? ORDER BY position ASC, created_at ASC;",
                (language_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def add_group(self, language_id: str, name: str, description: str = "", position: int = 0) -> str:
        group_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO glyph_groups (id, language_id, name, description, position) VALUES (?, ?, ?, ?, ?);",
                (group_id, language_id, name.strip(), description.strip(), position)
            )
        return group_id

    def update_group(self, group_id: str, name: Optional[str] = None, description: Optional[str] = None, position: Optional[int] = None):
        fields = []
        params = []
        if name is not None:
            fields.append("name = ?")
            params.append(name.strip())
        if description is not None:
            fields.append("description = ?")
            params.append(description.strip())
        if position is not None:
            fields.append("position = ?")
            params.append(position)
        
        if not fields:
            return

        params.append(group_id)
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE glyph_groups SET {', '.join(fields)} WHERE id = ?;", params)

    def delete_group(self, group_id: str):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM glyph_groups WHERE id = ?;", (group_id,))

    def get_glyphs_by_group(self, group_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM glyphs WHERE group_id = ? ORDER BY position ASC, created_at ASC;",
                (group_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_glyphs(self, language_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM glyphs WHERE language_id = ? ORDER BY position ASC, created_at ASC;",
                (language_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_glyph(self, glyph_id: str) -> Optional[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM glyphs WHERE id = ?;", (glyph_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_glyph(
        self,
        language_id: str,
        group_id: str,
        name: str,
        meaning: str = "",
        ipa_reading: str = "",
        svg_data: str = "",
        audio_path: str = "",
        position: int = 0
    ) -> str:
        glyph_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO glyphs (
                    id, group_id, language_id, name, meaning, ipa_reading, svg_data, audio_path, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (glyph_id, group_id, language_id, name.strip(), meaning.strip(), ipa_reading.strip(), svg_data, audio_path, position)
            )
        return glyph_id

    def update_glyph(
        self,
        glyph_id: str,
        name: Optional[str] = None,
        meaning: Optional[str] = None,
        ipa_reading: Optional[str] = None,
        svg_data: Optional[str] = None,
        audio_path: Optional[str] = None,
        group_id: Optional[str] = None,
        position: Optional[int] = None
    ):
        fields = []
        params = []
        if name is not None:
            fields.append("name = ?")
            params.append(name.strip())
        if meaning is not None:
            fields.append("meaning = ?")
            params.append(meaning.strip())
        if ipa_reading is not None:
            fields.append("ipa_reading = ?")
            params.append(ipa_reading.strip())
        if svg_data is not None:
            fields.append("svg_data = ?")
            params.append(svg_data)
        if audio_path is not None:
            fields.append("audio_path = ?")
            params.append(audio_path)
        if group_id is not None:
            fields.append("group_id = ?")
            params.append(group_id)
        if position is not None:
            fields.append("position = ?")
            params.append(position)

        if not fields:
            return

        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(glyph_id)
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE glyphs SET {', '.join(fields)} WHERE id = ?;", params)

    def delete_glyph(self, glyph_id: str):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM glyphs WHERE id = ?;", (glyph_id,))
