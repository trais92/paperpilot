"""`DriveStore`: Google Drive als Ablageziel (Port `StorageTarget`).

Alles liegt unter einem Wurzelordner (Standard „PaperPilot“) in „Meine Ablage“. Die Ordnerstruktur
ist dieselbe wie lokal. Unterschiede, die der Port erlaubt:

- Übersichtstabellen sind Google-Tabellen (beim Hochladen aus CSV umgewandelt).
- Duplikat-Index und Lauf-Stand liegen als JSON in `.paperpilot/` innerhalb des Wurzelordners.

Ordner-IDs werden pro Lauf zwischengespeichert, damit nicht jeder Pfad neu gesucht wird.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import PurePosixPath

from ..store import META_DIR, merge_table, newest_date, numbered_path, sha256
from .api import SHEET_MIME, DriveApi

ROOT_PARENT = "root"  # „Meine Ablage“


class DriveStore:
    """Ablage in Google Drive. Erfüllt denselben Vertrag wie `LocalStore` (tests/test_storage_contract.py)."""

    def __init__(self, api: DriveApi, root_name: str = "PaperPilot"):
        self._api = api
        self._root_name = root_name
        self._folders: dict[str, str] = {}
        self._index: dict[str, str] | None = None

    @property
    def location(self) -> str:
        return f"Google Drive: Meine Ablage/{self._root_name}"

    # -- Ordner -----------------------------------------------------------------------------
    def _folder_id(self, rel_dir: str, create: bool) -> str | None:
        """ID des Ordners `rel_dir` (relativ zur Wurzel, '' = Wurzel). Legt fehlende Ordner nur mit `create` an."""
        if rel_dir in self._folders:
            return self._folders[rel_dir]
        if rel_dir == "":
            found = self._api.find(ROOT_PARENT, self._root_name)
            parent_id = ROOT_PARENT
            name = self._root_name
        else:
            path = PurePosixPath(rel_dir)
            parent = self._folder_id("" if str(path.parent) == "." else str(path.parent), create)
            if parent is None:
                return None
            parent_id, name = parent, path.name
            found = self._api.find(parent_id, name)
        if found is not None:
            folder_id = found.id
        elif create:
            folder_id = self._api.create_folder(parent_id, name)
        else:
            return None
        self._folders[rel_dir] = folder_id
        return folder_id

    def _split(self, rel_path: str) -> tuple[str, str]:
        path = PurePosixPath(rel_path)
        return ("" if str(path.parent) == "." else str(path.parent)), path.name

    def _find_file(self, rel_path: str) -> str | None:
        rel_dir, name = self._split(rel_path)
        folder = self._folder_id(rel_dir, create=False)
        if folder is None:
            return None
        found = self._api.find(folder, name)
        return found.id if found else None

    # -- Dokumente --------------------------------------------------------------------------
    @property
    def index(self) -> dict[str, str]:
        if self._index is None:
            raw = self.read_text(f"{META_DIR}/index.json")
            self._index = json.loads(raw) if raw else {}
        return self._index

    def has(self, digest: str) -> bool:
        return digest in self.index

    def write_file(self, rel_path: str, content: bytes) -> str:
        candidate, n = rel_path, 2
        while self._find_file(candidate) is not None:  # nie überschreiben
            candidate, n = numbered_path(rel_path, n), n + 1
        rel_dir, name = self._split(candidate)
        folder = self._folder_id(rel_dir, create=True)
        assert folder is not None
        self._api.upload(folder, name, content, "application/octet-stream")
        self.index[sha256(content)] = candidate
        return candidate

    # -- eigene Textdateien (Tracker, Fristen, Metadaten) -------------------------------------
    def read_text(self, rel_path: str) -> str | None:
        file_id = self._find_file(rel_path)
        return None if file_id is None else self._api.download(file_id).decode("utf-8")

    def write_text(self, rel_path: str, text: str) -> None:
        data = text.encode("utf-8")
        file_id = self._find_file(rel_path)
        if file_id is not None:
            self._api.update_content(file_id, data, "text/plain")
            return
        rel_dir, name = self._split(rel_path)
        folder = self._folder_id(rel_dir, create=True)
        assert folder is not None
        self._api.upload(folder, name, data, "text/plain")

    # -- Übersichtstabellen als Google-Tabelle ----------------------------------------------
    def read_rows(self, table: str) -> list[dict[str, str]]:
        return self._read_table(table)[1]

    def append_rows(self, table: str, columns: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
        file_id, old_columns, old_rows = self._load_table(table)
        merged_columns, merged_rows = merge_table(old_columns, old_rows, columns, rows)
        buf = io.StringIO(newline="")
        writer = csv.DictWriter(buf, fieldnames=merged_columns)
        writer.writeheader()
        writer.writerows(merged_rows)
        data = buf.getvalue().encode("utf-8")
        if file_id is not None:
            self._api.update_content(file_id, data, "text/csv")
            return
        rel_dir, name = self._split(table)
        folder = self._folder_id(rel_dir, create=True)
        assert folder is not None
        self._api.upload(folder, name, data, "text/csv", as_mime=SHEET_MIME)

    def _read_table(self, table: str) -> tuple[list[str], list[dict[str, str]]]:
        _, columns, rows = self._load_table(table)
        return columns, rows

    def _load_table(self, table: str) -> tuple[str | None, list[str], list[dict[str, str]]]:
        file_id = self._find_file(table)
        if file_id is None:
            return None, [], []
        text = self._api.export(file_id, "text/csv").decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        rows = [{k: v or "" for k, v in row.items() if k is not None} for row in reader]
        return file_id, list(reader.fieldnames or []), rows

    # -- Lauf-Stand ---------------------------------------------------------------------------
    def last_run(self) -> datetime | None:
        raw = self.read_text(f"{META_DIR}/state.json")
        value = json.loads(raw).get("last_mail_date") if raw else None
        return datetime.fromisoformat(value) if value else None

    def save(self, last_mail_date: datetime | None) -> None:
        self.write_text(f"{META_DIR}/index.json", json.dumps(self.index, indent=1, ensure_ascii=False))
        newest = newest_date(self.last_run(), last_mail_date)
        state = {
            "last_run": datetime.now().isoformat(timespec="seconds"),
            "last_mail_date": newest.isoformat() if newest else None,
        }
        self.write_text(f"{META_DIR}/state.json", json.dumps(state, indent=1))
