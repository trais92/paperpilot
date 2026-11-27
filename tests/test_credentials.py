"""Zugangsdaten: Umgebung, Schlüsselbund (mit Attrappe), Verkettung und die Befehle login/logout.

Kein Test berührt den echten Schlüsselbund oder ein echtes Postfach.
"""

import sys
import types

import pytest

from paperpilot_ops import cli
from paperpilot_ops.cli import _imap_source
from paperpilot_ops.credentials import (
    KEYS,
    ChainedCredentialStore,
    CredentialStoreError,
    EnvCredentialStore,
    KeyringCredentialStore,
    default_credential_store,
)

SECRET = "app-passwort-0815"


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
        raise RuntimeError(f"Backend kaputt, Wert war {SECRET}")

    def set_password(self, service_name, username, password):
        raise RuntimeError(f"kann {password} nicht speichern")


# -- Umgebungsvariablen ------------------------------------------------------------------


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


# -- Schlüsselbund -----------------------------------------------------------------------


def test_keyring_roundtrip_under_own_service_name():
    backend = FakeKeyring()
    vault = KeyringCredentialStore(backend)
    vault.set("imap_password", SECRET)
    assert vault.get("imap_password") == SECRET
    assert backend.entries == {("paperpilot", "imap_password"): SECRET}
    assert vault.delete("imap_password") is True
    assert vault.delete("imap_password") is False
    assert vault.get("imap_password") is None


def test_keyring_rejects_empty_values_and_unknown_keys():
    vault = KeyringCredentialStore(FakeKeyring())
    with pytest.raises(ValueError):
        vault.set("imap_password", "")
    with pytest.raises(KeyError):
        vault.set("lieblingsfarbe", "blau")


def test_backend_errors_never_contain_the_secret():
    vault = KeyringCredentialStore(BrokenKeyring())
    with pytest.raises(CredentialStoreError) as read_error:
        vault.get("imap_password")
    with pytest.raises(CredentialStoreError) as write_error:
        vault.set("imap_password", SECRET)
    for err in (read_error.value, write_error.value):
        assert SECRET not in str(err)
        assert err.__cause__ is None and err.__suppress_context__  # Originalfehler wird nicht angehängt


def test_repr_never_shows_values():
    backend = FakeKeyring()
    vault = KeyringCredentialStore(backend)
    vault.set("imap_password", SECRET)
    chain = ChainedCredentialStore(EnvCredentialStore({"PAPERPILOT_IMAP_PASSWORD": SECRET}), vault)
    assert SECRET not in repr(vault) + repr(chain)
    assert SECRET not in repr(cli.ImapSource("imap.mail.example", "alex", SECRET))


def test_missing_keyring_package_gives_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)  # Import schlägt fehl
    with pytest.raises(CredentialStoreError, match=r"paperpilot-ops\[keyring\]"):
        KeyringCredentialStore()


def test_placeholder_backend_counts_as_no_keyring(monkeypatch):
    fail_backend = types.SimpleNamespace(priority=0)
    monkeypatch.setitem(sys.modules, "keyring", types.SimpleNamespace(get_keyring=lambda: fail_backend))
    with pytest.raises(CredentialStoreError, match="Kein Schlüsselbund"):
        KeyringCredentialStore()


def test_real_backend_is_used_when_available(monkeypatch):
    fake = FakeKeyring()
    module = types.SimpleNamespace(
        get_keyring=lambda: types.SimpleNamespace(priority=5),
        get_password=fake.get_password,
        set_password=fake.set_password,
        delete_password=fake.delete_password,
    )
    monkeypatch.setitem(sys.modules, "keyring", module)
    KeyringCredentialStore().set("imap_user", "alex@mail.example")
    assert fake.entries[("paperpilot", "imap_user")] == "alex@mail.example"


# -- Verkettung --------------------------------------------------------------------------


def test_chain_prefers_environment_and_falls_back_to_keyring():
    vault = KeyringCredentialStore(FakeKeyring())
    vault.set("imap_user", "gespeichert@mail.example")
    vault.set("imap_password", SECRET)
    chain = ChainedCredentialStore(EnvCredentialStore({"PAPERPILOT_IMAP_USER": "env@mail.example"}), vault)
    assert chain.get("imap_user") == "env@mail.example"
    assert chain.get("imap_password") == SECRET
    assert chain.get("imap_host") is None
    with pytest.raises(KeyError):
        chain.get("unbekannt")


def test_default_store_without_keyring_reads_environment_only(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)
    store = default_credential_store({"PAPERPILOT_IMAP_USER": "env@mail.example"})
    assert isinstance(store, EnvCredentialStore)
    assert store.get("imap_user") == "env@mail.example"


