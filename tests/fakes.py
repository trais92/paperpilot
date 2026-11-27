"""Attrappen für KI-Anbieter, gemeinsam genutzt von mehreren Testdateien. Kein Netz."""

import json

from paperpilot_ops.ai.http import HttpResponse, TransportError
from paperpilot_ops.models import Completion
from paperpilot_ops.ports import ProviderError


def chat_response(content, status=200, headers=None, usage=None):
    """Antwort im Format einer OpenAI-kompatiblen Chat-Schnittstelle."""
    body = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    if usage:
        body["usage"] = usage
    return HttpResponse(status, json.dumps(body).encode(), headers or {})


class FakeTransport:
    """Gibt vorbereitete Antworten der Reihe nach zurück und merkt sich die Anfragen."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def offline():
    return TransportError("URLError")


class ScriptedModel:
    """`LanguageModel`, das feste Texte liefert oder Fehler wirft."""

    def __init__(self, name, *answers):
        self._name = name
        self.answers = list(answers)
        self.calls = []

    @property
    def name(self):
        return self._name

    def complete_json(self, system, user, schema):
        self.calls.append((system, user, schema))
        answer = self.answers.pop(0)
        if isinstance(answer, ProviderError):
            raise answer
        if isinstance(answer, dict):
            answer = json.dumps(answer)
        return Completion(answer, self._name)
