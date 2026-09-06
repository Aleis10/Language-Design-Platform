import uuid
import json
from typing import Optional, Dict, Any, List
try:
    from database.db_Manager import Database_Manager
except ImportError:
    from .db_Manager import Database_Manager


class LanguageOverviewRepository:
    def __init__(self, db_manager: Database_Manager):
        self.db_manager = db_manager
        self._ensure_schema_extensions()

    def _ensure_schema_extensions(self):
        """Ensure language_overview and overview_custom_sections have all required UI fields."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check and extend language_overview table
            cursor.execute("PRAGMA table_info(language_overview);")
            overview_cols = {row["name"] for row in cursor.fetchall()}
            
            new_overview_cols = {
                "demonym": "TEXT",
                "speaker_population": "TEXT",
                "word_order": "TEXT",
                "morphology": "TEXT",
                "script_system": "TEXT",
                "history": "TEXT",
                "cultural_context": "TEXT",
                "status": "TEXT DEFAULT 'Drafting'",
            }
            for col, col_def in new_overview_cols.items():
                if col not in overview_cols:
                    cursor.execute(f"ALTER TABLE language_overview ADD COLUMN {col} {col_def};")

            # Check and extend overview_custom_sections table
            cursor.execute("PRAGMA table_info(overview_custom_sections);")
            section_cols = {row["name"] for row in cursor.fetchall()}
            if "section_type" not in section_cols:
                cursor.execute("ALTER TABLE overview_custom_sections ADD COLUMN section_type INTEGER DEFAULT 0;")

    def get_primary_language_id(self) -> Optional[str]:
        """Fetch the primary language ID (first registered project language)."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM languages ORDER BY created_at ASC LIMIT 1;")
            row = cursor.fetchone()
            return row["id"] if row else None

    def get_language_name(self, language_id: str) -> Optional[str]:
        """Fetch the display name of a language by its ID."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM languages WHERE id = ?;", (language_id,))
            row = cursor.fetchone()
            return row["name"] if row else None

    def create_initial_language(self, project_name: Optional[str] = None, language_type: str = "conlang_artlang") -> str:
        """Create the master language row and default language_overview row."""
        if not project_name or not project_name.strip():
            project_name = "Untitled Language"
        else:
            project_name = project_name.strip()

        language_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            # 1. Insert into languages
            cursor.execute(
                "INSERT INTO languages (id, name, language_type) VALUES (?, ?, ?);",
                (language_id, project_name, language_type)
            )
            # 2. Insert initial overview row with exonym pre-filled
            cursor.execute(
                """
                INSERT INTO language_overview (
                    language_id, exonym, status, is_spoken, is_extinct, is_constructed
                ) VALUES (?, ?, 'Drafting', 1, 0, 1);
                """,
                (language_id, project_name)
            )
        return language_id

    def get_overview_data(self, language_id: str) -> Dict[str, Any]:
        """Retrieve overview record as dictionary."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM language_overview WHERE language_id = ?;", (language_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            # If row doesn't exist, create an empty one
            cursor.execute(
                "INSERT INTO language_overview (language_id) VALUES (?);",
                (language_id,)
            )
            return {"language_id": language_id}

    def save_overview_data(self, language_id: str, data: Dict[str, Any]) -> None:
        """Save or update language overview fields."""
        allowed_cols = [
            "autonym", "exonym", "language_code", "is_spoken", "is_extinct",
            "is_constructed", "constructed_type", "genetic_classification",
            "glottocode", "iso_639_3", "notes", "demonym", "speaker_population",
            "word_order", "morphology", "script_system", "history", "cultural_context", "status"
        ]
        updates = {k: v for k, v in data.items() if k in allowed_cols}
        if not updates:
            return

        set_clause = ", ".join([f"{col} = ?" for col in updates.keys()])
        params = list(updates.values()) + [language_id]

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE language_overview SET {set_clause} WHERE language_id = ?;",
                params
            )

    def get_custom_sections(self, language_id: str) -> List[Dict[str, Any]]:
        """Fetch custom section cards ordered by position."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM overview_custom_sections WHERE language_id = ? ORDER BY position ASC, created_at ASC;",
                (language_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def add_custom_section(self, language_id: str, title: str, section_type: int, content: str = "", position: int = 0) -> str:
        """Create a new custom card record and return its UUID."""
        section_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO overview_custom_sections (id, language_id, title, content, section_type, position)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (section_id, language_id, title, content, section_type, position)
            )
        return section_id

    def update_custom_section(self, section_id: str, title: Optional[str] = None, content: Optional[str] = None, position: Optional[int] = None):
        """Update fields of an existing custom section."""
        fields = []
        params = []
        if title is not None:
            fields.append("title = ?")
            params.append(title)
        if content is not None:
            fields.append("content = ?")
            params.append(content)
        if position is not None:
            fields.append("position = ?")
            params.append(position)
        
        if not fields:
            return

        params.append(section_id)
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE overview_custom_sections SET {', '.join(fields)} WHERE id = ?;",
                params
            )

    def delete_custom_section(self, section_id: str):
        """Delete a custom section by ID."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM overview_custom_sections WHERE id = ?;", (section_id,))
