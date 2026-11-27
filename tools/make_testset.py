"""Erzeugt das Testset mit Angaben `src/paperpilot_ops/data/testset.jsonl` (Roadmap 5).

Alle Mails sind erfunden: Firmen, Personen und Beträge entstehen aus festen Listen und einem
festen Zufallsstartwert, Absender nutzen `.example`-Domains. Jede Vorlage steht für eine andere
Formulierung; die Angaben (Betrag, Belegdatum, Nummer, Frist) werden beim Erzeugen in Text oder
PDF-Anhang eingesetzt, deshalb stimmen die erwarteten Werte immer mit dem Inhalt überein.

Aufteilung: Jede dritte Vorlage einer Kategorie gehört komplett zu `holdout`. So prüft das
Holdout-Set Formulierungen, die beim Entwickeln (auf `dev`) nie zu sehen waren (Regel 9).

    python tools/make_testset.py            # schreibt die Datei neu
    python tools/make_testset.py --check    # Exit-Code 1, wenn die Datei nicht dem Generator entspricht
"""

from __future__ import annotations

import argparse
import base64
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "paperpilot_ops" / "data" / "testset.jsonl"
PER_LABEL = 16
SEED = 2026

FIRMEN = [
    ("Nordlicht Software", "nordlicht-software"),
    ("Kranich Logistik", "kranich-logistik"),
    ("Bergwerk Analytics", "bergwerk-analytics"),
    ("Seewind Energie", "seewind-energie"),
    ("Lindenhof Medien", "lindenhof-medien"),
    ("Fjordtech", "fjordtech"),
    ("Alpenblick IT", "alpenblick-it"),
    ("Hafenkante Consulting", "hafenkante"),
    ("Morgenrot Bau", "morgenrot-bau"),
    ("Silberfluss Pharma", "silberfluss"),
]
VERSORGER = [
    ("Stadtwerke Musterstadt", "stadtwerke-musterstadt"),
    ("Funkwelle Mobil", "funkwelle"),
    ("Glasfaser Nord", "glasfaser-nord"),
    ("Strompilot", "strompilot"),
    ("Wasserwerk Talheim", "wasserwerk-talheim"),
]
VERSICHERER = [("Schutzbrief Versicherung", "schutzbrief"), ("Lotsen Assekuranz", "lotsen-assekuranz")]
BANKEN = [("Kontor Bank", "kontorbank"), ("Sparhafen", "sparhafen"), ("Depotwerk", "depotwerk")]
VERMIETER = [("Hausverwaltung Ahornweg", "hv-ahornweg"), ("Wohnbau Lerchenfeld", "wohnbau-lerchenfeld")]
SHOPS = [("Modehaus Nord", "modehaus-nord"), ("Technikwelt", "technikwelt"), ("Gartenparadies", "gartenparadies")]
PORTALE = [("Jobportal", "jobportal"), ("Stellenblick", "stellenblick")]
PERSONEN = ["Sam", "Mira", "Jona", "Lea", "Tarek", "Ida", "Noah", "Ella"]
NACHNAMEN = ["Brandt", "Okafor", "Lindqvist", "Yilmaz", "Hartmann", "Novak", "Petersen"]
STELLEN = ["Projektmanager", "Junior Data Analyst", "PMO Analyst", "Projektkoordinatorin", "Product Owner"]


@dataclass(frozen=True)
class Template:
    subject: str
    body: str
    sender: str  # Platzhalter {name}, {domain}
    pool: str  # aus welcher Liste die Firma stammt
    fields: tuple[str, ...] = ()  # welche Angaben im Inhalt stehen
    pdf: str = ""  # "" kein Anhang, sonst Text des PDFs (mit Platzhaltern) oder "SCAN"
    label: str = ""  # abweichendes erwartetes Label (z. B. Scan -> unklar)


