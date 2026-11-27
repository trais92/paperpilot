"""Persönliche Einstellungen aus dem Einrichtungsassistenten (docs/adr/0010-persoenliche-einstellungen.md).

Die Regeldatei (`default_rules.toml` oder `--rules`) beschreibt Kategorien, Ordner und Vorfilter.
Der Assistent ändert sie nicht, sondern schreibt nur die wenigen Werte, die ein Mensch dort wählt,
in eine eigene kleine Datei `settings.toml` im Konfigurationsordner des Benutzers:

- Ablageziel (`local` mit Ordner oder `drive` mit Ordnername),
- welche Kategorien abgelegt werden.

`apply_settings()` legt diese Werte über die geladenen Regeln. Zugangsdaten stehen nie hier,
sondern im Schlüsselbund (Regel 6).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .config import STORAGE_TARGETS, Rules, StorageSettings

__all__ = [
    "CONFIG_DIR_ENV",
    "SETTINGS_FILE",
    "UserSettings",
    "apply_settings",
    "config_dir",
    "load_settings",
    "save_settings",
    "settings_path",
]

CONFIG_DIR_ENV = "PAPERPILOT_CONFIG_DIR"  # übersteuert den Ordner (Tests, portable Installation)
SETTINGS_FILE = "settings.toml"


@dataclass(frozen=True)
class UserSettings:
    """Vom Menschen gewählte Werte. `None` heißt: Wert aus der Regeldatei gilt."""

    storage_target: str | None = None
    target_dir: str | None = None
    drive_folder: str | None = None
    categories: Mapping[str, bool] = field(default_factory=dict)  # Label -> ablegen ja/nein

    def __post_init__(self) -> None:
        if self.storage_target is not None and self.storage_target not in STORAGE_TARGETS:
            raise ValueError(f"Unbekanntes Ablageziel {self.storage_target!r}, erlaubt: {', '.join(STORAGE_TARGETS)}")
        if self.drive_folder is not None and (not self.drive_folder.strip() or "/" in self.drive_folder):
            raise ValueError("Der Drive-Ordner muss ein einzelner Ordnername sein.")
        if self.target_dir is not None and not self.target_dir.strip():
            raise ValueError("Der Ablage-Ordner darf nicht leer sein.")


def config_dir(environ: Mapping[str, str] | None = None, platform: str | None = None, home: Path | None = None) -> Path:
    """Konfigurationsordner nach den Gepflogenheiten des Betriebssystems."""
    env = os.environ if environ is None else environ
    if env.get(CONFIG_DIR_ENV):
        return Path(env[CONFIG_DIR_ENV])
    platform = platform or sys.platform
    home = home or Path.home()
    if platform.startswith("win"):
        return Path(env.get("APPDATA") or home / "AppData" / "Roaming") / "PaperPilot"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "PaperPilot"
    return Path(env.get("XDG_CONFIG_HOME") or home / ".config") / "paperpilot"


def settings_path(environ: Mapping[str, str] | None = None) -> Path:
    return config_dir(environ) / SETTINGS_FILE


def load_settings(path: Path) -> UserSettings:
    """Liest `settings.toml`. Fehlt die Datei, gelten nur die Regeln."""
    if not path.exists():
        return UserSettings()
    raw = tomllib.loads(path.read_text("utf-8"))
    storage: dict[str, Any] = raw.get("storage", {})
    categories = raw.get("categories", {})
    if not all(isinstance(v, bool) for v in categories.values()):
        raise ValueError(f"{path}: [categories] erwartet true oder false je Kategorie.")
    return UserSettings(
        storage_target=storage.get("target"),
        target_dir=storage.get("target_dir"),
        drive_folder=storage.get("drive_folder"),
        categories=dict(categories),
    )


def _toml_string(value: str) -> str:
    # JSON-Strings sind gültige TOML-Basis-Strings (gleiche Maskierung von " \ und Steuerzeichen)
    return json.dumps(value, ensure_ascii=False)


def render_settings(settings: UserSettings) -> str:
    lines = ["# Vom Einrichtungsassistenten geschrieben (paperpilot setup). Zugangsdaten stehen im Schlüsselbund.", ""]
    storage = {"target": settings.storage_target, "target_dir": settings.target_dir}
    storage["drive_folder"] = settings.drive_folder
    lines.append("[storage]")
    lines += [f"{key} = {_toml_string(value)}" for key, value in storage.items() if value is not None]
    lines += ["", "[categories]  # true = ablegen, false = nur im Postfach lassen"]
    for label, on in sorted(settings.categories.items()):
        lines.append(f"{_toml_string(label)} = {'true' if on else 'false'}")
    return "\n".join(lines) + "\n"


def save_settings(settings: UserSettings, path: Path) -> None:
    """Schreibt atomar (temporäre Datei, dann ersetzen), damit nie eine halbe Datei entsteht."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".toml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(render_settings(settings))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def apply_settings(rules: Rules, settings: UserSettings) -> Rules:
    """Regeln mit den persönlichen Einstellungen. Unbekannte Kategorien sind ein Fehler."""
    known = {c.label for c in rules.categories}
    unknown = sorted(set(settings.categories) - known)
    if unknown:
        raise ValueError(f"Unbekannte Kategorie in den Einstellungen: {unknown[0]}")
    categories = tuple(
        replace(c, enabled=settings.categories[c.label]) if c.label in settings.categories else c
        for c in rules.categories
    )
    storage = StorageSettings(
        target=settings.storage_target or rules.storage.target,
        drive_folder=settings.drive_folder or rules.storage.drive_folder,
    )
    return replace(rules, categories=categories, storage=storage, target_dir=settings.target_dir or rules.target_dir)
