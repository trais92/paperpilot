"""Kompositionswurzel: der einzige Ort, an dem Ports mit konkreten Adaptern verbunden werden.

Die CLI (und später die Browser-Oberfläche) holt sich hier fertige Objekte. Der Kern
(`pipeline.py`, `evaluate.py`) kennt nur die Ports und bleibt davon unberührt.
"""

from __future__ import annotations

from .ai import AIClassifier, PrefilteredClassifier, build_language_model
from .ai.http import Transport, urllib_transport
from .classify import RuleClassifier
from .config import Rules
from .ports import Classifier, CredentialStore

CLASSIFIERS = ("ai", "rules")


def make_classifier(
    name: str, rules: Rules, creds: CredentialStore | None = None, transport: Transport = urllib_transport
) -> Classifier:
    """`ai`: Vorfilter plus KI (Standard für echte Läufe). `rules`: nur Stichwörter, offline."""
    if name == "rules":
        return RuleClassifier(rules)
    if name == "ai":
        if creds is None:
            raise ValueError("Für den KI-Klassifizierer werden Zugangsdaten gebraucht.")
        model = build_language_model(rules.ai, creds, transport)
        return PrefilteredClassifier(rules, AIClassifier(rules, model))
    raise ValueError(f"Unbekannter Klassifizierer: {name}")


def describe_classifier(classifier: Classifier) -> str:
    """Kurzbeschreibung für den Bericht, z. B. `KI: groq → mistral (Vorfilter: Regeln)`."""
    if isinstance(classifier, PrefilteredClassifier) and isinstance(classifier.ai, AIClassifier):
        return f"KI: {classifier.ai.model.name} (Vorfilter: Regeln)"
    if isinstance(classifier, RuleClassifier):
        return "Regeln (ohne KI)"
    return type(classifier).__name__
