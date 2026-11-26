"""Namenskonvention: JJJJ-MM-TT_Absender_Thema.ext"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from .models import Mail

_GENDER = re.compile(r"\((m|w|d|f|x|div)(\s*/\s*(m|w|d|f|x|div))+\)", re.IGNORECASE)
_PREFIX = re.compile(r"^\s*((re|aw|wg|fw|fwd)\s*:\s*)+", re.IGNORECASE)
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})
_STOP = {
    "ihre",
    "ihr",
    "deine",
    "dein",
    "zu",
    "zur",
    "zum",
    "der",
    "die",
    "das",
    "den",
    "und",
    "fuer",
    "von",
    "an",
    "am",
    "im",
    "in",
    "ein",
    "eine",
    "als",
    "mit",
    "ist",
    "bei",
    "ihres",
    "ihrer",
    "ihren",
    "deiner",
    "deinen",
}


def slug(text: str, max_words: int = 5) -> str:
    """'Einladung zum Interview: Projektmanager (m/w/d)' -> 'Einladung-Interview-Projektmanager'"""
    text = unicodedata.normalize("NFKC", _GENDER.sub("", text)).translate(_UMLAUTS)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = [w for w in re.split(r"[^A-Za-z0-9]+", re.sub(r"[/()]", "", text)) if w]
    kept = [w for w in words if w.lower() not in _STOP] or words
    out = "-".join(w if w.isupper() and len(w) > 1 else w[:1].upper() + w[1:] for w in kept[:max_words])
    return out or "Ohne-Titel"


def company_from_mail(mail: Mail, generic_domains: frozenset[str]) -> str:
    """Firmen-/Absendername: Domain (ohne TLD) oder bei Freemail der Anzeigename."""
    domain = mail.sender_domain
    if domain and domain not in generic_domains:
        parts = domain.split(".")
        core = parts[-2] if len(parts) >= 2 else parts[0]
        if core in {"mail", "jobs", "career", "karriere", "noreply"} and len(parts) >= 3:
            core = parts[-3]
        return slug(core.replace("-", " "), max_words=4)
    return slug(mail.sender_name or mail.sender_address.split("@")[0], max_words=3)


def build_filename(date: datetime, sender: str, topic: str, ext: str) -> str:
    ext = ext.lstrip(".").lower() or "txt"
    return f"{date:%Y-%m-%d}_{sender}_{slug(_PREFIX.sub('', topic))}.{ext}"
