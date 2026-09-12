import os
import re
import json
import zipfile
import shutil
import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional

def get_cache_root() -> str:
    cache_dir = os.path.expanduser("~/.cache/lexicography_platform/sessions")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

class ProjectArchiveManager:

    @staticmethod
    def get_session_dir_for_archive(langarc_path: str) -> str:
        norm_path = os.path.abspath(langarc_path)
        base_name = os.path.splitext(os.path.basename(norm_path))[0]
        slug = re.sub(r'[^a-zA-Z0-9_\-]', '_', base_name.lower())
        path_hash = hashlib.sha256(norm_path.encode("utf-8")).hexdigest()[:8]
        session_dir = os.path.join(get_cache_root(), f"{slug}_{path_hash}")
        os.makedirs(session_dir, exist_ok=True)
        os.makedirs(os.path.join(session_dir, "database"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "audio", "glyphs"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "audio", "lexicon"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "images", "svg"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "images", "raster"), exist_ok=True)
        return session_dir

    @classmethod
    def create_new_archive(
        cls,
        langarc_path: str,
        project_name: str,
        language_type: str = "conlang_artlang"
    ) -> Tuple[str, str]:
        langarc_path = os.path.abspath(langarc_path)
        if not (langarc_path.endswith(".langarc") or langarc_path.endswith(".zip")):
            langarc_path = f"{langarc_path}.langarc"

        session_dir = cls.get_session_dir_for_archive(langarc_path)
        
        # Clean out any old session debris if starting a fresh project with same name
        for item in os.listdir(session_dir):
            item_path = os.path.join(session_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)

        os.makedirs(os.path.join(session_dir, "database"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "audio", "glyphs"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "audio", "lexicon"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "images", "svg"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "images", "raster"), exist_ok=True)

        db_path = os.path.join(session_dir, "database", "project.db")

        manifest = {
            "format": "lexicography_archive",
            "format_version": "1.0",
            "project_name": project_name.strip(),
            "language_type": language_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_saved": datetime.now(timezone.utc).isoformat(),
            "db_path": "database/project.db"
        }
        with open(os.path.join(session_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return session_dir, db_path

    @classmethod
    def open_archive(cls, langarc_path: str) -> Tuple[str, str, str]:
        langarc_path = os.path.abspath(langarc_path)
        if not os.path.exists(langarc_path):
            raise FileNotFoundError(f"Archive file does not exist: {langarc_path}")

        if langarc_path.endswith(".db"):
            base_name = os.path.splitext(os.path.basename(langarc_path))[0].replace("_", " ").title()
            session_dir = os.path.dirname(langarc_path)
            return session_dir, langarc_path, base_name

        if not zipfile.is_zipfile(langarc_path):
            raise ValueError(f"File is not a valid zip or .langarc archive: {langarc_path}")

        session_dir = cls.get_session_dir_for_archive(langarc_path)

        with zipfile.ZipFile(langarc_path, "r") as zf:
            for member in zf.infolist():
                target_path = os.path.abspath(os.path.join(session_dir, member.filename))
                if not target_path.startswith(os.path.abspath(session_dir)):
                    raise PermissionError(f"Security error: path traversal in archive member: {member.filename}")
                zf.extract(member, session_dir)

        manifest_path = os.path.join(session_dir, "manifest.json")
        project_name = os.path.splitext(os.path.basename(langarc_path))[0].replace("_", " ").title()
        db_relative = "database/project.db"

        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    project_name = meta.get("project_name", project_name)
                    db_relative = meta.get("db_path", db_relative)
            except Exception as e:
                print(f"[ProjectArchiveManager] Manifest read warning: {e}")

        db_path = os.path.join(session_dir, db_relative)
        if not os.path.exists(db_path):
            found = False
            for root, _, files in os.walk(session_dir):
                for file in files:
                    if file.endswith(".db"):
                        db_path = os.path.join(root, file)
                        found = True
                        break
                if found:
                    break
            if not found:
                raise FileNotFoundError(f"No SQLite database found inside archive: {langarc_path}")

        return session_dir, db_path, project_name

    @classmethod
    def save_archive(cls, session_dir: str, langarc_path: str, project_name: str = "") -> str:
        langarc_path = os.path.abspath(langarc_path)
        os.makedirs(os.path.dirname(langarc_path), exist_ok=True)

        db_dir = os.path.join(session_dir, "database")
        if os.path.exists(db_dir):
            for f in os.listdir(db_dir):
                if f.endswith(".db"):
                    db_file = os.path.join(db_dir, f)
                    try:
                        conn = sqlite3.connect(db_file)
                        conn.execute("PRAGMA wal_checkpoint(FULL);")
                        conn.commit()
                        conn.close()
                    except Exception as e:
                        print(f"[ProjectArchiveManager] SQLite checkpoint note: {e}")

        manifest_path = os.path.join(session_dir, "manifest.json")
        manifest = {}
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                pass

        if project_name:
            manifest["project_name"] = project_name
        manifest["last_saved"] = datetime.now(timezone.utc).isoformat()
        manifest["format"] = "lexicography_archive"
        manifest["format_version"] = "1.0"

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        tmp_archive = f"{langarc_path}.tmp"
        with zipfile.ZipFile(tmp_archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(session_dir):
                for file in files:
                    full_file_path = os.path.join(root, file)
                    rel_arc_path = os.path.relpath(full_file_path, session_dir)
                    if file.endswith("-journal") or file.endswith("-wal") or file.endswith("-shm"):
                        continue
                    zf.write(full_file_path, arcname=rel_arc_path)

        if os.path.exists(langarc_path):
            os.remove(langarc_path)
        os.rename(tmp_archive, langarc_path)

        return langarc_path
