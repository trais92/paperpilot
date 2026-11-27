"""Attrappen und Helfer, gemeinsam genutzt von mehreren Testdateien: KI-Anbieter, Schlüsselbund,
Browser für die lokalen Seiten. Kein Netz außer 127.0.0.1.
"""

import http.client
import json
import threading
import urllib.parse

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


class FakeKeyring:
    """Bildet die drei genutzten Funktionen des Pakets `keyring` nach."""

    def __init__(self):
        self.entries: dict[tuple[str, str], str] = {}

    def get_password(self, service_name, username):
        return self.entries.get((service_name, username))

    def set_password(self, service_name, username, password):
        self.entries[(service_name, username)] = password

    def delete_password(self, service_name, username):
        del self.entries[(service_name, username)]


class BrokenKeyring(FakeKeyring):
    def get_password(self, service_name, username):
        raise RuntimeError("Backend kaputt, Wert war app-passwort-0815")

    def set_password(self, service_name, username, password):
        raise RuntimeError(f"kann {password} nicht speichern")


# -- lokale Seiten (web/) ---------------------------------------------------------


def request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    response = conn.getresponse()
    data = response.read().decode("utf-8")
    conn.close()
    return response, data


def post_form(port, path, form, origin="same"):
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if origin == "same":
        headers["Origin"] = f"http://127.0.0.1:{port}"
    elif origin:
        headers["Origin"] = origin
    return request(port, "POST", path, urllib.parse.urlencode(form), headers)


def browser_clicking(action):
    """Ersetzt den Browser: lädt die Seite und schickt das Formular in einem eigenen Thread."""

    def open_browser(url):
        parts = urllib.parse.urlsplit(url)
        assert parts.hostname == "127.0.0.1"
        token = dict(urllib.parse.parse_qsl(parts.query))["token"]

        def click():
            request(parts.port, "GET", f"/?{parts.query}")
            if action:
                post_form(parts.port, f"/{action}", {"token": token})
                request(parts.port, "GET", f"/?{parts.query}")

        threading.Thread(target=click, daemon=True).start()

    return open_browser