T = Template
TEMPLATES: dict[str, list[Template]] = {
    "bewerbung/eingangsbestaetigung": [
        T(
            "Eingangsbestätigung Ihrer Bewerbung",
            "Guten Tag,\n\nvielen Dank für Ihre Bewerbung als {stelle}. Ihre Unterlagen sind vollständig bei uns eingegangen. Wir prüfen sie sorgfältig und melden uns innerhalb von zwei Wochen.\n\nFreundliche Grüße\nIhr Recruiting-Team",
            "Recruiting <jobs@{domain}.example>",
            "firma",
        ),
        T(
            "Danke für deine Bewerbung!",
            "Hi {person},\n\nschön, dass du dich als {stelle} bei uns beworben hast. Deine Unterlagen sind angekommen. Wir schauen sie uns in Ruhe an und geben dir bald Bescheid.\n\nViele Grüße\nPeople Team {name}",
            "People Team <noreply@karriere.{domain}.example>",
            "firma",
        ),
        T(
            "Ihre Unterlagen: {stelle}",
            "Sehr geehrte Damen und Herren,\n\nhiermit bestätigen wir den Erhalt Ihrer Unterlagen für die Position {stelle} (Kennziffer {nr}). Bitte sehen Sie von Rückfragen zum Stand ab, wir kommen auf Sie zu.\n\nMit freundlichen Grüßen\n{name}",
            "{name} Personal <bewerbung@{domain}.example>",
            "firma",
        ),
    ],
    "bewerbung/einladung": [
        T(
            "Einladung zum Vorstellungsgespräch",
            "Guten Tag,\n\nIhre Unterlagen haben uns überzeugt. Wir möchten Sie gern am {termin} um {uhr} Uhr zu einem persönlichen Gespräch einladen. Bitte bestätigen Sie den Termin bis {frist}.\n\nFreundliche Grüße\n{person} {nachname}",
            "{person} {nachname} <{person_l}@{domain}.example>",
            "firma",
            ("due_date",),
        ),
        T(
            "Kennenlernen per Video am {termin}?",
            "Hallo {person},\n\nwir würden dich gern besser kennenlernen. Passt dir ein Videocall am {termin} um {uhr} Uhr? Den Link schicken wir nach deiner Zusage.\n\nBis bald\nTeam {name}",
            "Team {name} <talent@{domain}.example>",
            "firma",
        ),
        T(
            "Nächster Schritt: Gespräch mit der Fachabteilung",
            "Sehr geehrte/r Bewerber/in,\n\nfür die Stelle {stelle} laden wir Sie zum zweiten Gespräch mit der Fachabteilung ein. Termin: {termin}, {uhr} Uhr, an unserem Standort. Antworten Sie bitte bis spätestens {frist}.\n\nMit freundlichen Grüßen\n{name}",
            "{name} HR <hr@{domain}.example>",
            "firma",
            ("due_date",),
        ),
    ],
    "bewerbung/rueckfrage": [
        T(
            "Rückfrage zu Ihrer Bewerbung",
            "Guten Tag,\n\nzu Ihrer Bewerbung als {stelle} fehlen uns noch Ihre Arbeitszeugnisse. Könnten Sie diese bis {frist} nachreichen?\n\nVielen Dank\n{person} {nachname}",
            "{person} {nachname} <{person_l}@{domain}.example>",
            "firma",
            ("due_date",),
        ),
        T(
            "Kurze Frage zu Ihrer Verfügbarkeit",
            "Hallo,\n\nab wann könnten Sie bei uns starten, und wie ist Ihre Gehaltsvorstellung? Eine kurze Antwort bis {frist} würde uns sehr helfen.\n\nBeste Grüße\n{name}",
            "{name} <recruiting@{domain}.example>",
            "firma",
            ("due_date",),
        ),
        T(
            "Unterlagen unvollständig",
            "Sehr geehrte Damen und Herren,\n\nleider ist Ihr Lebenslauf als Datei beschädigt angekommen. Bitte senden Sie ihn uns erneut zu, damit wir Ihre Bewerbung (Kennziffer {nr}) weiter bearbeiten können.\n\nFreundliche Grüße\n{name}",
            "{name} Personal <bewerbung@{domain}.example>",
            "firma",
        ),
    ],
    "bewerbung/absage": [
        T(
            "Ihre Bewerbung bei {name}",
            "Guten Tag,\n\nvielen Dank für Ihr Interesse. Leider müssen wir Ihnen mitteilen, dass wir uns für eine andere Kandidatin entschieden haben. Wir wünschen Ihnen viel Erfolg.\n\nFreundliche Grüße\n{name}",
            "{name} <jobs@{domain}.example>",
            "firma",
        ),
        T(
            "Rückmeldung zur Position {stelle}",
            "Hallo {person},\n\nwir haben uns die Entscheidung nicht leicht gemacht. Für die Position {stelle} setzen wir den Prozess mit anderen Bewerbenden fort. Gern behalten wir deine Daten für künftige Stellen.\n\nAlles Gute\nTeam {name}",
            "Team {name} <talent@{domain}.example>",
            "firma",
        ),
        T(
            "Stand Ihrer Bewerbung",
            "Sehr geehrte Damen und Herren,\n\nnach eingehender Prüfung können wir Ihre Bewerbung (Kennziffer {nr}) nicht weiter berücksichtigen. Ihre Unterlagen löschen wir nach Ablauf der gesetzlichen Fristen.\n\nMit freundlichen Grüßen\n{name}",
            "{name} HR <hr@{domain}.example>",
            "firma",
        ),
    ],
    "bewerbung/angebot": [
        T(
            "Ihr Vertragsangebot",
            "Guten Tag,\n\nwir freuen uns, Ihnen die Stelle als {stelle} anbieten zu können. Den Vertragsentwurf finden Sie im Anhang. Bitte geben Sie uns bis {frist} Bescheid.\n\nHerzliche Grüße\n{person} {nachname}",
            "{person} {nachname} <{person_l}@{domain}.example>",
            "firma",
            ("due_date",),
        ),
        T(
            "Wir möchten dich an Bord holen!",
            "Hallo {person},\n\nherzlichen Glückwunsch: Wir möchten dir die Rolle als {stelle} anbieten. Startdatum und Konditionen stehen im Angebot. Melde dich gern bei Fragen.\n\nViele Grüße\nTeam {name}",
            "Team {name} <talent@{domain}.example>",
            "firma",
        ),
        T(
            "Zusage und nächste Schritte",
            "Sehr geehrte/r Bewerber/in,\n\nwir sagen Ihnen gern zu und senden Ihnen den Arbeitsvertrag für die Position {stelle} zur Unterschrift. Bitte unterschreiben Sie ihn bis {frist}.\n\nMit freundlichen Grüßen\n{name}",
            "{name} HR <hr@{domain}.example>",
            "firma",
            ("due_date",),
        ),
    ],
    "privat/rechnungen": [
        T(
            "Ihre Rechnung {nr}",
            "Guten Tag,\n\nanbei erhalten Sie Ihre Rechnung {nr} vom {beleg} über {betrag}. Bitte überweisen Sie den Betrag bis {frist}.\n\nIhr {name}",
            "{name} <rechnung@{domain}.example>",
            "versorger",
            ("amount", "reference", "document_date", "due_date"),
        ),
        T(
            "Rechnung für {monat}",
            "Hallo,\n\ndeine Rechnung für {monat} ist da. Du findest sie als PDF im Anhang.\n\nDein Team von {name}",
            "{name} <service@{domain}.example>",
            "versorger",
            ("amount", "reference", "document_date", "due_date"),
            "Rechnung Nr. {nr}\nRechnungsdatum: {beleg}\nGesamtbetrag: {betrag}\nZahlbar bis {frist} ohne Abzug.",
        ),
        T(
            "Zahlungserinnerung",
            "Sehr geehrte Kundin, sehr geehrter Kunde,\n\nfür die Rechnung {nr} konnten wir noch keinen Zahlungseingang feststellen. Offen sind {betrag}. Bitte gleichen Sie den Betrag bis {frist} aus.\n\nMit freundlichen Grüßen\n{name}",
            "{name} Buchhaltung <buchhaltung@{domain}.example>",
            "versorger",
            ("amount", "reference", "due_date"),
        ),
        T(
            "Beleg zu Ihrer Bestellung",
            "Vielen Dank für Ihren Einkauf. Ihren Beleg finden Sie im Anhang.",
            "{name} <beleg@{domain}.example>",
            "versorger",
            (),
            "SCAN",
            "unklar",
        ),
    ],
    "privat/versicherungen": [
        T(
            "Ihr Versicherungsschein",
            "Guten Tag,\n\nanbei erhalten Sie den Versicherungsschein zu Ihrer Hausratversicherung, Vertragsnummer {nr}. Der Jahresbeitrag beträgt {betrag}.\n\nIhre {name}",
            "{name} <kundenservice@{domain}.example>",
            "versicherer",
            ("amount", "reference"),
        ),
        T(
            "Beitragsanpassung ab {monat}",
            "Sehr geehrte Kundin, sehr geehrter Kunde,\n\nzum {beleg} passen wir den Beitrag Ihrer Haftpflichtversicherung an. Details stehen im beigefügten Schreiben.\n\nMit freundlichen Grüßen\n{name}",
            "{name} <post@{domain}.example>",
            "versicherer",
            ("amount", "reference", "document_date"),
            "Schreiben vom {beleg}\nVertrag {nr}\nNeuer Jahresbeitrag: {betrag}",
        ),
        T(
            "Schadenmeldung eingegangen",
            "Hallo,\n\nIhre Schadenmeldung zum Vorgang {nr} ist bei uns eingegangen. Bitte senden Sie uns bis {frist} Fotos des Schadens.\n\nIhre {name}",
            "{name} Schaden <schaden@{domain}.example>",
            "versicherer",
            ("reference", "due_date"),
        ),
    ],
    "privat/vertraege": [
        T(
            "Bestätigung Ihrer Vertragsänderung",
            "Guten Tag,\n\nwir bestätigen die Änderung Ihres Tarifs zum {beleg}. Ihre Kundennummer lautet {nr}, der monatliche Preis {betrag}.\n\nIhr {name}",
            "{name} <vertrag@{domain}.example>",
            "versorger",
            ("amount", "reference", "document_date"),
        ),
        T(
            "Ihre Kündigung",
            "Sehr geehrte Kundin, sehr geehrter Kunde,\n\nwir bestätigen den Eingang Ihrer Kündigung. Der Vertrag {nr} endet zum {frist}.\n\nMit freundlichen Grüßen\n{name}",
            "{name} Kundenservice <service@{domain}.example>",
            "versorger",
            ("reference", "due_date"),
        ),
        T(
            "Willkommen bei {name}",
            "Hallo {person},\n\nschön, dass du dabei bist. Die Vertragsunterlagen findest du im Anhang. Bitte prüfe sie in Ruhe.\n\nDein Team von {name}",
            "{name} <willkommen@{domain}.example>",
            "versorger",
            ("amount", "reference", "document_date"),
            "Auftragsbestätigung vom {beleg}\nKundennummer {nr}\nMonatlicher Grundpreis {betrag}",
        ),
    ],
    "privat/steuern": [
        T(
            "Ihr Steuerbescheid ist abrufbar",
            "Guten Tag,\n\nder Bescheid für das Jahr 2025 zur Steuernummer {nr} steht in Ihrem Postfach bereit. Einspruch ist bis {frist} möglich.\n\nIhr Finanzamt Musterstadt",
            "Finanzamt Musterstadt <noreply@finanzamt-musterstadt.example>",
            "fest",
            ("reference", "due_date"),
        ),
        T(
            "Erinnerung: Steuererklärung",
            "Hallo,\n\ndenk daran, deine Unterlagen für die Einkommensteuererklärung bis {frist} bei uns einzureichen.\n\nViele Grüße\nSteuerbüro {nachname}",
            "Steuerbüro {nachname} <kanzlei@steuer-{nachname_l}.example>",
            "fest",
            ("due_date",),
        ),
        T(
            "Festsetzung Grundsteuer",
            "Sehr geehrte Damen und Herren,\n\nanbei der Bescheid über die Grundsteuer. Bitte beachten Sie die Fälligkeit.\n\nStadtkasse Musterstadt",
            "Stadtkasse <stadtkasse@musterstadt.example>",
            "fest",
            ("amount", "reference", "document_date", "due_date"),
            "Bescheid vom {beleg}\nAktenzeichen {nr}\nFestgesetzte Grundsteuer: {betrag}\nFällig am {frist}",
        ),
    ],
    "privat/wohnen": [
        T(
            "Nebenkostenabrechnung",
            "Guten Tag,\n\nanbei die Nebenkostenabrechnung für Ihre Wohnung. Es ergibt sich eine Nachzahlung von {betrag}, fällig bis {frist}.\n\nIhre {name}",
            "{name} <verwaltung@{domain}.example>",
            "vermieter",
            ("amount", "due_date"),
        ),
        T(
            "Ankündigung Wartungsarbeiten",
            "Liebe Mieterinnen und Mieter,\n\nam {termin} werden die Rauchmelder im Haus geprüft. Bitte ermöglichen Sie den Zugang zwischen 8 und 12 Uhr.\n\nIhre {name}",
            "{name} <info@{domain}.example>",
            "vermieter",
        ),
        T(
            "Mieterhöhung zum {monat}",
            "Sehr geehrte Mieterin, sehr geehrter Mieter,\n\ndas beigefügte Schreiben erläutert die Anpassung Ihrer Miete. Bitte stimmen Sie bis {frist} zu.\n\nMit freundlichen Grüßen\n{name}",
            "{name} <mietverwaltung@{domain}.example>",
            "vermieter",
            ("amount", "reference", "document_date", "due_date"),
            "Schreiben vom {beleg}\nMietvertrag {nr}\nNeue Grundmiete: {betrag}\nZustimmung erbeten bis {frist}",
        ),
    ],
    "privat/finanzen": [
        T(
            "Ihr Kontoauszug ist da",
            "Guten Tag,\n\nIhr Kontoauszug für {monat} liegt im Online-Banking bereit.\n\nIhre {name}",
            "{name} <service@{domain}.example>",
            "bank",
        ),
        T(
            "Wertpapierabrechnung Kauf",
            "Hallo,\n\nIhre Order {nr} wurde ausgeführt. Kurswert inklusive Gebühren: {betrag}.\n\nIhr {name}",
            "{name} <depot@{domain}.example>",
            "bank",
            ("amount", "reference"),
        ),
        T(
            "Änderung der Kontoführungsentgelte",
            "Sehr geehrte Kundin, sehr geehrter Kunde,\n\nab dem {beleg} ändern sich unsere Preise. Widersprechen können Sie bis {frist}.\n\nIhre {name}",
            "{name} <info@{domain}.example>",
            "bank",
            ("due_date",),
        ),
    ],
    "werbung": [
        T(
            "Nur heute: 30 % auf alles",
            "Jetzt zugreifen! Nur heute 30 % Rabatt auf das gesamte Sortiment. Newsletter abbestellen? Hier klicken.",
            "{name} <newsletter@{domain}.example>",
            "shop",
        ),
        T(
            "{anzahl} neue Jobs für dich",
            "Diese Stellen passen zu deinem Profil: {stelle} und weitere. Jetzt bewerben! Benachrichtigungen verwalten oder abmelden.",
            "{name} <jobalert@{domain}.example>",
            "portal",
        ),
        T(
            "Dein Gutschein wartet",
            "Nur für kurze Zeit: Sichere dir 10 Euro Gutschein ab 50 Euro Einkauf. Wenn du keine E-Mails mehr möchtest, kannst du dich hier abmelden.",
            "{name} <angebote@{domain}.example>",
            "shop",
        ),
    ],
    "unklar": [
        T(
            "Grillen am Samstag?",
            "Hey, hast du Samstag Zeit? Wir grillen bei uns im Garten, bring gern was mit.",
            "{person} <{person_l}@example.com>",
            "fest",
        ),
        T(
            "Protokoll der Vereinssitzung",
            "Liebe Mitglieder, anbei das Protokoll der letzten Sitzung. Die nächste findet im Januar statt.",
            "Vorstand <vorstand@sportverein-musterstadt.example>",
            "fest",
        ),
        T(
            "Fotos vom Wochenende",
            "Hier sind endlich die Fotos. War richtig schön mit euch!",
            "{person} <{person_l}@example.com>",
            "fest",
        ),
    ],
}

