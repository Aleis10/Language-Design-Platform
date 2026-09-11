import uuid
from typing import Optional, Dict, Any, List
try:
    from database.db_Manager import Database_Manager
except ImportError:
    from .db_Manager import Database_Manager


class GrammarRepository:
    def __init__(self, db_manager: Database_Manager):
        self.db_manager = db_manager
        self._ensure_tables()

    def _ensure_tables(self):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Grammar Categories (e.g., Noun Classes, Tense, Aspect)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS grammar_categories (
                    id TEXT PRIMARY KEY,
                    language_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    position INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)

            # 2. Affix / Grammar Rules
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS grammar_rules (
                    id TEXT PRIMARY KEY,
                    language_id TEXT NOT NULL,
                    category_id TEXT,
                    name TEXT NOT NULL,
                    affix_pattern TEXT,
                    affix_type TEXT DEFAULT 'suffix',
                    gloss_tag TEXT NOT NULL,
                    gloss_description TEXT,
                    position INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE,
                    FOREIGN KEY (category_id) REFERENCES grammar_categories (id) ON DELETE SET NULL
                );
            """)

            # 3. Paradigm Grids (e.g., verb conjugation tables)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paradigm_grids (
                    id TEXT PRIMARY KEY,
                    language_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    headers TEXT NOT NULL DEFAULT '[]',
                    rows TEXT NOT NULL DEFAULT '[]',
                    position INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)

            # 4. Phrase / Sentence Templates (interlinear sentence patterns)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS phrase_templates (
                    id TEXT PRIMARY KEY,
                    language_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    pattern TEXT NOT NULL,
                    gloss TEXT,
                    translation TEXT,
                    notes TEXT,
                    position INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)

            # Index for fast rule lookup by language
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_grammar_rules_lang
                ON grammar_rules(language_id, position);
            """)

            # Migration: add missing columns for existing projects
            cursor.execute("PRAGMA table_info(grammar_rules);")
            existing_cols = {row["name"] for row in cursor.fetchall()}
            migrations = {
                "category_id": "TEXT",
                "gloss_tag": "TEXT NOT NULL DEFAULT ''",
                "gloss_description": "TEXT",
                "affix_pattern": "TEXT",
                "affix_type": "TEXT DEFAULT 'suffix'",
                "position": "INTEGER DEFAULT 0",
                "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            }
            for col, col_def in migrations.items():
                if col not in existing_cols:
                    cursor.execute(f"ALTER TABLE grammar_rules ADD COLUMN {col} {col_def};")

    # ── CATEGORIES ──────────────────────────────────────────────

    def get_categories(self, language_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM grammar_categories WHERE language_id = ? ORDER BY position ASC, created_at ASC;",
                (language_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def add_category(self, language_id: str, name: str, description: str = "", position: int = 0) -> str:
        cat_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            conn.execute(
                "INSERT INTO grammar_categories (id, language_id, name, description, position) VALUES (?, ?, ?, ?, ?);",
                (cat_id, language_id, name.strip(), description.strip(), position),
            )
        return cat_id

    def update_category(self, category_id: str, name: Optional[str] = None, description: Optional[str] = None):
        fields, params = [], []
        if name is not None:
            fields.append("name = ?")
            params.append(name.strip())
        if description is not None:
            fields.append("description = ?")
            params.append(description.strip())
        if not fields:
            return
        params.append(category_id)
        with self.db_manager.get_connection() as conn:
            conn.execute(f"UPDATE grammar_categories SET {', '.join(fields)} WHERE id = ?;", params)

    def delete_category(self, category_id: str):
        with self.db_manager.get_connection() as conn:
            conn.execute("DELETE FROM grammar_categories WHERE id = ?;", (category_id,))

    # ── RULES ───────────────────────────────────────────────────

    def get_rules(self, language_id: str, category_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            if category_id:
                cursor.execute(
                    "SELECT * FROM grammar_rules WHERE language_id = ? AND category_id = ? "
                    "ORDER BY position ASC, created_at ASC;",
                    (language_id, category_id),
                )
            else:
                cursor.execute(
                    "SELECT * FROM grammar_rules WHERE language_id = ? ORDER BY position ASC, created_at ASC;",
                    (language_id,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM grammar_rules WHERE id = ?;", (rule_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_rule(
        self,
        language_id: str,
        name: str,
        gloss_tag: str,
        category_id: Optional[str] = None,
        affix_pattern: str = "",
        affix_type: str = "suffix",
        gloss_description: str = "",
        position: int = 0,
    ) -> str:
        rule_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO grammar_rules
                    (id, language_id, category_id, name, affix_pattern, affix_type,
                     gloss_tag, gloss_description, position)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    rule_id, language_id, category_id,
                    name.strip(), affix_pattern.strip(), affix_type,
                    gloss_tag.strip(), gloss_description.strip(), position,
                ),
            )
        return rule_id

    def update_rule(self, rule_id: str, **fields):
        allowed = {
            "name", "category_id", "affix_pattern", "affix_type",
            "gloss_tag", "gloss_description", "position",
        }
        updates, params = [], []
        for key, val in fields.items():
            if key in allowed and val is not None:
                updates.append(f"{key} = ?")
                params.append(val.strip() if isinstance(val, str) else val)
        if not updates:
            return
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(rule_id)
        with self.db_manager.get_connection() as conn:
            conn.execute(f"UPDATE grammar_rules SET {', '.join(updates)} WHERE id = ?;", params)

    def delete_rule(self, rule_id: str):
        with self.db_manager.get_connection() as conn:
            conn.execute("DELETE FROM grammar_rules WHERE id = ?;", (rule_id,))

    def get_rules_for_parser(self, language_id: str) -> List[Dict[str, Any]]:
        """Return rules ordered longest-affix-first for the morphological parser."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT affix_pattern, affix_type, gloss_tag
                   FROM grammar_rules
                   WHERE language_id = ? AND affix_pattern IS NOT NULL AND affix_pattern != ''
                   ORDER BY LENGTH(affix_pattern) DESC;""",
                (language_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    # ── PARADIGM GRIDS ──────────────────────────────────────────

    def get_paradigms(self, language_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM paradigm_grids WHERE language_id = ? ORDER BY position ASC, created_at ASC;",
                (language_id,),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            import json
            for row in rows:
                try:
                    row["headers"] = json.loads(row.get("headers", "[]"))
                except Exception:
                    row["headers"] = []
                try:
                    row["rows"] = json.loads(row.get("rows", "[]"))
                except Exception:
                    row["rows"] = []
            return rows

    def add_paradigm(
        self,
        language_id: str,
        name: str,
        description: str = "",
        headers: Optional[List[str]] = None,
        rows: Optional[List[List[str]]] = None,
        position: int = 0,
    ) -> str:
        import json
        grid_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO paradigm_grids (id, language_id, name, description, headers, rows, position)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    grid_id, language_id, name.strip(), description.strip(),
                    json.dumps(headers or []), json.dumps(rows or []), position,
                ),
            )
        return grid_id

    def update_paradigm(self, grid_id: str, **fields):
        import json
        allowed = {"name", "description", "headers", "rows", "position"}
        updates, params = [], []
        for key, val in fields.items():
            if key in allowed and val is not None:
                if key in ("headers", "rows"):
                    val = json.dumps(val)
                updates.append(f"{key} = ?")
                params.append(val)
        if not updates:
            return
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(grid_id)
        with self.db_manager.get_connection() as conn:
            conn.execute(f"UPDATE paradigm_grids SET {', '.join(updates)} WHERE id = ?;", params)

    def delete_paradigm(self, grid_id: str):
        with self.db_manager.get_connection() as conn:
            conn.execute("DELETE FROM paradigm_grids WHERE id = ?;", (grid_id,))

    # ── PHRASE TEMPLATES ────────────────────────────────────────

    def get_templates(self, language_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM phrase_templates WHERE language_id = ? ORDER BY position ASC, created_at ASC;",
                (language_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def add_template(
        self,
        language_id: str,
        name: str,
        pattern: str,
        gloss: str = "",
        translation: str = "",
        notes: str = "",
        position: int = 0,
    ) -> str:
        tpl_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO phrase_templates
                    (id, language_id, name, pattern, gloss, translation, notes, position)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (tpl_id, language_id, name.strip(), pattern.strip(),
                 gloss.strip(), translation.strip(), notes.strip(), position),
            )
        return tpl_id

    def update_template(self, template_id: str, **fields):
        allowed = {"name", "pattern", "gloss", "translation", "notes", "position"}
        updates, params = [], []
        for key, val in fields.items():
            if key in allowed and val is not None:
                updates.append(f"{key} = ?")
                params.append(val.strip() if isinstance(val, str) else val)
        if not updates:
            return
        params.append(template_id)
        with self.db_manager.get_connection() as conn:
            conn.execute(f"UPDATE phrase_templates SET {', '.join(updates)} WHERE id = ?;", params)

    def delete_template(self, template_id: str):
        with self.db_manager.get_connection() as conn:
            conn.execute("DELETE FROM phrase_templates WHERE id = ?;", (template_id,))
