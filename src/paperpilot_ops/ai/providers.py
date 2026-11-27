"""Bekannte KI-Anbieter und der Aufbau eines `LanguageModel` aus Konfiguration und Zugangsdaten.

Stand der Angaben: 27.11.2026, aus den offiziellen Unterlagen der Anbieter (Quellen in docs/ai-providers.md).
Modelle lassen sich je Anbieter in `[ai.models]` überschreiben, falls ein Anbieter sie umbenennt.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import AISettings
from ..ports import CredentialStore, LanguageModel
from .anthropic import DEFAULT_CLAUDE_MODEL, AnthropicModel
from .fallback import FallbackModel
from .http import Transport, urllib_transport
from .openai_compatible import OpenAICompatibleModel


@dataclass(frozen=True)
class OpenAICompatibleProvider:
    base_url: str
    default_model: str
    min_interval: float  # Sekunden zwischen zwei Anfragen, passend zum Gratis-Kontingent
    reserve_model: str = ""  # zweites Modell desselben Anbieters mit eigenem Kontingent (ADR 0012)


RESERVE_SUFFIX = "-reserve"


# Aufgenommen werden nur Anbieter, die ohne Kreditkarte und ohne Abrechnung nutzbar sind
# (Kriterien und geprüfte Kandidaten: docs/ai-providers.md). Claude ist die bewusste Ausnahme:
# nicht voreingestellt, nur mit eigenem, kostenpflichtigem Schlüssel.
OPENAI_COMPATIBLE: dict[str, OpenAICompatibleProvider] = {
    # Gratis-Tarif: 30 Anfragen pro Minute, 1000 pro Tag, je Modell gezählt. Ist das Tageskontingent
    # von gpt-oss-20b erschöpft, antwortet gpt-oss-120b mit demselben Schlüssel (ADR 0012).
    "groq": OpenAICompatibleProvider(
        "https://api.groq.com/openai/v1", "openai/gpt-oss-20b", 2.0, reserve_model="openai/gpt-oss-120b"
    ),
}


# Anbieter, die über den eigenen Schlüssel abgerechnet werden. Überall, wo sie auftauchen
# (Hilfe, Anmeldung, Lauf, Assistent, Doku), steht deutlich „kostenpflichtig“ dabei.
PAID_PROVIDERS = frozenset({"claude"})
PAID_NOTICE = "kostenpflichtig, Abrechnung über deinen eigenen Schlüssel beim Anbieter"


def describe_provider(provider: str) -> str:
    """`groq (kostenlos)` bzw. `claude (kostenpflichtig, …)` für Hilfe und Hinweise."""
    return f"{provider} ({PAID_NOTICE if provider in PAID_PROVIDERS else 'kostenlos'})"


class MissingAIKeyError(RuntimeError):
    """Für keinen der konfigurierten Anbieter ist ein Schlüssel hinterlegt."""


def credential_key(provider: str) -> str:
    """Name des Zugangsdaten-Schlüssels für einen Anbieter, z. B. `groq_api_key`."""
    return f"{provider}_api_key"


def build_language_model(
    settings: AISettings, creds: CredentialStore, transport: Transport = urllib_transport
) -> LanguageModel:
    """Baut die Reserve-Kette aus allen Anbietern in `settings.chain`, für die ein Schlüssel vorliegt."""
    models: list[LanguageModel] = []
    for provider in settings.chain:
        api_key = creds.get(credential_key(provider))
        if not api_key:
            continue
        model_name = settings.models.get(provider)
        if provider == "claude":
            models.append(AnthropicModel(api_key, model_name or DEFAULT_CLAUDE_MODEL))
            continue
        spec = OPENAI_COMPATIBLE[provider]
        main = model_name or spec.default_model
        names = [(provider, main)]
        if settings.reserve_models and spec.reserve_model and spec.reserve_model != main:
            names.append((provider + RESERVE_SUFFIX, spec.reserve_model))
        models.extend(
            OpenAICompatibleModel(
                name, spec.base_url, model, api_key, transport=transport, min_interval=spec.min_interval
            )
            for name, model in names
        )
    if not models:
        first = settings.chain[0]
        raise MissingAIKeyError(
            f"Kein KI-Schlüssel gefunden ({', '.join(settings.chain)}). "
            f"Einmal speichern mit: paperpilot login --ai {first}"
        )
    return models[0] if len(models) == 1 else FallbackModel(*models)
