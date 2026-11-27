import csv

from paperpilot_ops.classify import FixedClassifier, RuleClassifier
from paperpilot_ops.models import Classification, Fields
from paperpilot_ops.pipeline import render_report, run
from paperpilot_ops.store import LocalStore, MemoryStore


def _mails(make_mail):
    return [
        make_mail(
            "Einladung zum Interview",
            "Zu Ihrer Bewerbung als PM laden wir Sie am 03.12.2026 um 11:00 Uhr ein.",
            sender="HR <jobs@kranich.example>",
            date="2026-11-18T10:00",
        ),
        make_mail(
            "Ihre Rechnung",
            "Zahlbar bis 15.12.2026.",
            sender="<rechnung@stadtwerke.example>",
            date="2026-11-19T10:00",
            attachments=[("Rechnung.pdf", b"%PDF demo")],
        ),
        make_mail("Newsletter: 30 % Rabatt", "Jetzt sichern. Abmelden.", sender="<newsletter@shop.example>"),
        make_mail("Hallo", "Lange nicht gesehen", sender="Sam <sam@example.com>", date="2026-11-21T10:00"),
    ]


def test_dry_run_writes_nothing(tmp_path, rules, make_mail):
    result = run(_mails(make_mail), RuleClassifier(rules), rules, LocalStore(tmp_path))
    assert not result.applied
    assert list(tmp_path.iterdir()) == []
    assert [p.action for p in result.plans] == ["file", "file", "ignore", "review"]


def test_apply_files_tracks_and_is_idempotent(tmp_path, rules, make_mail):
    clf = RuleClassifier(rules)
    run(_mails(make_mail), clf, rules, LocalStore(tmp_path), apply=True)

    assert (tmp_path / "06 Rechnungen & Belege/2026/2026-11-19_Stadtwerke_Rechnung.pdf").exists()
    assert any((tmp_path / "Bewerbungen/Kranich").glob("2026-11-18_Kranich_Einladung-Interview.md"))
    assert any((tmp_path / "00 Eingang").iterdir())  # unklar -> Mensch prueft

    rows = list(csv.DictReader((tmp_path / "Bewerbungen/tracker.csv").open(encoding="utf-8")))
    assert rows[0]["firma"] == "Kranich" and rows[0]["status"] == "einladung"
    assert rows[0]["neu_aus_mail"].startswith("NEU 2026-11-18")

    ics = (tmp_path / "Fristen/fristen.ics").read_text()
    assert "20261203T110000" in ics and "20261215" in ics

    # Zweiter Lauf mit denselben Mails: alles schon da
    store = LocalStore(tmp_path)
    second = run(
        [m for m in _mails(make_mail) if store.last_run() is None or m.date > store.last_run()], clf, rules, store
    )
    assert second.plans == []
    third = run(_mails(make_mail), clf, rules, LocalStore(tmp_path))
    assert {p.action for p in third.plans} <= {"duplicate", "ignore"}


def test_pipeline_works_with_any_storage_target(rules, make_mail):
    """Der Kern kennt nur den Port: derselbe Lauf funktioniert ohne Dateisystem."""
    store = MemoryStore()
    result = run(_mails(make_mail), RuleClassifier(rules), rules, store, apply=True)

    assert result.applied
    assert "06 Rechnungen & Belege/2026/2026-11-19_Stadtwerke_Rechnung.pdf" in store.files
    assert "Bewerbungen/tracker.csv" in store.texts
    assert "20261215" in (store.read_text("Fristen/fristen.ics") or "")
    assert store.last_run() is not None


def test_dry_run_writes_nothing_to_memory_store(rules, make_mail):
    store = MemoryStore()
    run(_mails(make_mail), RuleClassifier(rules), rules, store)
    assert store.files == {} and store.texts == {} and store.last_run() is None


# -- Wählbare Kategorien und Übersichtstabellen ------------------------------------------


def test_rules_table_location_is_fixed_part_of_folder(rules):
    assert rules.table_for("06 Rechnungen & Belege/{year}") == "06 Rechnungen & Belege/Übersicht"
    assert rules.table_for("Bewerbungen/{company}") == "Bewerbungen/Übersicht"
    assert rules.table_for("00 Eingang") == "00 Eingang/Übersicht"
    assert rules.table_for("{year}/Belege") == "Übersicht"


def test_apply_fills_one_overview_per_category(rules, make_mail):
    store = MemoryStore()
    run(_mails(make_mail), RuleClassifier(rules), rules, store, apply=True)
    invoices = store.read_rows("06 Rechnungen & Belege/Übersicht")
    assert len(invoices) == 1
    row = invoices[0]
    assert (row["Kategorie"], row["Frist"], row["Absender"]) == ("privat/rechnungen", "2026-12-15", "Stadtwerke")
    assert row["Dateien"].endswith("2026-11-19_Stadtwerke_Rechnung.pdf") and " | " in row["Dateien"]
    assert store.read_rows("Bewerbungen/Übersicht")[0]["Kategorie"] == "bewerbung/einladung"
    assert store.read_rows("00 Eingang/Übersicht")[0]["Betreff"] == "Hallo"
    assert set(store.tables) == {"06 Rechnungen & Belege/Übersicht", "Bewerbungen/Übersicht", "00 Eingang/Übersicht"}


