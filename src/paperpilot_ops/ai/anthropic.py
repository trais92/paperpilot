"""Adapter für Claude über das offizielle SDK (optionales Extra: pip install "paperpilot-ops[llm]").

Nutzt strukturierte Ausgabe (`output_config.format` mit JSON-Schema), niedrigen Aufwand
(`effort: "low"`) und die serverseitige Reserve von Anthropic bei Ablehnungen (`fallbacks="default"`).
Gegen die echte Schnittstelle noch nicht gemessen (siehe docs/ai-providers.md).
"""

from __future__ import annotations

from typing import Any

from ..models import Completion
from ..ports import ProviderError

DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"

# Fehlerklassen des SDK nach Art der Störung, über den Klassennamen zugeordnet,
# damit das SDK nur geladen wird, wenn Claude wirklich genutzt wird.
_ERROR_KINDS = {
    "AuthenticationError": "auth",
    "PermissionDeniedError": "auth",
    "RateLimitError": "rate_limit",
    "APIConnectionError": "network",
    "APITimeoutError": "network",
    "InternalServerError": "server",
}


class AnthropicModel:
    """Claude als `LanguageModel`. `client` ist austauschbar (Tests)."""

    def __init__(self, api_key: str, model: str = DEFAULT_CLAUDE_MODEL, client: Any = None):
        if client is None:
            try:
                import anthropic  # optionales Extra
            except ImportError:
                raise ProviderError(
                    "claude", "invalid_response", 'Paket "anthropic" fehlt: pip install "paperpilot-ops[llm]"'
                ) from None
            client = anthropic.Anthropic(api_key=api_key)
        self._client = client
        self.model = model

    def __repr__(self) -> str:
        return f"AnthropicModel(model={self.model!r})"

    @property
    def name(self) -> str:
        return "claude"

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> Completion:
        try:
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=1024,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=system,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # SDK-Fehler werden zu ProviderError, ohne Originaltext
            kind = _ERROR_KINDS.get(type(exc).__name__, "server")
            raise ProviderError("claude", kind, f"Anfrage fehlgeschlagen ({type(exc).__name__})") from None
        if response.stop_reason == "refusal":
            raise ProviderError("claude", "refusal", "Anfrage abgelehnt")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ProviderError("claude", "invalid_response", "Antwort enthält keinen Text")
        usage = getattr(response, "usage", None)
        return Completion(text, "claude", getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None))
