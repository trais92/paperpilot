"""Pipeline: abrufen -> klassifizieren -> Duplikate prüfen -> planen -> (nach Freigabe) ausführen.

Planen und Ausführen sind getrennt: ohne --apply wird nur der Plan gezeigt
(Human-in-the-loop). Gelöscht wird nie etwas.

Aktionen pro Mail: `file` (ablegen), `review` (unklar, in den Eingang), `ignore` (Werbung),
`duplicate` (schon abgelegt), `skip` (Kategorie erkannt, aber nicht zum Sortieren gewählt).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from .classify import UNCLEAR
from .config import Rules
from .deadlines import extract_deadlines
from .models import Deadline, Fields, Mail, MailPlan, PlannedFile
from .naming import build_filename, company_from_mail
from .ports import Classifier, StorageTarget
from .store import sha256, update_deadlines, update_tracker


def mail_as_markdown(mail: Mail) -> bytes:
    att = "".join(f"\n- {a.filename}" for a in mail.attachments) or " keine"
    return (
        f"# {mail.subject}\n\n"
        f"- Von: {mail.sender}\n- Datum: {mail.date:%Y-%m-%d %H:%M}\n- Anhänge:{att}\n\n---\n\n{mail.body}\n"
    ).encode()


def plan_mail(mail: Mail, classifier: Classifier, rules: Rules, store: StorageTarget, seen: set[str]) -> MailPlan:
    """Entscheidet, was mit einer Mail passiert. Rein lesend: schreibt nichts in `store`."""
    c = classifier.classify(mail)
    cat = rules.category(c.label)
    company = company_from_mail(mail, rules.generic_domains)
    p = MailPlan(mail=mail, classification=c, action="file", company=company)

    if cat is not None and cat.action == "ignore":
        p.action = "ignore"
        return p
    if not rules.is_selected(c.label):
        p.action = "skip"
        return p

    if c.label == UNCLEAR:
        p.action = "review"
        folder = rules.review_folder
    else:
        folder = rules.folder_for(c.label).format(company=company, year=mail.date.year)

    p.table = rules.table_for(rules.review_folder if p.action == "review" else rules.folder_for(c.label))
    body = mail_as_markdown(mail)
    p.files.append(
        PlannedFile(f"{folder}/{build_filename(mail.date, company, mail.subject, 'md')}", body, sha256(body))
    )
    for a in mail.attachments:
        stem, _, ext = a.filename.rpartition(".")
        name = build_filename(mail.date, company, stem or a.filename, ext or "bin")
        p.files.append(PlannedFile(f"{folder}/{name}", a.content, sha256(a.content)))

    if all(store.has(f.sha256) or f.sha256 in seen for f in p.files):
        p.action = "duplicate"
        p.files = []
        return p
    seen.update(f.sha256 for f in p.files)

    p.deadlines = extract_deadlines(mail)
    due = c.fields.due_date  # von der KI erkannte Frist, z. B. aus dem PDF-Anhang
    if due and all(f"{d.date:%Y-%m-%d}" != due for d in p.deadlines):
        p.deadlines.append(Deadline(datetime.fromisoformat(due), False, "Frist laut KI", mail.id, mail.subject))
        p.deadlines.sort(key=lambda d: d.date)
    p.notify = c.label in rules.notify_on or p.action == "review"
    return p


OVERVIEW_COLUMNS = (
    "Datum",
    "Absender",
    "Betreff",
    "Kategorie",
    "Betrag",
    "Belegdatum",
    "Nummer",
    "Frist",
    "Dateien",
    "Begründung",
    "Mail-ID",
)


def overview_row(plan: MailPlan, written_paths: list[str]) -> dict[str, str]:
    """Eine Zeile der Übersichtstabelle. `written_paths` sind die tatsächlich verwendeten Pfade."""
    deadline = plan.deadlines[0] if plan.deadlines else None
    fields = plan.classification.fields
    return {
        "Datum": f"{plan.mail.date:%Y-%m-%d}",
        "Absender": plan.company,
        "Betreff": plan.mail.subject,
        "Kategorie": plan.classification.label,
        "Betrag": fields.amount,
        "Belegdatum": fields.document_date,
        "Nummer": fields.reference,
        "Frist": fields.due_date or (f"{deadline.date:%Y-%m-%d}" if deadline else ""),
        "Dateien": " | ".join(written_paths),
        "Begründung": plan.classification.reason,
        "Mail-ID": plan.mail.id,
    }


def describe_fields(fields: Fields) -> str:
    """Kurzform für Bericht und Browser, z. B. `49.90 EUR · Nr. R-1 · Frist 2026-12-15`."""
    parts = [
        fields.amount,
        f"Nr. {fields.reference}" if fields.reference else "",
        f"vom {fields.document_date}" if fields.document_date else "",
        f"Frist {fields.due_date}" if fields.due_date else "",
    ]
    return " · ".join(part for part in parts if part)


@dataclass
class RunResult:
    plans: list[MailPlan] = field(default_factory=list)
    applied: bool = False

    def by_action(self, action: str) -> list[MailPlan]:
        return [p for p in self.plans if p.action == action]


def run(
    mails: Iterable[Mail],
    classifier: Classifier,
    rules: Rules,
    store: StorageTarget,
    apply: bool = False,
) -> RunResult:
    """Plant alle Mails und führt den Plan nur bei `apply=True` aus (Trockenlauf ist Standard)."""
    seen: set[str] = set()
    plans = [plan_mail(m, classifier, rules, store, seen) for m in sorted(mails, key=lambda m: m.date)]
    result = RunResult(plans=plans)
    if not apply:
        return result

    all_deadlines: list[Deadline] = []
    overview: dict[str, list[dict[str, str]]] = {}
    for p in plans:
        if p.action not in ("file", "review"):
            continue
        written = [store.write_file(f.path, f.content) for f in p.files]
        overview.setdefault(p.table, []).append(overview_row(p, written))
        all_deadlines += p.deadlines
        if p.classification.group in rules.groups:
            frist = f" · Frist {p.deadlines[0].date:%Y-%m-%d}" if p.deadlines else ""
            note = f"NEU {p.mail.date:%Y-%m-%d} · {p.classification.subtype} · {p.mail.subject}{frist}"
            update_tracker(store, rules.tracker, p.company, p.classification.subtype, p.mail.date, p.mail.subject, note)
    for table, rows in overview.items():  # eine Schreiboperation pro Tabelle
        store.append_rows(table, OVERVIEW_COLUMNS, rows)
    if all_deadlines:
        update_deadlines(store, "Fristen", all_deadlines)
    newest = max((p.mail.date for p in plans), default=None)
    store.save(newest)
    result.applied = True
    return result


def render_report(result: RunResult, location: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    filed, review = result.by_action("file"), result.by_action("review")
    ignored, dup = result.by_action("ignore"), result.by_action("duplicate")
    skipped = result.by_action("skip")
    notify = [p for p in result.plans if p.notify and p.action == "file"]
    lines = [
        f"Lauf {now:%Y-%m-%d %H:%M} · {len(result.plans)} Mails · "
        f"{len(filed)} ablegen · {len(review)} zur Prüfung · {len(ignored)} Werbung · {len(dup)} Duplikate",
        None if result.applied else "TROCKENLAUF: nichts wurde geschrieben. Mit --apply ausführen.",
    ]
    if notify:
        lines.append("\nMELDEN (Handlung nötig):")
        for p in notify:
            frist = f" -> {p.deadlines[0].date:%d.%m.%Y %H:%M}".replace(" 00:00", "") if p.deadlines else ""
            lines.append(f"  ! {p.classification.label:<30} {p.company}: {p.mail.subject}{frist}")
    if filed:
        lines.append("\nABLAGE:")
        for p in filed:
            for f in p.files:
                lines.append(f"  + {f.path}")
    if review:
        lines.append("\nZUR PRÜFUNG (unklar, liegt im Eingang):")
        for p in review:
            lines.append(f"  ? {p.mail.subject}  [{p.classification.reason}]")
    with_fields = [p for p in filed + review if p.classification.fields]
    if with_fields:
        lines.append("\nANGABEN:")
        for p in with_fields:
            lines.append(f"  € {describe_fields(p.classification.fields):<40} {p.mail.subject}")
    deadlines = [d for p in result.plans for d in p.deadlines]
    if deadlines:
        lines.append("\nFRISTEN & TERMINE:")
        for d in sorted(deadlines, key=lambda d: d.date):
            when = f"{d.date:%d.%m.%Y %H:%M}" if d.has_time else f"{d.date:%d.%m.%Y}"
            lines.append(f"  • {when:<16} {d.title}")
    if ignored:
        lines.append(f"\nIGNORIERT: {len(ignored)} Werbe-/Alert-Mails")
    if skipped:
        labels = sorted({p.classification.label for p in skipped})
        lines.append(f"NICHT GEWÄHLT: {len(skipped)} Mails ({', '.join(labels)}), bleiben nur im Postfach")
    tables = sorted({p.table for p in filed + review})
    if result.applied and tables:
        lines.append("\nÜBERSICHTEN:")
        lines.extend(f"  = {t}" for t in tables)
    if result.applied:
        lines.append(f"\nAblage: {location}")
    return "\n".join(line for line in lines if line is not None)
