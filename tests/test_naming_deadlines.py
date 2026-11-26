from datetime import datetime

from personal_ops.deadlines import extract_deadlines, to_ics
from personal_ops.naming import build_filename, company_from_mail, slug


def test_slug_removes_umlauts_stopwords_and_gender():
    assert slug("Einladung zum Interview: Projektmanager (m/w/d)") == "Einladung-Interview-Projektmanager"
    assert slug("Rückfrage zur Verfügbarkeit") == "Rueckfrage-Verfuegbarkeit"


def test_filename_convention():
    name = build_filename(datetime(2026, 11, 20), "Hansa-Versicherung", "AW: Ihre Police", "PDF")
    assert name == "2026-11-20_Hansa-Versicherung_Police.pdf"


def test_company_from_domain_and_freemail(make_mail, rules):
    assert (
        company_from_mail(make_mail(sender="HR <jobs@karriere.nordlicht-software.example>"), rules.generic_domains)
        == "Nordlicht-Software"
    )
    assert company_from_mail(make_mail(sender="Sam Beispiel <sam@example.com>"), rules.generic_domains) == "Sam-Beispiel"


def test_deadline_with_time_and_without_year(make_mail):
    m = make_mail(body="Wir laden Sie am 03.12.2026 um 11:00 Uhr ein. Bitte antworten Sie bis 28.11.")
    ds = extract_deadlines(m)
    assert [(d.date, d.has_time) for d in ds] == [(datetime(2026, 11, 28), False), (datetime(2026, 12, 3, 11, 0), True)]


def test_date_without_year_in_past_rolls_to_next_year(make_mail):
    ds = extract_deadlines(make_mail(body="Frist ist der 15.01.", date="2026-11-20T10:00"))
    assert ds[0].date == datetime(2027, 1, 15)


def test_no_trigger_no_deadline(make_mail):
    assert extract_deadlines(make_mail(body="Rechnung vom 01.12.2026 anbei.")) == []


def test_ics_contains_events(make_mail):
    ics = to_ics(extract_deadlines(make_mail(subject="Interview", body="Termin am 03.12.2026 um 11:00 Uhr.")))
    assert "DTSTART:20261203T110000" in ics and ics.count("BEGIN:VEVENT") == 1
