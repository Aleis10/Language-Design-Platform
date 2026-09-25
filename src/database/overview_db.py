import uuid
from typing import Dict, List, Any, Optional
from database.db_Manager import Database_Manager

class LanguageOverviewRepository:
    def __init__(self, db_manager: Database_Manager):
        self.db = db_manager

    def create_initial_language(self, project_name: str, language_type: str = "conlang_artlang") -> str:
        language_id = str(uuid.uuid4())
        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO languages (id, name, language_type) VALUES (?, ?, ?);",
                (language_id, project_name, language_type)
            )
            conn.execute(
                "INSERT INTO language_overview (language_id, exonym) VALUES (?, ?);",
                (language_id, project_name)
            )
        return language_id

    def get_primary_language_id(self) -> Optional[str]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT id FROM languages LIMIT 1;").fetchone()
            return row["id"] if row else None

    def get_overview_data(self, language_id: str) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM language_overview WHERE language_id = ?;",
                (language_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_overview_field(self, language_id: str, field_name: str, value: Any):
        allowed_fields = {
                    "autonym", "exonym", "language_code", "is_spoken", "is_extinct",
                    "is_constructed", "constructed_type", "genetic_classification",
                    "glottocode", "iso_639_3", "notes",
                    "demonym", "speaker_population",
                    "word_order", "morphology", "script_system",
                    "history", "cultural_context", "status"
                }
        if field_name not in allowed_fields:
            raise ValueError(f"Invalid field name: {field_name}")

        query = f"UPDATE language_overview SET {field_name} = ? WHERE language_id = ?;"
        with self.db.get_connection() as conn:
            conn.execute(query, (value, language_id))

    def get_custom_sections(self, language_id: str) -> List[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, title, content, position 
                FROM overview_custom_sections 
                WHERE language_id = ? 
                ORDER BY position ASC;
                """,
                (language_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def add_custom_section(self, language_id: str, title: str, content: str = "") -> str:
        section_id = str(uuid.uuid4())
        with self.db.get_connection() as conn:
            pos_row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM overview_custom_sections WHERE language_id = ?;",
                (language_id,)
            ).fetchone()
            next_pos = pos_row["next_pos"]

            conn.execute(
                """
                INSERT INTO overview_custom_sections (id, language_id, title, content, position)
                VALUES (?, ?, ?, ?, ?);
                """,
                (section_id, language_id, title, content, next_pos)
            )
        return section_id

    def update_custom_section(self, section_id: str, title: str, content: str):
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE overview_custom_sections SET title = ?, content = ? WHERE id = ?;",
                (title, content, section_id)
            )

    def delete_custom_section(self, section_id: str):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM overview_custom_sections WHERE id = ?;", (section_id,))