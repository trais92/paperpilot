"""Regel-Klassifizierer: Stichwörter und Absender, erklärbar, offline.

Seit ADR 0003 sortiert die KI (`ai/classifier.py`). Die Regeln dienen als Vorfilter für Werbung,
als Vergleichswert in `paperpilot eval` und für die Demo ohne Schlüssel.
"""

from __future__ import annotations

from collections.abc import Mapping

from .config import Rules
from .models import Classification, Mail
from .ports import Classifier

__all__ = ["UNCLEAR", "Classifier", "FixedClassifier", "RuleClassifier"]

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


class FixedClassifier:
    """Gibt vorher ermittelte Klassifizierungen zurück, z. B. nach Korrektur im Browser-Bericht.

    So wird beim Ausführen nicht erneut eine KI gefragt, und Korrekturen des Menschen gelten genau.
    Unbekannte Mails ergeben `unklar` (Regel 5).
    """

    def __init__(self, results: Mapping[str, Classification]):
        self._results = dict(results)

    def classify(self, mail: Mail) -> Classification:
        return self._results.get(mail.id, Classification(UNCLEAR, 0.0, "nicht im freigegebenen Plan"))