def test_default_store_with_keyring_chains_environment_first(monkeypatch):
    fake = FakeKeyring()
    fake.set_password("paperpilot", "imap_user", "gespeichert@mail.example")
    module = types.SimpleNamespace(
        get_keyring=lambda: types.SimpleNamespace(priority=5),
        get_password=fake.get_password,
        set_password=fake.set_password,
        delete_password=fake.delete_password,
    )
    monkeypatch.setitem(sys.modules, "keyring", module)
    assert default_credential_store({}).get("imap_user") == "gespeichert@mail.example"


# -- CLI: Abfrage beim Lauf --------------------------------------------------------------


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


def test_missing_password_is_prompted_with_login_hint(monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda *_: SECRET)
    source = _imap_source(FakeCredentials(imap_user="alex@mail.example"))
    assert source.password == SECRET
    assert "paperpilot login" in capsys.readouterr().out


# -- CLI: login und logout ---------------------------------------------------------------


@pytest.fixture
def vault(monkeypatch, tmp_path):
    """Schlüsselbund-Attrappe, Arbeitsordner leer, Probe-Anmeldung abgeschaltet."""
    store = KeyringCredentialStore(FakeKeyring())
    monkeypatch.setattr(cli, "_open_vault", lambda: store)
    monkeypatch.setattr(cli, "_verify_imap", lambda source: None)
    monkeypatch.chdir(tmp_path)
    return store


def _answers(monkeypatch, *lines):
    it = iter(lines)
    monkeypatch.setattr("builtins.input", lambda *_: next(it))
    monkeypatch.setattr("getpass.getpass", lambda *_: SECRET)


def test_login_stores_in_keyring_and_nowhere_else(vault, monkeypatch, capsys, tmp_path):
    _answers(monkeypatch, "", "alex@mail.example")
    assert cli.main(["login"]) == 0
    assert vault.get("imap_host") == "imap.gmail.com"
    assert vault.get("imap_user") == "alex@mail.example"
    assert vault.get("imap_password") == SECRET
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err
    assert list(tmp_path.iterdir()) == []  # keine Datei angelegt


def test_next_run_does_not_ask_again(vault, monkeypatch):
    _answers(monkeypatch, "imap.mail.example", "alex@mail.example")
    cli.main(["login"])
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("darf nicht fragen"))
    monkeypatch.setattr("getpass.getpass", lambda *_: pytest.fail("darf nicht fragen"))
    source = _imap_source(ChainedCredentialStore(EnvCredentialStore({}), vault))
    assert (source.host, source.user, source.password) == ("imap.mail.example", "alex@mail.example", SECRET)


def test_failed_check_stores_nothing(vault, monkeypatch, capsys):
    def reject(source):
        raise OSError(f"login failed for {source.password}")

    monkeypatch.setattr(cli, "_verify_imap", reject)
    _answers(monkeypatch, "", "alex@mail.example")
    assert cli.main(["login"]) == 1
    assert all(vault.get(k) is None for k in KEYS)
    err = capsys.readouterr().err
    assert "Nichts gespeichert" in err and SECRET not in err


def test_login_requires_user(vault, monkeypatch):
    _answers(monkeypatch, "", "")
    assert cli.main(["login"]) == 1
    assert vault.get("imap_password") is None


def test_status_shows_presence_but_never_values(vault, monkeypatch, capsys):
    vault.set("imap_password", SECRET)
    assert cli.main(["login", "--status"]) == 0
    out = capsys.readouterr().out
    assert "imap_password    gespeichert" in out and "imap_user        fehlt" in out
    assert SECRET not in out


def test_logout_deletes_everything(vault, monkeypatch, capsys):
    _answers(monkeypatch, "", "alex@mail.example")
    cli.main(["login"])
    capsys.readouterr()
    assert cli.main(["logout"]) == 0
    assert "imap_password" in capsys.readouterr().out
    assert all(vault.get(k) is None for k in KEYS)
    assert cli.main(["logout"]) == 0
    assert "nichts gespeichert" in capsys.readouterr().out


def test_login_without_keyring_explains_alternative(monkeypatch, capsys):
    def unavailable():
        raise CredentialStoreError("Kein Schlüsselbund auf diesem System gefunden (Keyring).")

    monkeypatch.setattr(cli, "_open_vault", unavailable)
    assert cli.main(["login", "--status"]) == 2
    assert cli.main(["logout"]) == 2
    assert "Umgebungsvariablen" in capsys.readouterr().err


def test_login_ai_stores_api_key(vault, monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda *_: "  gsk-schluessel  ")
    assert cli.main(["login", "--ai", "groq"]) == 0
    assert vault.get("groq_api_key") == "gsk-schluessel"
    assert "gsk-schluessel" not in capsys.readouterr().out


def test_login_ai_empty_key_stores_nothing(vault, monkeypatch):
    monkeypatch.setattr("getpass.getpass", lambda *_: "")
    assert cli.main(["login", "--ai", "claude"]) == 1
    assert vault.get("claude_api_key") is None