def test_overview_lists_actual_paths_after_collision(rules, make_mail):
    store = MemoryStore()
    store.write_file("06 Rechnungen & Belege/2026/2026-11-19_Stadtwerke_Rechnung.pdf", b"anderer Inhalt")
    run(_mails(make_mail), RuleClassifier(rules), rules, store, apply=True)
    row = store.read_rows("06 Rechnungen & Belege/Übersicht")[0]
    assert "2026-11-19_Stadtwerke_Rechnung-2.pdf" in row["Dateien"]


def test_dry_run_writes_no_overview(rules, make_mail):
    store = MemoryStore()
    run(_mails(make_mail), RuleClassifier(rules), rules, store)
    assert store.tables == {}


def test_local_overview_opens_in_excel(tmp_path, rules, make_mail):
    run(_mails(make_mail), RuleClassifier(rules), rules, LocalStore(tmp_path), apply=True)
    raw = (tmp_path / "06 Rechnungen & Belege/Übersicht.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM: Excel erkennt UTF-8
    header = "Datum;Absender;Betreff;Kategorie;Betrag;Belegdatum;Nummer;Frist;Dateien;Begründung;Mail-ID"
    assert raw.decode("utf-8-sig").splitlines()[0] == header


def test_ai_fields_reach_overview_report_and_calendar(tmp_path, rules, make_mail):

    mail = make_mail("Ihre Rechnung", "Siehe Anhang.", attachments=[("Rechnung.pdf", b"%PDF demo")])
    fields = Fields(amount="49.90 EUR", document_date="2026-11-19", reference="R-2026-17", due_date="2026-12-15")
    clf = FixedClassifier({mail.id: Classification("privat/rechnungen", 0.9, "KI (groq): Rechnung", fields)})
    store = LocalStore(tmp_path)
    result = run([mail], clf, rules, store, apply=True)

    rows = store.read_rows(result.plans[0].table)
    assert rows[0]["Betrag"] == "49.90 EUR" and rows[0]["Nummer"] == "R-2026-17"
    assert rows[0]["Belegdatum"] == "2026-11-19" and rows[0]["Frist"] == "2026-12-15"
    assert "20261215" in (tmp_path / "Fristen/fristen.ics").read_text()  # Frist aus dem PDF im Kalender
    report = render_report(result, store.location)
    assert "ANGABEN:" in report and "49.90 EUR · Nr. R-2026-17 · vom 2026-11-19 · Frist 2026-12-15" in report


def test_ai_due_date_already_found_in_text_is_not_doubled(rules, make_mail):

    mail = make_mail("Rechnung", "Zahlbar bis 15.12.2026.")
    clf = FixedClassifier({mail.id: Classification("privat/rechnungen", 0.9, "", Fields(due_date="2026-12-15"))})
    result = run([mail], clf, rules, MemoryStore())
    assert len(result.plans[0].deadlines) == 1


def _default_rules_edited(tmp_path, old, new):
    """Standardregeln mit einer Textersetzung laden, so wie ein Mensch die Datei anpassen würde."""
    from paperpilot_ops.config import default_rules_text, load_rules

    text = default_rules_text()
    assert old in text
    path = tmp_path / "rules.toml"
    path.write_text(text.replace(old, new, 1), "utf-8")
    return load_rules(path)


def test_unselected_category_is_skipped_and_reported(tmp_path, make_mail):
    rules = _default_rules_edited(
        tmp_path, 'label = "privat/rechnungen"', 'label = "privat/rechnungen"\nenabled = false'
    )
    store = MemoryStore()
    result = run(_mails(make_mail), RuleClassifier(rules), rules, store, apply=True)
    assert [p.action for p in result.plans] == ["file", "skip", "ignore", "review"]
    assert not any("Rechnungen" in path for path in store.files)
    assert "06 Rechnungen & Belege/Übersicht" not in store.tables
    assert "NICHT GEWÄHLT: 1 Mails (privat/rechnungen)" in render_report(result, store.location)


def test_disabled_group_skips_all_its_categories(tmp_path, make_mail):
    rules = _default_rules_edited(tmp_path, "[groups.bewerbung]\n", "[groups.bewerbung]\nenabled = false\n")
    assert not rules.is_selected("bewerbung/einladung") and not rules.is_selected("bewerbung/sonstiges")
    assert rules.is_selected("privat/rechnungen") and rules.is_selected("unklar")
    result = run(_mails(make_mail), RuleClassifier(rules), rules, MemoryStore())
    assert result.plans[0].action == "skip"


def test_report_lists_overviews_after_apply(rules, make_mail):
    store = MemoryStore()
    report = render_report(run(_mails(make_mail), RuleClassifier(rules), rules, store, apply=True), store.location)
    assert "ÜBERSICHTEN:\n  = 00 Eingang/Übersicht\n  = 06 Rechnungen & Belege/Übersicht" in report
