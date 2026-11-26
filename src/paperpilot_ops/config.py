"""Laedt die Regeldatei (TOML)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class Category:
    label: str
    keywords: tuple[str, ...]
    senders: tuple[str, ...] = ()
    group: str = ""
    folder: str = ""
    action: str = "file"  # 'file' | 'ignore'


@dataclass(frozen=True)
class Group:
    name: str
    keywords: tuple[str, ...]
    folder: str


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


def default_rules_text() -> str:
    return resources.files("paperpilot_ops").joinpath("default_rules.toml").read_text("utf-8")


def load_rules(path: str | Path | None = None) -> Rules:
    raw = tomllib.loads(Path(path).read_text("utf-8") if path else default_rules_text())
    g = raw.get("general", {})
    groups = {
        name: Group(name, tuple(k.lower() for k in spec.get("keywords", [])), spec.get("folder", ""))
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
    )
