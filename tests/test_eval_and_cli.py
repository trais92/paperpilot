from personal_ops.cli import main


def test_eval_meets_baseline(capsys):
    # Schutz gegen Verschlechterung: Regeln aendern darf die Trefferquote nicht unter 85 % druecken
    assert main(["eval", "--min-accuracy", "0.85"]) == 0
    assert "Genauigkeit" in capsys.readouterr().out


def test_demo_runs_end_to_end(tmp_path, capsys):
    out = tmp_path / "demo"
    assert main(["demo", "--out", str(out)]) == 0
    first = capsys.readouterr().out
    assert "MELDEN" in first and (out / "Fristen/fristen.ics").exists()
    assert main(["demo", "--out", str(out)]) == 0
    assert "0 Mails" in capsys.readouterr().out


def test_init_does_not_overwrite(tmp_path):
    path = tmp_path / "rules.toml"
    assert main(["init", "--path", str(path)]) == 0
    assert main(["init", "--path", str(path)]) == 1
