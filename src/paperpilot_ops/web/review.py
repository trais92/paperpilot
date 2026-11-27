"""Bericht mit Freigabe: Plan zeigen, Kategorien korrigieren lassen, erst dann ausführen.

Die Seite kommt ohne JavaScript aus: ein Formular mit einer Auswahlliste pro Mail und zwei Knöpfen.
Jeder Wert aus einer Mail wird mit `html.escape` maskiert, weil Mails beliebigen Text enthalten können.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ..classify import UNCLEAR, FixedClassifier
from ..config import Rules
from ..fields import FIELD_LABELS, FIELD_NAMES, FieldError, parse_form_fields
from ..models import Classification, Mail, MailPlan
from ..pipeline import RunResult, render_report, run
from ..ports import StorageTarget
from .page import FormError, UnknownAction, layout
from .page import escape as _e

CORRECTED = "vom Menschen korrigiert"

ACTION_TEXT = {
    "file": "ablegen",
    "review": "in den Eingang (unklar)",
    "ignore": "nicht ablegen (Werbung)",
    "duplicate": "schon abgelegt",
    "skip": "nicht gewählt",
}


class ReviewError(FormError):
    """Ungültige Freigabe (falsches Token, unbekannte Kategorie). Es wurde nichts geschrieben."""


@dataclass
class ReviewSession:
    """Ein Lauf, der auf Freigabe wartet. `approve` führt genau einmal aus."""

    mails: list[Mail]
    plan: RunResult
    rules: Rules
    store: StorageTarget
    token: str
    result: RunResult | None = None
    cancelled: bool = False
    labels: list[str] = field(init=False)

    def __post_init__(self) -> None:
        self.labels = sorted({*self.rules.labels, *(f"{g}/sonstiges" for g in self.rules.groups)})

    @property
    def finished(self) -> bool:
        return self.result is not None or self.cancelled

    # -- Aktionen ------------------------------------------------------------------------------
    def submit(self, action: str, form: Mapping[str, str]) -> None:
        """Einstieg für den Server: `approve` oder `cancel`."""
        if action == "approve":
            self.approve(form)
        elif action == "cancel":
            self.cancel(form)
        else:
            raise UnknownAction(action)

    def approve(self, form: Mapping[str, str]) -> RunResult:
        """Führt den Plan mit den Korrekturen aus `form` aus (`label-<n>` und `f-<n>-<feld>` je Mail).

        Erst wird alles geprüft, dann einmal ausgeführt: Ist eine Angabe ungültig, wird nichts geschrieben.
        """
        self._check(form)
        decided = {p.mail.id: self._decision(n, p, form) for n, p in enumerate(self.plan.plans)}
        self.result = run(self.mails, FixedClassifier(decided), self.rules, self.store, apply=True)
        return self.result

    def _decision(self, n: int, p: MailPlan, form: Mapping[str, str]) -> Classification:
        before = p.classification
        label = form.get(f"label-{n}", before.label)
        if label not in self.labels:
            raise ReviewError(f"Unbekannte Kategorie: {label}")
        fields = before.fields
        prefix = f"f-{n}-"
        if any(key.startswith(prefix) for key in form):
            try:
                fields = parse_form_fields(form, prefix)
            except FieldError as exc:
                raise ReviewError(f"Mail {n + 1} ({p.mail.subject[:40]}): {exc}") from None
        if label == before.label and fields == before.fields:
            return before
        return Classification(label, 1.0 if label != before.label else before.confidence, CORRECTED, fields)

    def cancel(self, form: Mapping[str, str]) -> None:
        self._check(form)
        self.cancelled = True

    def _check(self, form: Mapping[str, str]) -> None:
        if self.finished:
            raise ReviewError("Dieser Lauf ist schon abgeschlossen.")
        if form.get("token") != self.token:
            raise ReviewError("Ungültiges Formular.")

    # -- Seiten --------------------------------------------------------------------------------
    def page(self) -> str:
        if self.result is not None:
            return self._done_page(self.result)
        if self.cancelled:
            return layout("Abgebrochen", "<p>Nichts wurde geschrieben. Das Fenster kann geschlossen werden.</p>")
        return self._plan_page()

    def _plan_page(self) -> str:
        counts = {a: len(self.plan.by_action(a)) for a in ACTION_TEXT}
        summary = " · ".join(f"{counts[a]} {text}" for a, text in ACTION_TEXT.items() if counts[a])
        rows = "\n".join(self._row(n, p) for n, p in enumerate(self.plan.plans))
        body = f"""
<p class="lead">{len(self.plan.plans)} neue Mails · {_e(summary)}</p>
<p>Noch ist nichts geschrieben. Prüfe Kategorien und Angaben, korrigiere sie bei Bedarf und gib den Lauf frei.
Ziel: <strong>{_e(self.store.location)}</strong></p>
<form method="post" action="/approve">
<input type="hidden" name="token" value="{_e(self.token)}">
<table>
<thead><tr><th>Datum</th><th>Mail</th><th>Kategorie</th><th>Angaben</th><th>Was passiert</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<div class="actions">
<button type="submit" class="primary">Freigeben und ablegen</button>
<button type="submit" formaction="/cancel">Abbrechen</button>
</div>
</form>"""
        return layout("Lauf freigeben", body)

    def _row(self, n: int, p: MailPlan) -> str:
        c = p.classification
        options = "".join(
            f'<option value="{_e(label)}"{" selected" if label == c.label else ""}>{_e(_label_text(label))}</option>'
            for label in self.labels
        )
        targets = "".join(f"<li>{_e(f.path)}</li>" for f in p.files)
        deadlines = "".join(f"<li>Frist {d.date:%d.%m.%Y}</li>" for d in p.deadlines)
        details = f"<ul>{targets}{deadlines}</ul>" if targets or deadlines else ""
        return (
            f'<tr class="{_e(p.action)}"><td>{p.mail.date:%d.%m.%Y}</td>'
            f"<td><strong>{_e(p.mail.subject)}</strong><br><small>{_e(p.mail.sender)}</small></td>"
            f'<td><select name="label-{n}" aria-label="Kategorie">{options}</select>'
            f"<br><small>{_e(c.reason)}</small></td>"
            f"<td>{self._field_inputs(n, p)}</td>"
            f"<td>{_e(ACTION_TEXT.get(p.action, p.action))}{details}</td></tr>"
        )

    def _field_inputs(self, n: int, p: MailPlan) -> str:
        """Eingabefelder für Betrag, Belegdatum, Nummer und Frist, nur bei Mails, die abgelegt werden."""
        if p.action not in ("file", "review"):
            return ""
        values = p.classification.fields
        hints = {"amount": "49.90 EUR", "document_date": "JJJJ-MM-TT", "reference": "R-123", "due_date": "JJJJ-MM-TT"}
        return "".join(
            f'<label class="field"><small>{_e(FIELD_LABELS[name])}</small>'
            f'<input type="text" name="f-{n}-{name}" value="{_e(getattr(values, name))}" '
            f'placeholder="{_e(hints[name])}"></label>'
            for name in FIELD_NAMES
        )

    def _done_page(self, result: RunResult) -> str:
        report = render_report(result, self.store.location)
        return layout("Erledigt", f"<p>Der Lauf ist ausgeführt.</p><pre>{_e(report)}</pre>")


def _label_text(label: str) -> str:
    if label == UNCLEAR:
        return "unklar (in den Eingang)"
    if label == "werbung":
        return "werbung (nicht ablegen)"
    return label
