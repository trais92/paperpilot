"""Klassifizierer: regelbasiert (Standard, offline) und optional per LLM."""

from __future__ import annotations

import json
import os
from typing import Any

from .config import Rules
from .models import Classification, Mail
from .ports import Classifier

__all__ = ["UNCLEAR", "Classifier", "LLMClassifier", "RuleClassifier", "make_classifier"]

UNCLEAR = "unklar"


def _hits(keywords: tuple[str, ...], mail: Mail) -> float:
    """Treffer zaehlen: Betreff zaehlt doppelt, Text einfach."""
    subject, body = mail.subject.lower(), mail.body.lower()
    score = 0.0
    for kw in keywords:
        if kw in subject:
            score += 2
        elif kw in body:
            score += 1
    return score


class RuleClassifier:
    """Transparenter Stichwort-Klassifizierer. Jede Entscheidung ist erklaerbar."""

    def __init__(self, rules: Rules):
        self.rules = rules

    def scores(self, mail: Mail) -> dict[str, float]:
        group_scores = {name: _hits(g.keywords, mail) for name, g in self.rules.groups.items()}
        out: dict[str, float] = {}
        best_sub: dict[str, float] = {}
        for cat in self.rules.categories:
            s = _hits(cat.keywords, mail)
            s += 3 * sum(1 for snd in cat.senders if snd in mail.sender_address)
            if cat.group:
                # Untertyp zaehlt nur, wenn Gruppe UND eigene Stichwoerter treffen
                gs = group_scores.get(cat.group, 0)
                best_sub[cat.group] = max(best_sub.get(cat.group, 0), s)
                s = gs + s if gs > 0 and s > 0 else 0.0
            out[cat.label] = s
        # Gruppe erkannt, aber kein Untertyp: '<gruppe>/sonstiges'
        for name, gs in group_scores.items():
            if gs > 0 and best_sub.get(name, 0) == 0:
                out[f"{name}/sonstiges"] = gs
        return out

    def classify(self, mail: Mail) -> Classification:
        scores = self.scores(mail)
        if not scores:
            return Classification(UNCLEAR, 0.0, "keine Kategorien konfiguriert")
        ranked = sorted(
            scores.items(),
            key=lambda kv: (kv[1], kv[0] in self.rules.notify_on),
            reverse=True,
        )
        (best, best_s), second_s = ranked[0], (ranked[1][1] if len(ranked) > 1 else 0.0)
        if best_s < self.rules.min_score:
            return Classification(UNCLEAR, 0.0, f"bester Score {best_s:g} < {self.rules.min_score:g}")
        conf = round(best_s / (best_s + second_s), 2) if best_s + second_s else 0.0
        return Classification(best, conf, f"Score {best_s:g}, naechster {second_s:g}")


class LLMClassifier:
    """Optionaler Klassifizierer ueber die Claude API (strukturierte JSON-Ausgabe).

    Braucht `pip install paperpilot-ops[llm]` und Zugangsdaten
    (z. B. ANTHROPIC_API_KEY). Bei Fehlern oder Ablehnung: 'unklar' -> menschliche Pruefung.
    """

    MODEL = os.environ.get("PAPERPILOT_MODEL", "claude-opus-5-5")

    def __init__(self, rules: Rules, client: Any = None):
        self.rules = rules
        if client is None:
            import anthropic  # optional dependency

            client = anthropic.Anthropic()
        self.client = client
        labels = sorted(set(rules.labels) | {f"{g}/sonstiges" for g in rules.groups})
        self.labels = labels
        self.schema = {
            "type": "object",
            "properties": {
                "label": {"type": "string", "enum": labels},
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["label", "confidence", "reason"],
            "additionalProperties": False,
        }

    def _prompt(self, mail: Mail) -> str:
        return (
            "Ordne diese E-Mail genau einem Label zu. "
            "'werbung' sind Newsletter, Rabattaktionen und automatische Job-Empfehlungen. "
            "'bewerbung/*' nur fuer Korrespondenz zu einer echten, selbst eingereichten Bewerbung. "
            "Wenn du unsicher bist, waehle 'unklar', dann prueft ein Mensch.\n\n"
            f"Labels: {', '.join(self.labels)}\n\n"
            f"Von: {mail.sender}\nBetreff: {mail.subject}\n\n{mail.body[:4000]}"
        )

    def classify(self, mail: Mail) -> Classification:
        try:
            response = self.client.beta.messages.create(
                model=self.MODEL,
                max_tokens=1024,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": self.schema},
                },
                messages=[{"role": "user", "content": self._prompt(mail)}],
            )
        except Exception as exc:  # Netzwerk, Auth, Rate-Limit: lieber Mensch fragen
            return Classification(UNCLEAR, 0.0, f"LLM-Fehler: {type(exc).__name__}")
        if response.stop_reason == "refusal":
            return Classification(UNCLEAR, 0.0, "LLM hat abgelehnt")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return Classification(UNCLEAR, 0.0, "LLM-Antwort kein JSON")
        return Classification(data["label"], float(data["confidence"]), data.get("reason", ""))


def make_classifier(name: str, rules: Rules) -> Classifier:
    if name == "rules":
        return RuleClassifier(rules)
    if name == "llm":
        return LLMClassifier(rules)
    raise ValueError(f"Unbekannter Klassifizierer: {name}")
