"""Laden der Konfiguration: Abschnitt [ai] und Beschreibungen der Kategorien."""

import pytest

from paperpilot_ops.config import AISettings, load_rules


def _write(tmp_path, text):
    path = tmp_path / "rules.toml"
    path.write_text(text, "utf-8")
    return path


def test_defaults_without_ai_section(tmp_path):
    rules = load_rules(_write(tmp_path, ""))
    assert rules.ai == AISettings()
    assert rules.ai.chain == ("groq",)


def test_ai_section_is_read(tmp_path):
    path = _write(
        tmp_path,
        '[ai]\nprovider = "claude"\nfallback = ["groq", "claude"]\nmin_confidence = 0.75\n'
        '[ai.models]\ngroq = "anderes-modell"\n',
    )
    ai = load_rules(path).ai
    assert ai.chain == ("claude", "groq")  # doppelte Einträge fallen weg
    assert ai.min_confidence == 0.75 and ai.models == {"groq": "anderes-modell"}


@pytest.mark.parametrize(
    "text",
    [
        '[ai]\nprovider = "orakel"\n',
        '[ai]\nfallback = ["mistral"]\n',
        "[ai]\nmin_confidence = 2\n",
        '[ai.models]\nx = "y"\n',
    ],
)
def test_invalid_ai_settings_fail_on_load(tmp_path, text):
    with pytest.raises(ValueError):
        load_rules(_write(tmp_path, text))


def test_every_default_category_has_a_description(rules):
    assert all(c.description for c in rules.categories)
