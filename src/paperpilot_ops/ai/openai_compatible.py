"""Adapter für Anbieter mit OpenAI-kompatibler Chat-Schnittstelle (Mistral, Groq).

Spricht `POST {base_url}/chat/completions` mit der Standardbibliothek an. Strukturierte Ausgabe wird
über den JSON-Modus (`response_format: json_object`) angefordert, den beide Anbieter für alle Modelle
anbieten; das Schema steht zusätzlich im Systemprompt. Die eigentliche Prüfung macht der Aufrufer.

Verhalten bei Störungen:
- 429 (Kontingent): einmal warten (höchstens `max_retry_wait` Sekunden, `Retry-After` wird beachtet),
  dann `ProviderError(kind="rate_limit")`.
- 401/403: `auth`, 5xx: `server`, keine Verbindung: `network`, kaputte Hülle: `invalid_response`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from ..models import Completion
from ..ports import ProviderError
from .http import HttpRequest, HttpResponse, Transport, TransportError, urllib_transport


class OpenAICompatibleModel:
    """Ein Modell hinter einer OpenAI-kompatiblen Schnittstelle."""

    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: str,
        *,
        transport: Transport = urllib_transport,
        timeout: float = 30.0,
        min_interval: float = 0.0,
        max_retry_wait: float = 20.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not base_url.startswith("https://"):
            raise ValueError("Nur verschlüsselte Verbindungen (https) sind erlaubt.")
        self._name = name
        self._url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout
        self._min_interval = min_interval
        self._max_retry_wait = max_retry_wait
        self._clock = clock
        self._sleep = sleep
        self._last_call: float | None = None

    def __repr__(self) -> str:
        return f"OpenAICompatibleModel(name={self._name!r}, model={self.model!r})"

    @property
    def name(self) -> str:
        return self._name

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> Completion:
        body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": f"{system}\n\nJSON-Schema der Antwort:\n{json.dumps(schema)}"},
                {"role": "user", "content": user},
            ],
        }
        request = HttpRequest(
            "POST",
            self._url,
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json.dumps(body).encode("utf-8"),
            self._timeout,
        )
        response = self._send(request)
        if response.status == 429:
            wait = _retry_after(response, default=self._max_retry_wait)
            if wait > self._max_retry_wait:
                raise ProviderError(self._name, "rate_limit", "Kontingent erschöpft")
            self._sleep(wait)
            response = self._send(request)
        return self._parse(response)

    def _send(self, request: HttpRequest) -> HttpResponse:
        if self._last_call is not None and self._min_interval > 0:
            remaining = self._min_interval - (self._clock() - self._last_call)
            if remaining > 0:
                self._sleep(remaining)  # Gratis-Tarife erlauben nur wenige Anfragen pro Sekunde/Minute
        self._last_call = self._clock()
        try:
            return self._transport(request)
        except TransportError as err:
            raise ProviderError(self._name, "network", f"keine Verbindung ({err})") from None

    def _parse(self, response: HttpResponse) -> Completion:
        status = response.status
        if status in (401, 403):
            raise ProviderError(self._name, "auth", f"Schlüssel abgelehnt (HTTP {status})")
        if status == 429:
            raise ProviderError(self._name, "rate_limit", "Kontingent erschöpft")
        if status >= 500:
            raise ProviderError(self._name, "server", f"Dienst gestört (HTTP {status})")
        if status != 200:
            raise ProviderError(self._name, "invalid_response", f"Anfrage abgelehnt (HTTP {status})")
        try:
            data = json.loads(response.body)
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError(self._name, "invalid_response", "Antwort hat nicht das erwartete Format") from None
        if not isinstance(text, str):
            raise ProviderError(self._name, "invalid_response", "Antwort enthält keinen Text")
        return Completion(text, self._name, usage.get("prompt_tokens"), usage.get("completion_tokens"))


def _retry_after(response: HttpResponse, default: float) -> float:
    try:
        return float(response.headers.get("retry-after", default))
    except ValueError:
        return default