POOLS = {
    "firma": FIRMEN,
    "versorger": VERSORGER,
    "versicherer": VERSICHERER,
    "bank": BANKEN,
    "vermieter": VERMIETER,
    "shop": SHOPS,
    "portal": PORTALE,
    "fest": [("", "")],
}
MONATE = ["Oktober 2026", "November 2026", "Dezember 2026", "Januar 2027"]


def _de_amount(value: float) -> str:
    whole, cents = f"{value:.2f}".split(".")
    return f"{whole},{cents} €" if value < 1000 else f"{int(whole):,}".replace(",", ".") + f",{cents} €"


def minimal_pdf(text: str | None) -> bytes:
    """Ein gültiges einseitiges PDF; `None` ergibt eine Seite ohne Text (wie ein Scan)."""
    lines = [] if text is None else text.splitlines()
    ops = "".join(
        f"BT /F1 11 Tf 72 {740 - 16 * i} Td ({line.replace('(', '[').replace(')', ']')}) Tj ET\n"
        for i, line in enumerate(lines)
    )
    stream = ops.encode("cp1252")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def _sample(rng: random.Random, label: str, index: int, template_no: int, template: Template) -> dict[str, object]:
    name, domain = rng.choice(POOLS[template.pool])
    person, nachname = rng.choice(PERSONEN), rng.choice(NACHNAMEN)
    mail_date = datetime(2026, 11, 2, 8) + timedelta(days=rng.randrange(25), minutes=rng.randrange(600))
    beleg = (mail_date - timedelta(days=rng.randrange(1, 6))).date()
    frist = (mail_date + timedelta(days=rng.randrange(7, 30))).date()
    termin = (mail_date + timedelta(days=rng.randrange(3, 14))).date()
    amount = round(rng.uniform(8, 1800), 2)
    nr = f"{rng.choice(['RE', 'KD', 'VN', 'AZ', 'NR'])}-{rng.randrange(2025, 2027)}-{rng.randrange(1000, 99999)}"
    slots = {
        "name": name,
        "domain": domain,
        "person": person,
        "person_l": person.lower(),
        "nachname": nachname,
        "nachname_l": nachname.lower(),
        "stelle": rng.choice(STELLEN),
        "betrag": _de_amount(amount),
        "nr": nr,
        "beleg": f"{beleg:%d.%m.%Y}",
        "frist": f"{frist:%d.%m.%Y}",
        "termin": f"{termin:%d.%m.%Y}",
        "uhr": rng.choice(["9:30", "10:00", "14:00", "15:30"]),
        "monat": rng.choice(MONATE),
        "anzahl": str(rng.randrange(3, 25)),
    }
    gold = {"amount": f"{amount:.2f} EUR", "document_date": beleg.isoformat(), "reference": nr}
    gold["due_date"] = frist.isoformat()
    sample: dict[str, object] = {
        "id": f"t{index:03d}",
        "date": f"{mail_date:%Y-%m-%dT%H:%M}",
        "from": template.sender.format(**slots),
        "subject": template.subject.format(**slots),
        "body": template.body.format(**slots),
        "label": template.label or label,
        "fields": {key: gold[key] for key in template.fields},
        "split": "holdout" if template_no % 3 == 2 else "dev",
        "template": f"{label}#{template_no}",
    }
    if template.pdf:
        content = minimal_pdf(None if template.pdf == "SCAN" else template.pdf.format(**slots))
        sample["attachments"] = [{"filename": "Dokument.pdf", "base64": base64.b64encode(content).decode("ascii")}]
    return sample


def build() -> list[dict[str, object]]:
    rng = random.Random(SEED)
    samples: list[dict[str, object]] = []
    for label, templates in TEMPLATES.items():
        for i in range(PER_LABEL):
            template_no = i % len(templates)
            samples.append(_sample(rng, label, len(samples) + 1, template_no, templates[template_no]))
    return samples


def render(samples: list[dict[str, object]]) -> str:
    return "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in samples)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="nur prüfen, ob die Datei aktuell ist")
    args = parser.parse_args(argv)
    text = render(build())
    if args.check:
        current = OUT.read_text("utf-8") if OUT.exists() else ""
        if current != text:
            print(f"{OUT} entspricht nicht dem Generator. Neu erzeugen: python tools/make_testset.py")
            return 1
        print(f"{OUT} ist aktuell.")
        return 0
    OUT.write_text(text, "utf-8")
    print(f"{len(text.splitlines())} Mails geschrieben: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
