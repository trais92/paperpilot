"""Gemeinsame Bausteine der lokalen Seiten: Maskierung, Layout, Fehlerarten, Vertrag mit dem Server."""

from __future__ import annotations

import html
from collections.abc import Mapping
from typing import Protocol

__all__ = ["FormError", "LocalPage", "UnknownAction", "escape", "layout"]


class FormError(ValueError):
    """Ungültiges Formular (falsches Token, unbekannter Wert). Es wurde nichts geändert."""


class UnknownAction(LookupError):
    """Kein Formular unter dieser Adresse (der Server antwortet mit 404)."""


class LocalPage(Protocol):
    """Was `server.serve()` von einer Seite braucht. Umgesetzt von `ReviewSession` und `SetupSession`.

    `submit` prüft selbst das Token im Formular und wirft `FormError` oder `UnknownAction`.
    Nach jedem angenommenen Formular fragt der Server `finished`, um zu wissen, ob er enden kann.
    """

    token: str

    @property
    def finished(self) -> bool: ...

    def page(self) -> str: ...

    def submit(self, action: str, form: Mapping[str, str]) -> None: ...


def escape(value: object) -> str:
    """Jeder Wert aus Mails oder Eingaben geht hierdurch, bevor er in HTML landet."""
    return html.escape(str(value), quote=True)


STYLE = """
:root{color-scheme:light dark;--bg:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e6;--accent:#2457d6;
--ok:#1a7f37;--bad:#c4261d}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--fg:#ececef;--muted:#a0a0a8;--line:#2c2c30;
--accent:#7aa2ff;--ok:#4ac26b;--bad:#ff7b72}}
body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:auto}h1{font-size:22px;margin:0 0 8px}h2{font-size:18px;margin:0 0 8px}
.lead{font-size:17px}a{color:var(--accent)}
table{width:100%;border-collapse:collapse;margin:16px 0}th,td{text-align:left;vertical-align:top;padding:8px;
border-bottom:1px solid var(--line)}small{color:var(--muted)}ul{margin:4px 0 0;padding-left:18px}
select,input{max-width:100%;font:inherit}tr.ignore,tr.duplicate,tr.skip{opacity:.6}
.actions{display:flex;gap:12px;flex-wrap:wrap}button{font:inherit;padding:8px 16px;border-radius:8px;
border:1px solid var(--line);background:transparent;color:var(--fg);cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
pre{white-space:pre-wrap;background:color-mix(in srgb,var(--fg) 6%,transparent);padding:12px;border-radius:8px}
section{border:1px solid var(--line);border-radius:12px;padding:16px;margin:16px 0}
label{display:block;margin:8px 0}input[type=text],input[type=password]{width:24rem;padding:6px 8px;
border:1px solid var(--line);border-radius:6px;background:transparent;color:var(--fg)}
fieldset{border:0;padding:0;margin:8px 0}legend{font-weight:600}.check label{display:inline-block;margin:4px 16px 4px 0}
form+h2{margin-top:24px}
.ok{color:var(--ok)}.bad{color:var(--bad)}.notice{padding:8px 12px;border-radius:8px;border:1px solid currentColor}
@media (max-width:700px){thead{display:none}tr{display:block;padding:8px 0;border-bottom:1px solid var(--line)}
td{display:block;border:0;padding:4px 0}input[type=text],input[type=password]{width:100%}}
"""


def layout(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='de'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>PaperPilot: {escape(title)}</title><style>{STYLE}</style></head>"
        f"<body><main><h1>{escape(title)}</h1>{body}</main></body></html>"
    )
