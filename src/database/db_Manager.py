import sqlite3
import os
from contextlib import contextmanager


class Database_Manager:
    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)
        
        # 1. Ensure target directory exists on disk
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        # 2. Initialize database schemas & write initial structure
        self._init_db()

    @contextmanager
    def get_connection(self):
        """Provides a transactional database connection context."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_db(self):
        """Creates table schemas and forces physical file creation."""
        with self.get_connection() as conn:
            # 1. Master Languages Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS languages (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    language_type TEXT DEFAULT 'conlang_artlang',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. Language Overview Core Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS language_overview (
                    language_id TEXT PRIMARY KEY,
                    autonym TEXT,
                    exonym TEXT,
                    language_code TEXT,
                    is_spoken INTEGER DEFAULT 1,
                    is_extinct INTEGER DEFAULT 0,
                    is_constructed INTEGER DEFAULT 1,
                    constructed_type TEXT,
                    genetic_classification TEXT,
                    glottocode TEXT,
                    iso_639_3 TEXT,
                    notes TEXT,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)

            # 3. Dynamic Custom Sections Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS overview_custom_sections (
                    id TEXT PRIMARY KEY,
                    language_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT,
                    position INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (language_id) REFERENCES languages (id) ON DELETE CASCADE
                );
            """)

          
        print(f"Database is created at : {self.db_path}")