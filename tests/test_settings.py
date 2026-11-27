"""Persönliche Einstellungen (settings.toml) aus dem Assistenten (ADR 0010)."""

import tomllib
from pathlib import Path

import pytest

from paperpilot_ops import cli
from paperpilot_ops.credentials import EnvCredentialStore
from paperpilot_ops.settings import (
    UserSettings,
    apply_settings,
    config_dir,
    load_settings,
    render_settings,
    save_settings,
    settings_path,
)


def test_config_dir_per_platform(tmp_path):
    home = tmp_path
    assert config_dir({}, "linux", home) == home / ".config" / "paperpilot"
    assert config_dir({"XDG_CONFIG_HOME": "/x"}, "linux", home) == Path("/x/paperpilot")
    assert config_dir({}, "darwin", home) == home / "Library" / "Application Support" / "PaperPilot"
    assert config_dir({"APPDATA": "C:/Users/a/AppData/Roaming"}, "win32", home) == Path(
        "C:/Users/a/AppData/Roaming/PaperPilot"
    )
    assert config_dir({"PAPERPILOT_CONFIG_DIR": "/portabel"}, "win32", home) == Path("/portabel")


def test_tests_never_touch_real_settings(isolated_config):
    assert settings_path().parent == isolated_config


def test_missing_file_means_rules_only(tmp_path, rules):
    settings = load_settings(tmp_path / "fehlt.toml")
    assert settings == UserSettings()
    assert apply_settings(rules, settings) == rules


def test_roundtrip_with_special_characters(tmp_path):
    path = tmp_path / "a" / "settings.toml"
    original = UserSettings(
        storage_target="local",
        target_dir='C:\\Ablage "Privat"\nneu',
        categories={"bewerbung/absage": False, "privat/rechnungen": True},
    )
    save_settings(original, path)
    assert load_settings(path) == original
    assert not list(path.parent.glob(".settings-*"))  # keine Reste der atomaren Schreibweise
    tomllib.loads(render_settings(original))  # gültiges TOML


def test_apply_overrides_storage_and_selection(rules):
    settings = UserSettings(
        storage_target="drive", drive_folder="Belege", target_dir="anders", categories={"bewerbung/absage": False}
    )
    applied = apply_settings(rules, settings)
    assert applied.storage.target == "drive" and applied.storage.drive_folder == "Belege"
    assert applied.target_dir == "anders"
    assert not applied.is_selected("bewerbung/absage")
    assert applied.is_selected("bewerbung/einladung")


@pytest.mark.parametrize(
    "kwargs",
    [{"storage_target": "ftp"}, {"drive_folder": "a/b"}, {"drive_folder": " "}, {"target_dir": ""}],
)
def test_invalid_values_are_rejected(kwargs):
    with pytest.raises(ValueError):
        UserSettings(**kwargs)


def test_unknown_category_is_an_error(rules):
    with pytest.raises(ValueError, match="erfunden"):
        apply_settings(rules, UserSettings(categories={"erfunden": True}))


def test_non_boolean_category_value_is_an_error(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('[categories]\n"bewerbung/absage" = "nein"\n', "utf-8")
    with pytest.raises(ValueError):
        load_settings(path)


def test_run_uses_settings(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "default_credential_store", lambda: EnvCredentialStore({}))
    target = tmp_path / "aus-einstellungen"
    save_settings(UserSettings(storage_target="local", target_dir=str(target)), settings_path())
    assert cli.main(["run", "--classifier", "rules", "--apply"]) == 0
    assert any(target.iterdir())
