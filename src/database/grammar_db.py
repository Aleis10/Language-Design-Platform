import json
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

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_grammar_rules_lang
                ON grammar_rules(language_id, position);
            """)

            # Features the language has (Number, Tense ...) and their values (Singular, Plural ...)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS grammar_features (
                    id TEXT PRIMARY KEY,
                    language_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    word_classes TEXT NOT NULL DEFAULT '[]',
                    position INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS grammar_feature_values (
                    id TEXT PRIMARY KEY,
                    feature_id TEXT NOT NULL,
                    language_id TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    trigger TEXT NOT NULL DEFAULT '',
                    position INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (feature_id) REFERENCES grammar_features (id) ON DELETE CASCADE,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)
            # Irregular forms: one word + some feature values = the exact form
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS grammar_irregulars (
                    id TEXT PRIMARY KEY,
                    language_id TEXT NOT NULL,
                    entry_id TEXT NOT NULL,
                    value_ids TEXT NOT NULL DEFAULT '[]',
                    form TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_grammar_irregulars_entry
                ON grammar_irregulars(language_id, entry_id);
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
                "value_id": "TEXT",                              # the feature value this rule expresses
                "word_class": "TEXT DEFAULT ''",                 # NOUN, VERB ... (empty = any)
                "condition_type": "TEXT DEFAULT ''",             # ends_with, starts_with, not_ends_with ...
                "condition_value": "TEXT DEFAULT ''",            # e.g. "a, e, i, o, u"
            }
            for col, col_def in migrations.items():
                if col not in existing_cols:
                    cursor.execute(f"ALTER TABLE grammar_rules ADD COLUMN {col} {col_def};")

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
        value_id: Optional[str] = None,
        word_class: str = "",
        condition_type: str = "",
        condition_value: str = "",
    ) -> str:
        rule_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO grammar_rules
                    (id, language_id, category_id, name, affix_pattern, affix_type,
                     gloss_tag, gloss_description, position,
                     value_id, word_class, condition_type, condition_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    rule_id, language_id, category_id,
                    name.strip(), affix_pattern.strip(), affix_type,
                    gloss_tag.strip(), gloss_description.strip(), position,
                    value_id or None, word_class.strip(), condition_type.strip(), condition_value.strip(),
                ),
            )
        return rule_id

    def update_rule(self, rule_id: str, **fields):
        allowed = {
            "name", "category_id", "affix_pattern", "affix_type",
            "gloss_tag", "gloss_description", "position",
            "value_id", "word_class", "condition_type", "condition_value",
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

    # ------------------------------------------------------------------ features and their values
    @staticmethod
    def _load_list(text: Any) -> List[Any]:
        try:
            data = json.loads(text or "[]")
            return data if isinstance(data, list) else []
        except (TypeError, ValueError):
            return []

    def get_features(self, language_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM grammar_features WHERE language_id = ? ORDER BY position ASC, created_at ASC;",
                (language_id,),
            )
            rows = [dict(r) for r in cursor.fetchall()]
        for row in rows:
            row["word_classes"] = self._load_list(row.get("word_classes"))
        return rows

    def add_feature(self, language_id: str, name: str, word_classes: Optional[List[str]] = None,
                    position: Optional[int] = None) -> str:
        feature_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            if position is None:
                row = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 AS nxt FROM grammar_features WHERE language_id = ?;",
                    (language_id,),
                ).fetchone()
                position = row["nxt"]
            conn.execute(
                "INSERT INTO grammar_features (id, language_id, name, word_classes, position) VALUES (?, ?, ?, ?, ?);",
                (feature_id, language_id, name.strip(), json.dumps([c.upper() for c in (word_classes or [])]), position),
            )
        return feature_id

    def update_feature(self, feature_id: str, name: Optional[str] = None,
                       word_classes: Optional[List[str]] = None, position: Optional[int] = None):
        updates, params = [], []
        if name is not None:
            updates.append("name = ?")
            params.append(name.strip())
        if word_classes is not None:
            updates.append("word_classes = ?")
            params.append(json.dumps([c.upper() for c in word_classes]))
        if position is not None:
            updates.append("position = ?")
            params.append(position)
        if not updates:
            return
        params.append(feature_id)
        with self.db_manager.get_connection() as conn:
            conn.execute(f"UPDATE grammar_features SET {', '.join(updates)} WHERE id = ?;", params)

    def delete_feature(self, feature_id: str):
        with self.db_manager.get_connection() as conn:
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM grammar_feature_values WHERE feature_id = ?;", (feature_id,)).fetchall()]
        for value_id in ids:
            self.delete_feature_value(value_id)
        with self.db_manager.get_connection() as conn:
            conn.execute("DELETE FROM grammar_features WHERE id = ?;", (feature_id,))

    def get_feature_values(self, language_id: str) -> List[Dict[str, Any]]:
        # every value of every feature, with the name and word classes of its feature
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT v.*, f.name AS feature_name, f.word_classes AS word_classes_json
                FROM grammar_feature_values v JOIN grammar_features f ON f.id = v.feature_id
                WHERE v.language_id = ?
                ORDER BY f.position ASC, f.created_at ASC, v.position ASC, v.created_at ASC;
                """,
                (language_id,),
            )
            rows = [dict(r) for r in cursor.fetchall()]
        for row in rows:
            row["word_classes"] = self._load_list(row.pop("word_classes_json", "[]"))
        return rows

    def add_feature_value(self, feature_id: str, tag: str, label: str = "", trigger: str = "",
                          position: Optional[int] = None) -> str:
        value_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            feature = conn.execute("SELECT language_id FROM grammar_features WHERE id = ?;", (feature_id,)).fetchone()
            if feature is None:
                raise ValueError("unknown feature")
            if position is None:
                row = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 AS nxt FROM grammar_feature_values WHERE feature_id = ?;",
                    (feature_id,),
                ).fetchone()
                position = row["nxt"]
            conn.execute(
                """
                INSERT INTO grammar_feature_values (id, feature_id, language_id, tag, label, trigger, position)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (value_id, feature_id, feature["language_id"], tag.strip(), label.strip(), (trigger or "").strip(), position),
            )
        return value_id

    def update_feature_value(self, value_id: str, tag: Optional[str] = None, label: Optional[str] = None,
                             trigger: Optional[str] = None, position: Optional[int] = None):
        updates, params = [], []
        for column, value in (("tag", tag), ("label", label), ("trigger", trigger)):
            if value is not None:
                updates.append(f"{column} = ?")
                params.append(value.strip())
        if position is not None:
            updates.append("position = ?")
            params.append(position)
        if not updates:
            return
        params.append(value_id)
        with self.db_manager.get_connection() as conn:
            conn.execute(f"UPDATE grammar_feature_values SET {', '.join(updates)} WHERE id = ?;", params)

    def delete_feature_value(self, value_id: str):
        # rules that used the value go back to being plain tagged rules; irregulars lose the value
        # (and are removed when nothing is left of them)
        with self.db_manager.get_connection() as conn:
            conn.execute("UPDATE grammar_rules SET value_id = NULL WHERE value_id = ?;", (value_id,))
            for row in conn.execute("SELECT id, value_ids FROM grammar_irregulars;").fetchall():
                ids = [i for i in self._load_list(row["value_ids"]) if i != value_id]
                if ids == self._load_list(row["value_ids"]):
                    continue
                if ids:
                    conn.execute("UPDATE grammar_irregulars SET value_ids = ? WHERE id = ?;", (json.dumps(ids), row["id"]))
                else:
                    conn.execute("DELETE FROM grammar_irregulars WHERE id = ?;", (row["id"],))
            conn.execute("DELETE FROM grammar_feature_values WHERE id = ?;", (value_id,))

    def ensure_default_features(self, language_id: str) -> bool:
        # give a language the starter set the first time; returns True when something was added
        from translation.features import DEFAULT_FEATURES
        if self.get_features(language_id):
            return False
        for position, feature in enumerate(DEFAULT_FEATURES):
            feature_id = self.add_feature(language_id, feature["name"], feature["word_classes"], position)
            for vpos, value in enumerate(feature["values"]):
                self.add_feature_value(feature_id, value["tag"], value["label"], value["trigger"], vpos)
        return True

    # ------------------------------------------------------------------ irregular forms
    def get_irregulars(self, language_id: str, entry_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            if entry_id:
                cursor.execute(
                    "SELECT * FROM grammar_irregulars WHERE language_id = ? AND entry_id = ? ORDER BY created_at ASC;",
                    (language_id, entry_id),
                )
            else:
                cursor.execute(
                    "SELECT * FROM grammar_irregulars WHERE language_id = ? ORDER BY created_at ASC;", (language_id,))
            rows = [dict(r) for r in cursor.fetchall()]
        for row in rows:
            row["value_ids"] = self._load_list(row.get("value_ids"))
        return rows

    def add_irregular(self, language_id: str, entry_id: str, value_ids: List[str], form: str) -> str:
        irregular_id = str(uuid.uuid4())
        with self.db_manager.get_connection() as conn:
            conn.execute(
                "INSERT INTO grammar_irregulars (id, language_id, entry_id, value_ids, form) VALUES (?, ?, ?, ?, ?);",
                (irregular_id, language_id, str(entry_id), json.dumps(sorted(str(v) for v in value_ids)), form.strip()),
            )
        return irregular_id

    def update_irregular(self, irregular_id: str, value_ids: Optional[List[str]] = None, form: Optional[str] = None):
        updates, params = [], []
        if value_ids is not None:
            updates.append("value_ids = ?")
            params.append(json.dumps(sorted(str(v) for v in value_ids)))
        if form is not None:
            updates.append("form = ?")
            params.append(form.strip())
        if not updates:
            return
        params.append(irregular_id)
        with self.db_manager.get_connection() as conn:
            conn.execute(f"UPDATE grammar_irregulars SET {', '.join(updates)} WHERE id = ?;", params)

    def delete_irregular(self, irregular_id: str):
        with self.db_manager.get_connection() as conn:
            conn.execute("DELETE FROM grammar_irregulars WHERE id = ?;", (irregular_id,))
