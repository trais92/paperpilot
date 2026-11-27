"""Evaluation: Trefferquote eines Klassifizierers auf einem gelabelten Testset messen.

Gemessen werden Kategorien (Genauigkeit, Precision/Recall/F1 je Label, Verwechslungen) und,
wenn das Testset erwartete Angaben enthält (`fields`), die ausgelesenen Angaben je Feld.
Testsets können in `dev` und `holdout` geteilt sein (`split`); optimiert wird nur auf `dev` (Regel 9).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from .fields import FIELD_LABELS, FIELD_NAMES, FieldError, check_amount, check_date, check_reference
from .ports import Classifier
from .sources import mail_from_dict

__all__ = ["SPLITS", "EvalReport", "FieldMetrics", "LabelMetrics", "evaluate", "render_eval", "select_split"]

SPLITS = ("all", "dev", "holdout")


@dataclass
class LabelMetrics:
    label: str
    precision: float
    recall: float
    f1: float
    support: int


@dataclass
class FieldMetrics:
    """Wie gut eine Angabe ausgelesen wird. Exakter Vergleich nach Normalisierung (`fields.py`)."""

    name: str
    precision: float  # richtige / ausgegebene Werte: Wie oft stimmt eine ausgegebene Angabe?
    recall: float  # richtige / erwartete Werte: Wie viele erwartete Angaben werden gefunden?
    expected: int
    predicted: int
    correct: int


@dataclass
class EvalReport:
    n: int
    accuracy: float
    group_accuracy: float
    macro_f1: float
    per_label: list[LabelMetrics]
    errors: list[tuple[str, str, str, str]]  # id, subject, erwartet, vorhergesagt
    unclear_rate: float
    split: str = "all"
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)  # erwartet -> vorhergesagt -> Anzahl
    fields: list[FieldMetrics] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Für `paperpilot eval --json` (Vergleich zwischen Anbietern und Läufen)."""
        return asdict(self)


def _div(a: float, b: float) -> float:
    return a / b if b else 0.0


def select_split(samples: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    """`all` oder nur `dev`/`holdout`. Mails ohne `split` zählen zu `dev`."""
    if split not in SPLITS:
        raise ValueError(f"Unbekannter Split {split!r}, erlaubt: {', '.join(SPLITS)}")
    if split == "all":
        return samples
    return [s for s in samples if s.get("split", "dev") == split]


def _normalise(name: str, value: object) -> str:
    """Erwartete Angabe aus dem Testset in dieselbe Form bringen wie die Vorhersage."""
    if name == "amount":
        return check_amount(value)
    if name == "reference":
        return check_reference(value)
    return check_date(value)


def _field_metrics(gold: list[dict[str, str]], pred: list[dict[str, str]]) -> list[FieldMetrics]:
    out = []
    for name in FIELD_NAMES:
        expected = sum(1 for g in gold if g.get(name))
        predicted = sum(1 for p in pred if p.get(name))
        correct = sum(1 for g, p in zip(gold, pred, strict=True) if g.get(name) and g.get(name) == p.get(name))
        out.append(
            FieldMetrics(
                FIELD_LABELS[name], _div(correct, predicted), _div(correct, expected), expected, predicted, correct
            )
        )
    return out


def evaluate(classifier: Classifier, samples: list[dict[str, Any]], split: str = "all") -> EvalReport:
    samples = select_split(samples, split)
    gold: list[str] = []
    pred: list[str] = []
    errors: list[tuple[str, str, str, str]] = []
    gold_fields: list[dict[str, str]] = []
    pred_fields: list[dict[str, str]] = []
    for s in samples:
        result = classifier.classify(mail_from_dict(s))
        p = result.label
        gold.append(s["label"])
        pred.append(p)
        if p != s["label"]:
            errors.append((s["id"], s["subject"], s["label"], p))
        if "fields" in s:
            try:
                gold_fields.append({k: _normalise(k, v) for k, v in s["fields"].items()})
            except FieldError as exc:
                raise ValueError(f"Testset {s['id']}: ungültige erwartete Angabe ({exc})") from None
            pred_fields.append({name: getattr(result.fields, name) for name in FIELD_NAMES})
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    confusion: dict[str, dict[str, int]] = {}
    for g, p in zip(gold, pred, strict=True):
        row = confusion.setdefault(g, {})
        row[p] = row.get(p, 0) + 1
        if g == p:
            tp[g] += 1
        else:
            fp[p] += 1
            fn[g] += 1
    per_label = []
    for label in sorted(set(gold)):
        pr, rc = _div(tp[label], tp[label] + fp[label]), _div(tp[label], tp[label] + fn[label])
        per_label.append(LabelMetrics(label, pr, rc, _div(2 * pr * rc, pr + rc), tp[label] + fn[label]))
    n = len(gold)
    return EvalReport(
        n=n,
        accuracy=_div(sum(tp.values()), n),
        group_accuracy=_div(sum(g.split("/")[0] == p.split("/")[0] for g, p in zip(gold, pred, strict=True)), n),
        macro_f1=_div(sum(m.f1 for m in per_label), len(per_label)),
        per_label=per_label,
        errors=errors,
        unclear_rate=_div(pred.count("unklar"), n),
        split=split,
        confusion={g: dict(sorted(row.items())) for g, row in sorted(confusion.items())},
        fields=_field_metrics(gold_fields, pred_fields) if gold_fields else [],
    )


def render_eval(r: EvalReport) -> str:
    split = "" if r.split == "all" else f" (Split: {r.split})"
    lines = [
        f"Testset: {r.n} Mails{split}",
        f"Genauigkeit (Label):   {r.accuracy:6.1%}",
        f"Genauigkeit (Gruppe):  {r.group_accuracy:6.1%}   (bewerbung / privat / werbung)",
        f"Macro-F1:              {r.macro_f1:6.3f}",
        f"An Mensch übergeben:   {r.unclear_rate:6.1%}   (Label 'unklar')",
        "",
        f"{'Label':<32}{'Precision':>10}{'Recall':>10}{'F1':>8}{'n':>5}",
    ]
    for m in r.per_label:
        lines.append(f"{m.label:<32}{m.precision:>10.2f}{m.recall:>10.2f}{m.f1:>8.2f}{m.support:>5}")
    if r.fields:
        lines += ["", f"{'Angabe':<32}{'Precision':>10}{'Recall':>10}{'erw.':>8}{'ausg.':>7}"]
        for f in r.fields:
            lines.append(f"{f.name:<32}{f.precision:>10.2f}{f.recall:>10.2f}{f.expected:>8}{f.predicted:>7}")
    mixups = sorted(
        ((n, g, p) for g, row in r.confusion.items() for p, n in row.items() if g != p), key=lambda t: (-t[0], t[1])
    )
    if mixups:
        lines.append("\nVerwechslungen (erwartet -> bekam):")
        lines.extend(f"  {n:>3} × {g:<30} -> {p}" for n, g, p in mixups)
    if r.errors:
        lines.append("\nFehlklassifiziert:")
        for _id, subj, g, p in r.errors:
            lines.append(f"  {_id:<8} erwartet {g:<28} bekam {p:<28} {subj[:50]}")
    return "\n".join(lines)
