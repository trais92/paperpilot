"""Vertrag des Ports `LanguageModel` für jeden Adapter, dazu Besonderheiten je Adapter. Kein Netz."""

import json
import sys
import types

import pytest
from fakes import FakeTransport, ScriptedModel, chat_response, offline

from paperpilot_ops.ai.anthropic import AnthropicModel
from paperpilot_ops.ai.fallback import FallbackModel
from paperpilot_ops.ai.http import HttpRequest, HttpResponse, TransportError, urllib_transport
from paperpilot_ops.ai.openai_compatible import OpenAICompatibleModel
from paperpilot_ops.ai.providers import MissingAIKeyError, build_language_model
from paperpilot_ops.config import AISettings
from paperpilot_ops.credentials import EnvCredentialStore
from paperpilot_ops.ports import LanguageModel, ProviderError

KEY = "sk-test-geheim-123"
SCHEMA = {"type": "object"}
ANSWER = '{"label": "privat/rechnungen", "confidence": 0.9, "reason": "Rechnung"}'


# -- Attrappe für das Anthropic-SDK -------------------------------------------------------


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Response:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [_Block(text)] if text is not None else []
        self.stop_reason = stop_reason
        self.usage = types.SimpleNamespace(input_tokens=120, output_tokens=15)


class RateLimitError(Exception):
    """Gleicher Klassenname wie im SDK, damit die Zuordnung greift."""


class FakeAnthropicClient:
    def __init__(self, outcome):
        self.calls = []
        client = self

        class _Messages:
            def create(self, **kwargs):
                client.calls.append(kwargs)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        self.beta = types.SimpleNamespace(messages=_Messages())


# -- Vertragstest: jeder Adapter, Erfolg und Störung ---------------------------------------


def _openai(*responses):
    return OpenAICompatibleModel(
        "groq", "https://api.groq.example/v1", "modell-x", KEY, transport=FakeTransport(*responses)
    )


ADAPTERS = {
    "openai_compatible": (lambda: _openai(chat_response(ANSWER)), lambda: _openai(offline())),
    "anthropic": (
        lambda: AnthropicModel(KEY, client=FakeAnthropicClient(_Response(ANSWER))),
        lambda: AnthropicModel(KEY, client=FakeAnthropicClient(ConnectionError("x"))),
    ),
    "fallback": (
        lambda: FallbackModel(ScriptedModel("a", ProviderError("a", "network", "aus")), ScriptedModel("b", ANSWER)),
        lambda: FallbackModel(ScriptedModel("a", ProviderError("a", "auth", "nein"))),
    ),
}


@pytest.fixture(params=list(ADAPTERS))
def adapter(request):
    return ADAPTERS[request.param]


def test_contract_returns_text_unchanged(adapter):
    model: LanguageModel = adapter[0]()
    completion = model.complete_json("system", "user", SCHEMA)
    assert completion.text == ANSWER
    assert completion.provider and isinstance(model.name, str)


def test_contract_failures_become_provider_error(adapter):
    with pytest.raises(ProviderError):
        adapter[1]().complete_json("system", "user", SCHEMA)


def test_contract_key_never_in_repr(adapter):
    assert KEY not in repr(adapter[0]())


# -- OpenAI-kompatibel (Groq) ----------------------------------------------------


def test_openai_request_shape():
    transport = FakeTransport(chat_response(ANSWER, usage={"prompt_tokens": 50, "completion_tokens": 9}))
    model = OpenAICompatibleModel("groq", "https://api.groq.example/v1/", "klein", KEY, transport=transport)
    completion = model.complete_json("SYS", "USER", {"type": "object", "x": 1})
    req = transport.requests[0]
    body = json.loads(req.body)
    assert req.method == "POST" and req.url == "https://api.groq.example/v1/chat/completions"
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    assert body["model"] == "klein" and body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system" and '"x": 1' in body["messages"][0]["content"]
    assert body["messages"][1] == {"role": "user", "content": "USER"}
    assert (completion.provider, completion.input_tokens, completion.output_tokens) == ("groq", 50, 9)
    assert KEY not in repr(req)


