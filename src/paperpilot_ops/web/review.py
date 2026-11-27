"""Bericht mit Freigabe: Plan zeigen, Kategorien korrigieren lassen, erst dann ausführen.

Die Seite kommt ohne JavaScript aus: ein Formular mit einer Auswahlliste pro Mail und zwei Knöpfen.
Jeder Wert aus einer Mail wird mit `html.escape` maskiert, weil Mails beliebigen Text enthalten können.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from ..classify import UNCLEAR, FixedClassifier
from ..config import Rules
from ..models import Classification, Mail, MailPlan
from ..pipeline import RunResult, render_report, run
from ..ports import StorageTarget

CORRECTED = "vom Menschen korrigiert"

ACTION_TEXT = {
    "file": "ablegen",
    "review": "in den Eingang (unklar)",
    "ignore": "nicht ablegen (Werbung)",
    "duplicate": "schon abgelegt",
    "skip": "nicht gewählt",
}


class ReviewError(ValueError):
    """Ungültige Freigabe (falsches Token, unbekannte Kategorie). Es wurde nichts geschrieben."""


@dataclass
class ReviewSession:
    """Ein Lauf, der auf Freigabe wartet. `approve` führt genau einmal aus."""

    mails: list[Mail]
    plan: RunResult
    rules: Rules
    store: StorageTarget
    token: str
    on_done: Callable[[], None] = lambda: None
    result: RunResult | None = None
    cancelled: bool = False
    labels: list[str] = field(init=False)

    def __post_init__(self) -> None:
        self.labels = sorted({*self.rules.labels, *(f"{g}/sonstiges" for g in self.rules.groups)})

    @property
    def finished(self) -> bool:
        return self.result is not None or self.cancelled

    # -- Aktionen ------------------------------------------------------------------------------
    def approve(self, form: Mapping[str, str]) -> RunResult:
        """Führt den Plan mit den Korrekturen aus `form` aus (`label-<n>` je Mail)."""
        self._check(form)
        decided: dict[str, Classification] = {}
        for n, p in enumerate(self.plan.plans):
            label = form.get(f"label-{n}", p.classification.label)
            if label not in self.labels:
                raise ReviewError(f"Unbekannte Kategorie: {label}")
            same = label == p.classification.label
            decided[p.mail.id] = p.classification if same else Classification(label, 1.0, CORRECTED)
        self.result = run(self.mails, FixedClassifier(decided), self.rules, self.store, apply=True)
        self.on_done()
        return self.result

    def cancel(self, form: Mapping[str, str]) -> None:
        self._check(form)
        self.cancelled = True
        self.on_done()

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
            return _layout("Abgebrochen", "<p>Nichts wurde geschrieben. Das Fenster kann geschlossen werden.</p>")
        return self._plan_page()

    def _plan_page(self) -> str:
        counts = {a: len(self.plan.by_action(a)) for a in ACTION_TEXT}
        summary = " · ".join(f"{counts[a]} {text}" for a, text in ACTION_TEXT.items() if counts[a])
        rows = "\n".join(self._row(n, p) for n, p in enumerate(self.plan.plans))
        body = f"""
<p class="lead">{len(self.plan.plans)} neue Mails · {_e(summary)}</p>
<p>Noch ist nichts geschrieben. Prüfe die Kategorien, korrigiere sie bei Bedarf und gib den Lauf frei.
Ziel: <strong>{_e(self.store.location)}</strong></p>
<form method="post" action="/approve">
<input type="hidden" name="token" value="{_e(self.token)}">
<table>
<thead><tr><th>Datum</th><th>Mail</th><th>Kategorie</th><th>Was passiert</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<div class="actions">
<button type="submit" class="primary">Freigeben und ablegen</button>
<button type="submit" formaction="/cancel">Abbrechen</button>
</div>
</form>"""
        return _layout("Lauf freigeben", body)

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
            f"<td>{_e(ACTION_TEXT.get(p.action, p.action))}{details}</td></tr>"
        )

    def _done_page(self, result: RunResult) -> str:
        report = render_report(result, self.store.location)
        return _layout("Erledigt", f"<p>Der Lauf ist ausgeführt.</p><pre>{_e(report)}</pre>")


def _label_text(label: str) -> str:
    if label == UNCLEAR:
        return "unklar (in den Eingang)"
    if label == "werbung":
        return "werbung (nicht ablegen)"
    return label


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


_STYLE = """
:root{color-scheme:light dark;--bg:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e6;--accent:#2457d6}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--fg:#ececef;--muted:#a0a0a8;--line:#2c2c30;--accent:#7aa2ff}}
body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:auto}h1{font-size:22px;margin:0 0 8px}.lead{font-size:17px}
table{width:100%;border-collapse:collapse;margin:16px 0}th,td{text-align:left;vertical-align:top;padding:8px;
border-bottom:1px solid var(--line)}small{color:var(--muted)}ul{margin:4px 0 0;padding-left:18px}
select{max-width:100%;font:inherit}tr.ignore,tr.duplicate,tr.skip{opacity:.6}
.actions{display:flex;gap:12px;flex-wrap:wrap}button{font:inherit;padding:8px 16px;border-radius:8px;
border:1px solid var(--line);background:transparent;color:var(--fg);cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
pre{white-space:pre-wrap;background:color-mix(in srgb,var(--fg) 6%,transparent);padding:12px;border-radius:8px}
@media (max-width:700px){thead{display:none}tr{display:block;padding:8px 0;border-bottom:1px solid var(--line)}
td{display:block;border:0;padding:4px 0}}
"""


def _layout(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='de'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>PaperPilot: {_e(title)}</title><style>{_STYLE}</style></head>"
        f"<body><main><h1>{_e(title)}</h1>{body}</main></body></html>"
    )
