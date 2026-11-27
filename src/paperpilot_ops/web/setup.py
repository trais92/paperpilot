"""Einrichtungsassistent als lokale Seite: Postfach, KI-Schlüssel, Kategorien, Ablageziel, Zeitplan.

Eine Seite mit einem Formular pro Abschnitt. Jeder Abschnitt speichert für sich:
- Zugangsdaten (Postfach, KI-Schlüssel, Google) gehen in den Schlüsselbund (Regel 6) und werden
  nie wieder angezeigt, nur „gespeichert“ oder „fehlt“;
- Kategorien und Ablageziel gehen in `settings.toml` (`settings.py`, ADR 0010).

Netzwerk und Browser stecken in den übergebenen Funktionen `check_imap` und `google_login`,
damit die Seite ohne Netz testbar bleibt.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..config import Category, Rules
from ..credentials import CredentialStoreError
from ..ports import MutableCredentialStore
from ..settings import UserSettings, apply_settings, save_settings
from .page import FormError, UnknownAction, escape, layout

__all__ = ["DEFAULT_IMAP_HOST", "SetupSession"]

DEFAULT_IMAP_HOST = "imap.gmail.com"
APP_PASSWORD_HELP = "https://myaccount.google.com/apppasswords"
GROQ_KEYS_URL = "https://console.groq.com/keys"


@dataclass
class _Notice:
    text: str
    ok: bool


@dataclass
class SetupSession:
    """Zustand des Assistenten. `submit()` ist der einzige Weg, etwas zu speichern."""

    rules: Rules  # Regeldatei ohne persönliche Einstellungen
    settings: UserSettings
    settings_file: Path
    vault: MutableCredentialStore | None  # None: kein Schlüsselbund auf diesem System
    token: str
    check_imap: Callable[[str, str, str], None]
    google_login: Callable[[str, str], str]
    vault_error: str = ""
    review_requested: bool = False
    done: bool = False
    notice: _Notice | None = field(default=None, repr=False)

    @property
    def finished(self) -> bool:
        return self.done

    @property
    def effective_rules(self) -> Rules:
        return apply_settings(self.rules, self.settings)

    # -- Aktionen ------------------------------------------------------------------------------
    def submit(self, action: str, form: Mapping[str, str]) -> None:
        handlers: dict[str, Callable[[Mapping[str, str]], str]] = {
            "mail": self._save_mail,
            "ai": self._save_ai,
            "categories": self._save_categories,
            "storage": self._save_storage,
            "google": self._connect_google,
            "finish": self._finish,
        }
        if action not in handlers:
            raise UnknownAction(action)
        if self.done:
            raise FormError("Die Einrichtung ist schon abgeschlossen.")
        if form.get("token") != self.token:
            raise FormError("Ungültiges Formular.")
        try:
            self.notice = _Notice(handlers[action](form), ok=True)
        except (FormError, CredentialStoreError) as exc:
            self.notice = _Notice(str(exc), ok=False)

    def _vault(self) -> MutableCredentialStore:
        if self.vault is None:
            raise FormError(f"Kein Schlüsselbund verfügbar: {self.vault_error} Nichts gespeichert.")
        return self.vault

    def _save_mail(self, form: Mapping[str, str]) -> str:
        vault = self._vault()
        host = form.get("host", "").strip() or DEFAULT_IMAP_HOST
        user = form.get("user", "").strip()
        password = form.get("password", "")
        if not user or not password:
            raise FormError("Mailadresse und App-Passwort sind Pflicht. Nichts gespeichert.")
        try:
            self.check_imap(host, user, password)
        except Exception as exc:  # Meldungen des Servers können Eingaben spiegeln, deshalb nur der Typ
            raise FormError(
                f"Anmeldung bei {host} fehlgeschlagen ({type(exc).__name__}). Nichts gespeichert."
            ) from None
        vault.set("imap_host", host)
        vault.set("imap_user", user)
        vault.set("imap_password", password)
        return f"Postfach geprüft und gespeichert ({host})."

    def _save_ai(self, form: Mapping[str, str]) -> str:
        vault = self._vault()
        key = form.get("groq_key", "").strip()
        if not key:
            raise FormError("Kein Schlüssel eingegeben. Nichts gespeichert.")
        vault.set("groq_api_key", key)
        return "KI-Schlüssel gespeichert."

    def _save_categories(self, form: Mapping[str, str]) -> str:
        chosen = {c.label: form.get(f"cat-{c.label}") == "on" for c in self._selectable()}
        self._store(replace(self.settings, categories=chosen))
        count = sum(chosen.values())
        return f"Kategorien gespeichert: {count} von {len(chosen)} werden abgelegt."

    def _save_storage(self, form: Mapping[str, str]) -> str:
        target = form.get("target", "local")
        try:
            updated = replace(
                self.settings,
                storage_target=target,
                target_dir=form.get("target_dir", "").strip() or self.effective_rules.target_dir,
                drive_folder=form.get("drive_folder", "").strip() or self.effective_rules.storage.drive_folder,
            )
        except ValueError as exc:
            raise FormError(f"{exc} Nichts gespeichert.") from None
        self._store(updated)
        if target == "drive":
            return "Ablageziel gespeichert: Google Drive."
        return f"Ablageziel gespeichert: {updated.target_dir}."

    def _connect_google(self, form: Mapping[str, str]) -> str:
        vault = self._vault()
        client_id = form.get("client_id", "").strip() or vault.get("google_client_id") or ""
        client_secret = form.get("client_secret", "").strip() or vault.get("google_client_secret") or ""
        if not client_id or not client_secret:
            raise FormError(
                "Client-ID und Client-Secret sind Pflicht (siehe docs/google-drive.md). Nichts gespeichert."
            )
        try:
            refresh_token = self.google_login(client_id, client_secret)
        except Exception as exc:  # OAuthError hat eine eigene, wertfreie Meldung; sonst nur der Typ
            reason = str(exc) if type(exc).__name__ == "OAuthError" else type(exc).__name__
            raise FormError(f"Anmeldung bei Google fehlgeschlagen: {reason} Nichts gespeichert.") from None
        vault.set("google_client_id", client_id)
        vault.set("google_client_secret", client_secret)
        vault.set("google_refresh_token", refresh_token)
        return "Google Drive verbunden."

    def _finish(self, form: Mapping[str, str]) -> str:
        self.review_requested = form.get("next") == "review"
        self.done = True
        return "Einrichtung abgeschlossen."

    def _store(self, settings: UserSettings) -> None:
        apply_settings(self.rules, settings)  # prüft vor dem Schreiben, dass alles zu den Regeln passt
        save_settings(settings, self.settings_file)
        self.settings = settings

    def _selectable(self) -> list[Category]:
        """Kategorien, die abgelegt werden können (Werbung wird nie abgelegt und steht nicht zur Wahl)."""
        return [c for c in self.rules.categories if c.action == "file"]

    # -- Seite ---------------------------------------------------------------------------------
    def _has(self, key: str) -> bool:
        if self.vault is None:
            return False
        try:
            return bool(self.vault.get(key))
        except CredentialStoreError:
            return False

    def page(self) -> str:
        if self.done:
            follow = (
                "<p>Gleich öffnet sich der erste Lauf zur Freigabe.</p>"
                if self.review_requested
                else "<p>Das Fenster kann geschlossen werden.</p>"
            )
            return layout("Einrichtung abgeschlossen", f"<p>Alles ist gespeichert.</p>{follow}")
        parts = [self._notice_html(), self._intro(), self._mail_section(), self._ai_section()]
        parts += [self._categories_section(), self._storage_section(), self._schedule_section()]
        parts.append(self._finish_section())
        return layout("PaperPilot einrichten", "\n".join(parts))

    def _form(self, action: str, inner: str, button: str) -> str:
        return (
            f'<form method="post" action="/{action}" autocomplete="off">'
            f'<input type="hidden" name="token" value="{escape(self.token)}">{inner}'
            f'<div class="actions"><button type="submit" class="primary">{escape(button)}</button></div></form>'
        )

    def _status(self, ok: bool, yes: str = "gespeichert", no: str = "fehlt") -> str:
        return f'<span class="ok">✓ {escape(yes)}</span>' if ok else f'<span class="bad">○ {escape(no)}</span>'

    def _notice_html(self) -> str:
        if self.notice is None:
            return ""
        css = "ok" if self.notice.ok else "bad"
        return f'<p class="notice {css}" role="status">{escape(self.notice.text)}</p>'

    def _intro(self) -> str:
        vault = (
            ""
            if self.vault is not None
            else f'<p class="bad">Kein Schlüsselbund gefunden: {escape(self.vault_error)} '
            "Zugangsdaten lassen sich dann nur über Umgebungsvariablen setzen (siehe README).</p>"
        )
        return (
            '<p class="lead">Fünf Schritte, jeder speichert für sich. Passwörter und Schlüssel landen im '
            "Schlüsselbund des Betriebssystems und werden hier nie wieder angezeigt.</p>" + vault
        )

    def _mail_section(self) -> str:
        user = ""
        host = DEFAULT_IMAP_HOST
        if self.vault is not None and self._has("imap_user"):
            user = self.vault.get("imap_user") or ""
            host = self.vault.get("imap_host") or host
        inner = (
            f'<label>IMAP-Server<br><input type="text" name="host" value="{escape(host)}"></label>'
            f'<label>Mailadresse<br><input type="text" name="user" value="{escape(user)}"></label>'
            '<label>App-Passwort<br><input type="password" name="password"></label>'
            f'<small>Bei Gmail: IMAP aktivieren und ein <a href="{APP_PASSWORD_HELP}" target="_blank" '
            'rel="noopener noreferrer">App-Passwort</a> anlegen. PaperPilot liest nur, es verschiebt, '
            "löscht oder markiert nichts. Vor dem Speichern wird die Anmeldung geprüft.</small>"
        )
        status = self._status(self._has("imap_password"))
        return f"<section><h2>1. Postfach {status}</h2>{self._form('mail', inner, 'Prüfen und speichern')}</section>"

    def _ai_section(self) -> str:
        inner = (
            '<label>Groq-API-Schlüssel<br><input type="password" name="groq_key"></label>'
            f'<small>Kostenlos und ohne Kreditkarte: bei <a href="{GROQ_KEYS_URL}" target="_blank" '
            'rel="noopener noreferrer">console.groq.com</a> anmelden und einen Schlüssel erstellen. '
            "Was an die KI geht, steht in docs/ai-providers.md.<br>Claude ist ebenfalls möglich, aber "
            "<strong>kostenpflichtig</strong> (eigener Schlüssel, Abrechnung beim Anbieter) und deshalb hier "
            "nicht voreingestellt: paperpilot login --ai claude.</small>"
        )
        status = self._status(self._has("groq_api_key"))
        return f"<section><h2>2. KI {status}</h2>{self._form('ai', inner, 'Speichern')}</section>"

    def _categories_section(self) -> str:
        rules = self.effective_rules
        by_group: dict[str, list[str]] = {}
        for c in self._selectable():
            checked = " checked" if rules.is_selected(c.label) else ""
            title = f' title="{escape(c.description)}"' if c.description else ""
            box = (
                f'<label{title}><input type="checkbox" name="cat-{escape(c.label)}"{checked}> '
                f"{escape(c.label.split('/', 1)[-1])}</label>"
            )
            by_group.setdefault(c.label.split("/", 1)[0] if "/" in c.label else "weitere", []).append(box)
        groups = "".join(
            f'<fieldset class="check"><legend>{escape(name)}</legend>{"".join(boxes)}</fieldset>'
            for name, boxes in by_group.items()
        )
        inner = groups + "<small>Nicht gewählte Kategorien werden erkannt, bleiben aber nur im Postfach.</small>"
        return f"<section><h2>3. Kategorien</h2>{self._form('categories', inner, 'Speichern')}</section>"

    def _storage_section(self) -> str:
        rules = self.effective_rules
        local = rules.storage.target == "local"
        drive_ok = self._has("google_refresh_token")
        inner = (
            f'<fieldset><label><input type="radio" name="target" value="local"{" checked" if local else ""}> '
            "Ordner auf diesem Rechner</label>"
            f'<label>Ordner<br><input type="text" name="target_dir" value="{escape(rules.target_dir)}"></label>'
            f'<label><input type="radio" name="target" value="drive"{"" if local else " checked"}> '
            f"Google Drive {self._status(drive_ok, 'verbunden', 'nicht verbunden')}</label>"
            f'<label>Ordner in „Meine Ablage“<br><input type="text" name="drive_folder" '
            f'value="{escape(rules.storage.drive_folder)}"></label></fieldset>'
        )
        google = (
            '<label>OAuth-Client-ID<br><input type="text" name="client_id"></label>'
            '<label>OAuth-Client-Secret<br><input type="password" name="client_secret"></label>'
            "<small>Leer lassen, um gespeicherte Werte zu nutzen. Ein neues Fenster fragt bei Google nach "
            "Zustimmung; PaperPilot sieht danach nur Dateien, die es selbst anlegt. Einrichtung des "
            "OAuth-Clients: docs/google-drive.md.</small>"
        )
        return (
            f"<section><h2>4. Ablageziel</h2>{self._form('storage', inner, 'Speichern')}"
            f"<h2>Google Drive verbinden</h2>{self._form('google', google, 'Mit Google verbinden')}</section>"
        )

    def _schedule_section(self) -> str:
        command = "paperpilot run --source imap --apply"
        return (
            "<section><h2>5. Zeitplan</h2><p>Für automatische Läufe ohne Freigabe einmal einrichten:</p>"
            "<p><small>Linux/macOS (crontab -e), täglich 9 und 21 Uhr:</small></p>"
            f"<pre>0 9,21 * * * {escape(command)}</pre>"
            "<p><small>Windows (Eingabeaufforderung):</small></p>"
            f'<pre>schtasks /create /tn "paperpilot-mail" /sc daily /st 09:00 /tr "{escape(command)}"</pre>'
            "<small>Die Einstellungen dieser Seite gelten auch für zeitgesteuerte Läufe.</small></section>"
        )

    def _finish_section(self) -> str:
        return (
            f'<form method="post" action="/finish"><input type="hidden" name="token" value="{escape(self.token)}">'
            '<div class="actions"><button type="submit" name="next" value="review" class="primary">'
            "Fertig, ersten Lauf ansehen</button>"
            '<button type="submit" name="next" value="close">Fertig</button></div></form>'
        )
