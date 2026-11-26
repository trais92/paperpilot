"""Pipeline: abrufen -> klassifizieren -> Duplikate pruefen -> planen -> (nach Freigabe) ausfuehren.

Planen und Ausfuehren sind getrennt: ohne --apply wird nur der Plan gezeigt
(Human-in-the-loop). Geloescht wird nie etwas.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .classify import UNCLEAR, Classifier
from .config import Rules
from .deadlines import extract_deadlines
from .models import Mail, MailPlan, PlannedFile
from .naming import build_filename, company_from_mail
from .store import LocalStore, sha256, update_deadlines, update_tracker


def mail_as_markdown(mail: Mail) -> bytes:
    att = "".join(f"\n- {a.filename}" for a in mail.attachments) or " keine"
    return (
        f"# {mail.subject}\n\n"
        f"- Von: {mail.sender}\n- Datum: {mail.date:%Y-%m-%d %H:%M}\n- Anhänge:{att}\n\n---\n\n{mail.body}\n"
    ).encode()


def plan_mail(mail: Mail, classifier: Classifier, rules: Rules, store: LocalStore, seen: set[str]) -> MailPlan:
    c = classifier.classify(mail)
    cat = rules.category(c.label)
    company = company_from_mail(mail, rules.generic_domains)
    p = MailPlan(mail=mail, classification=c, action="file", company=company)

    if cat is not None and cat.action == "ignore":
        p.action = "ignore"
        return p

    if c.label == UNCLEAR:
        p.action = "review"
        folder = rules.review_folder
    else:
        folder = rules.folder_for(c.label).format(company=company, year=mail.date.year)

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
    p.notify = c.label in rules.notify_on or p.action == "review"
    return p


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
    store: LocalStore,
    apply: bool = False,
) -> RunResult:
    seen: set[str] = set()
    plans = [plan_mail(m, classifier, rules, store, seen) for m in sorted(mails, key=lambda m: m.date)]
    result = RunResult(plans=plans)
    if not apply:
        return result

    all_deadlines = []
    for p in plans:
        if p.action not in ("file", "review"):
            continue
        for f in p.files:
            store.write_file(f.path, f.content)
        all_deadlines += p.deadlines
        if p.classification.group in rules.groups:
            frist = f" · Frist {p.deadlines[0].date:%Y-%m-%d}" if p.deadlines else ""
            note = f"NEU {p.mail.date:%Y-%m-%d} · {p.classification.subtype} · {p.mail.subject}{frist}"
            update_tracker(
                store.root / rules.tracker, p.company, p.classification.subtype, p.mail.date, p.mail.subject, note
            )
    if all_deadlines:
        update_deadlines(store.root / "Fristen", all_deadlines)
    newest = max((p.mail.date for p in plans), default=None)
    store.save(newest)
    result.applied = True
    return result


def render_report(result: RunResult, root: Path, now: datetime | None = None) -> str:
    now = now or datetime.now()
    filed, review = result.by_action("file"), result.by_action("review")
    ignored, dup = result.by_action("ignore"), result.by_action("duplicate")
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
    deadlines = [d for p in result.plans for d in p.deadlines]
    if deadlines:
        lines.append("\nFRISTEN & TERMINE:")
        for d in sorted(deadlines, key=lambda d: d.date):
            when = f"{d.date:%d.%m.%Y %H:%M}" if d.has_time else f"{d.date:%d.%m.%Y}"
            lines.append(f"  • {when:<16} {d.title}")
    if ignored:
        lines.append(f"\nIGNORIERT: {len(ignored)} Werbe-/Alert-Mails")
    if result.applied:
        lines.append(f"\nAblage: {root.resolve()}")
    return "\n".join(line for line in lines if line is not None)