def test_openai_only_https():
    with pytest.raises(ValueError):
        OpenAICompatibleModel("x", "http://api.example/v1", "m", KEY)


@pytest.mark.parametrize(
    ("status", "kind"), [(401, "auth"), (403, "auth"), (500, "server"), (503, "server"), (400, "invalid_response")]
)
def test_openai_http_errors(status, kind):
    with pytest.raises(ProviderError) as err:
        _openai(HttpResponse(status, b"{}")).complete_json("s", "u", SCHEMA)
    assert err.value.kind == kind and KEY not in str(err.value)


@pytest.mark.parametrize(
    "body", [b"kein json", b"{}", b'{"choices": []}', b'{"choices": [{"message": {"content": 5}}]}']
)
def test_openai_broken_envelope(body):
    with pytest.raises(ProviderError) as err:
        _openai(HttpResponse(200, body)).complete_json("s", "u", SCHEMA)
    assert err.value.kind == "invalid_response"


def test_openai_rate_limit_waits_once_then_succeeds():
    waits = []
    transport = FakeTransport(HttpResponse(429, b"", {"retry-after": "3"}), chat_response(ANSWER))
    model = OpenAICompatibleModel("groq", "https://g.example/v1", "m", KEY, transport=transport, sleep=waits.append)
    assert model.complete_json("s", "u", SCHEMA).text == ANSWER
    assert waits == [3.0]


def test_openai_rate_limit_twice_is_error():
    transport = FakeTransport(HttpResponse(429, b""), HttpResponse(429, b""))
    model = OpenAICompatibleModel("groq", "https://g.example/v1", "m", KEY, transport=transport, sleep=lambda s: None)
    with pytest.raises(ProviderError) as err:
        model.complete_json("s", "u", SCHEMA)
    assert err.value.kind == "rate_limit"


def test_openai_long_retry_after_gives_up_immediately():
    transport = FakeTransport(HttpResponse(429, b"", {"retry-after": "3600"}))
    model = OpenAICompatibleModel("groq", "https://g.example/v1", "m", KEY, transport=transport, sleep=pytest.fail)
    with pytest.raises(ProviderError, match="Kontingent"):
        model.complete_json("s", "u", SCHEMA)


def test_openai_throttles_to_min_interval():
    now = [100.0]
    waits = []
    transport = FakeTransport(chat_response(ANSWER), chat_response(ANSWER))
    model = OpenAICompatibleModel(
        "groq", "https://g.example/v1", "m", KEY, transport=transport, min_interval=2.0,
        clock=lambda: now[0], sleep=waits.append,
    )  # fmt: skip
    model.complete_json("s", "u", SCHEMA)
    now[0] += 0.5
    model.complete_json("s", "u", SCHEMA)
    assert waits == [1.5]


# -- Claude -------------------------------------------------------------------------------


