import pytest

from paperpilot_ops.cli import _imap_source
from paperpilot_ops.credentials import KEYS, EnvCredentialStore


def test_reads_known_keys_from_environment():
    store = EnvCredentialStore({"PAPERPILOT_IMAP_USER": "alex@mail.example"})
    assert store.get("imap_user") == "alex@mail.example"
    assert store.get("imap_password") is None


def test_empty_value_counts_as_missing():
    assert EnvCredentialStore({"PAPERPILOT_IMAP_PASSWORD": ""}).get("imap_password") is None


def test_unknown_key_is_a_programming_error():
    with pytest.raises(KeyError):
        EnvCredentialStore({}).get("passwort")


def test_every_key_maps_to_a_paperpilot_variable():
    assert all(var.startswith("PAPERPILOT_") for var in KEYS.values())


class FakeCredentials:
    def __init__(self, **values):
        self.values = values

    def get(self, key):
        return self.values.get(key)


def test_imap_source_uses_credential_store_without_prompt(monkeypatch):
    def no_prompt(*_):
        raise AssertionError("darf nicht nachfragen, wenn Zugangsdaten vorhanden sind")

    monkeypatch.setattr("builtins.input", no_prompt)
    monkeypatch.setattr("getpass.getpass", no_prompt)
    source = _imap_source(FakeCredentials(imap_user="alex@mail.example", imap_password="geheim"))
    assert (source.host, source.user, source.password) == ("imap.gmail.com", "alex@mail.example", "geheim")
