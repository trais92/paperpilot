"""Lädt die Konfigurationsdatei (TOML): Kategorien, Ordner, Vorfilter-Regeln und KI-Einstellungen."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Category:
    label: str
    keywords: tuple[str, ...]
    senders: tuple[str, ...] = ()
    group: str = ""
    folder: str = ""
    action: str = "file"  # 'file' | 'ignore'
    description: str = ""  # Beschreibung in einem Satz, damit die KI die Kategorie versteht
    enabled: bool = True  # False: wird erkannt, aber nicht abgelegt ("nicht gewählt")


@dataclass(frozen=True)
class Group:
    name: str
    keywords: tuple[str, ...]
    folder: str
    enabled: bool = True  # False schaltet alle Kategorien der Gruppe ab


# Bekannte KI-Anbieter. Die Technik dahinter steht in ai/providers.py.
AI_PROVIDERS = ("groq", "claude")


@dataclass(frozen=True)
class AISettings:
    """Abschnitt `[ai]`: welcher Anbieter zuerst gefragt wird und welche als Reserve dienen."""

    provider: str = "groq"
    fallback: tuple[str, ...] = ()
    min_confidence: float = 0.6  # darunter wird `unklar` vergeben
    models: dict[str, str] = field(default_factory=dict)  # optional: anderes Modell je Anbieter
    read_pdfs: bool = True  # Text aus PDF-Anhängen mitsenden (für Betrag, Nummer, Frist)

    @property
    def chain(self) -> tuple[str, ...]:
        """Anbieter in der Reihenfolge, in der sie gefragt werden, ohne Doppelte."""
        return tuple(dict.fromkeys((self.provider, *self.fallback)))


def _load_ai(raw: dict[str, Any]) -> AISettings:
    default = AISettings()
    settings = AISettings(
        provider=raw.get("provider", default.provider),
        fallback=tuple(raw.get("fallback", default.fallback)),
        min_confidence=float(raw.get("min_confidence", default.min_confidence)),
        models=dict(raw.get("models", {})),
        read_pdfs=bool(raw.get("read_pdfs", default.read_pdfs)),
    )
    unknown = [p for p in (*settings.chain, *settings.models) if p not in AI_PROVIDERS]
    if unknown:
        raise ValueError(f"Unbekannter KI-Anbieter {unknown[0]!r}, erlaubt: {', '.join(AI_PROVIDERS)}")
    if not 0.0 <= settings.min_confidence <= 1.0:
        raise ValueError("ai.min_confidence muss zwischen 0 und 1 liegen")
    return settings


STORAGE_TARGETS = ("local", "drive")


@dataclass(frozen=True)
class StorageSettings:
    """Abschnitt `[storage]`: wohin abgelegt wird."""

    target: str = "local"  # "local" (Ordner `target_dir`) oder "drive" (Google Drive)
    drive_folder: str = "PaperPilot"  # Wurzelordner in „Meine Ablage“


def _load_storage(raw: dict[str, Any]) -> StorageSettings:
    settings = StorageSettings(target=raw.get("target", "local"), drive_folder=raw.get("drive_folder", "PaperPilot"))
    if settings.target not in STORAGE_TARGETS:
        raise ValueError(f"Unbekanntes Ablageziel {settings.target!r}, erlaubt: {', '.join(STORAGE_TARGETS)}")
    if not settings.drive_folder.strip() or "/" in settings.drive_folder:
        raise ValueError("storage.drive_folder muss ein einzelner Ordnername sein")
    return settings


@dataclass(frozen=True)
class Rules:
    target_dir: str
    min_score: float
    notify_on: frozenset[str]
    review_folder: str
    tracker: str
    generic_domains: frozenset[str]
    categories: tuple[Category, ...]
    groups: dict[str, Group] = field(default_factory=dict)
    ai: AISettings = field(default_factory=AISettings)
    storage: StorageSettings = field(default_factory=StorageSettings)

    @property
    def labels(self) -> list[str]:
        return [c.label for c in self.categories] + ["unklar"]

    def category(self, label: str) -> Category | None:
        return next((c for c in self.categories if c.label == label), None)

    def folder_for(self, label: str) -> str:
        cat = self.category(label)
        if cat is None:
            group = self.groups.get(label.split("/", 1)[0])
            return group.folder if group and group.folder else self.review_folder
        if cat.folder:
            return cat.folder
        if cat.group and cat.group in self.groups:
            return self.groups[cat.group].folder
        return self.review_folder

    def is_selected(self, label: str) -> bool:
        """Soll diese Kategorie abgelegt werden? `unklar` und unbekannte Labels immer (in den Eingang)."""
        group = self.groups.get(label.split("/", 1)[0]) if "/" in label else None
        if group is not None and not group.enabled:
            return False
        cat = self.category(label)
        return cat.enabled if cat is not None else True

    def table_for(self, folder: str) -> str:
        """Übersichtstabelle eines Zielordners: im festen Teil des Ordners vor dem ersten Platzhalter.

        `06 Rechnungen & Belege/{year}` -> `06 Rechnungen & Belege/Übersicht`,
        `Bewerbungen/{company}` -> `Bewerbungen/Übersicht`, `00 Eingang` -> `00 Eingang/Übersicht`.
        """
        fixed = [part for part in folder.split("/") if part][: _fixed_depth(folder)]
        return "/".join([*fixed, OVERVIEW_NAME])


OVERVIEW_NAME = "Übersicht"


def _fixed_depth(folder: str) -> int:
    parts = [part for part in folder.split("/") if part]
    for i, part in enumerate(parts):
        if "{" in part:
            return i
    return len(parts)


def default_rules_text() -> str:
    return resources.files("paperpilot_ops").joinpath("default_rules.toml").read_text("utf-8")


def load_rules(path: str | Path | None = None) -> Rules:
    raw = tomllib.loads(Path(path).read_text("utf-8") if path else default_rules_text())
    g = raw.get("general", {})
    groups = {
        name: Group(
            name,
            tuple(k.lower() for k in spec.get("keywords", [])),
            spec.get("folder", ""),
            bool(spec.get("enabled", True)),
        )
        for name, spec in raw.get("groups", {}).items()
    }
    cats = tuple(
        Category(
            label=c["label"],
            keywords=tuple(k.lower() for k in c.get("keywords", [])),
            senders=tuple(s.lower() for s in c.get("senders", [])),
            group=c.get("group", ""),
            folder=c.get("folder", ""),
            action=c.get("action", "file"),
            description=c.get("description", ""),
            enabled=bool(c.get("enabled", True)),
        )
        for c in raw.get("categories", [])
    )
    for c in cats:
        if c.group and c.group not in groups:
            raise ValueError(f"Kategorie {c.label!r} verweist auf unbekannte Gruppe {c.group!r}")
    return Rules(
        target_dir=g.get("target_dir", "ablage"),
        min_score=float(g.get("min_score", 2.0)),
        notify_on=frozenset(g.get("notify_on", [])),
        review_folder=g.get("review_folder", "00 Eingang"),
        tracker=g.get("tracker", "Bewerbungen/tracker.csv"),
        generic_domains=frozenset(d.lower() for d in g.get("generic_domains", [])),
        categories=cats,
        groups=groups,
        ai=_load_ai(raw.get("ai", {})),
        storage=_load_storage(raw.get("storage", {})),
    )