def test_anthropic_request_uses_structured_output_and_fallbacks():
    client = FakeAnthropicClient(_Response(ANSWER))
    completion = AnthropicModel(KEY, client=client).complete_json("SYS", "USER", SCHEMA)
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["system"] == "SYS"
    assert call["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert (completion.input_tokens, completion.output_tokens) == (120, 15)


def test_anthropic_refusal_and_empty_answer():
    with pytest.raises(ProviderError) as refusal:
        AnthropicModel(KEY, client=FakeAnthropicClient(_Response("", "refusal"))).complete_json("s", "u", SCHEMA)
    with pytest.raises(ProviderError) as empty:
        AnthropicModel(KEY, client=FakeAnthropicClient(_Response(None))).complete_json("s", "u", SCHEMA)
    assert (refusal.value.kind, empty.value.kind) == ("refusal", "invalid_response")


def test_anthropic_sdk_errors_are_mapped_by_class_name():
    with pytest.raises(ProviderError) as err:
        AnthropicModel(KEY, client=FakeAnthropicClient(RateLimitError(KEY))).complete_json("s", "u", SCHEMA)
    assert err.value.kind == "rate_limit" and KEY not in str(err.value)


def test_anthropic_without_sdk_explains_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(ProviderError, match=r"paperpilot-ops\[llm\]"):
        AnthropicModel(KEY)


# -- Reserve-Kette ------------------------------------------------------------------------


def test_fallback_asks_next_only_on_provider_error():
    first = ScriptedModel("groq", ProviderError("groq", "rate_limit", "voll"))
    second = ScriptedModel("reserve", ANSWER)
    chain = FallbackModel(first, second)
    assert chain.name == "groq → reserve"
    assert chain.complete_json("s", "u", SCHEMA).provider == "reserve"


def test_fallback_does_not_ask_reserve_after_an_answer():
    first, second = ScriptedModel("groq", "kein json"), ScriptedModel("reserve", ANSWER)
    assert FallbackModel(first, second).complete_json("s", "u", SCHEMA).text == "kein json"
    assert second.calls == []


def test_fallback_reports_all_failures():
    chain = FallbackModel(
        ScriptedModel("groq", ProviderError("groq", "network", "x")),
        ScriptedModel("reserve", ProviderError("reserve", "auth", "y")),
    )
    with pytest.raises(ProviderError, match=r"groq \(network\); reserve \(auth\)"):
        chain.complete_json("s", "u", SCHEMA)


def test_fallback_needs_a_model():
    with pytest.raises(ValueError):
        FallbackModel()


# -- Aufbau aus Konfiguration und Zugangsdaten --------------------------------------------


def _fake_anthropic_sdk(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=lambda api_key: object()))


def test_build_uses_only_providers_with_keys(monkeypatch):
    _fake_anthropic_sdk(monkeypatch)
    creds = EnvCredentialStore({"PAPERPILOT_CLAUDE_API_KEY": KEY})
    model = build_language_model(AISettings(provider="groq", fallback=("claude",)), creds)
    assert model.name == "claude"


def test_build_chain_and_model_override(monkeypatch):
    _fake_anthropic_sdk(monkeypatch)
    creds = EnvCredentialStore({"PAPERPILOT_GROQ_API_KEY": KEY, "PAPERPILOT_CLAUDE_API_KEY": KEY})
    settings = AISettings(provider="groq", fallback=("claude",), models={"groq": "anderes-modell"})
    model = build_language_model(settings, creds)
    assert isinstance(model, FallbackModel) and model.name == "groq → claude"
    assert "anderes-modell" in repr(model)


def test_default_settings_use_only_free_groq():
    model = build_language_model(AISettings(), EnvCredentialStore({"PAPERPILOT_GROQ_API_KEY": KEY}))
    assert model.name == "groq" and "openai/gpt-oss-20b" in repr(model)


def test_build_claude_with_injected_sdk(monkeypatch):
    seen = {}
    fake_sdk = types.SimpleNamespace(Anthropic=lambda api_key: seen.setdefault("key", api_key) and object())
    monkeypatch.setitem(sys.modules, "anthropic", fake_sdk)
    model = build_language_model(
        AISettings(provider="claude", fallback=()), EnvCredentialStore({"PAPERPILOT_CLAUDE_API_KEY": KEY})
    )
    assert model.name == "claude" and seen["key"] == KEY


def test_build_without_any_key_explains_login():
    with pytest.raises(MissingAIKeyError, match="paperpilot login --ai groq"):
        build_language_model(AISettings(), EnvCredentialStore({}))


# -- HTTP-Baustein ------------------------------------------------------------------------


def test_urllib_transport_maps_unreachable_host_to_transport_error():
    with pytest.raises(TransportError):
        urllib_transport(HttpRequest("POST", "https://127.0.0.1:9/v1", {}, b"{}", timeout=0.5))
