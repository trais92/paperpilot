"""Evaluation: Trefferquote eines Klassifizierers auf einem gelabelten Testset messen."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .ports import Classifier
from .sources import mail_from_dict


@dataclass
class LabelMetrics:
    label: str
    precision: float
    recall: float
    f1: float
    support: int


@dataclass
class EvalReport:
    n: int
    accuracy: float
    group_accuracy: float
    macro_f1: float
    per_label: list[LabelMetrics]
    errors: list[tuple[str, str, str, str]]  # id, subject, erwartet, vorhergesagt
    unclear_rate: float


def _div(a: float, b: float) -> float:
    return a / b if b else 0.0


def evaluate(classifier: Classifier, samples: list[dict[str, Any]]) -> EvalReport:
    gold: list[str] = []
    pred: list[str] = []
    errors: list[tuple[str, str, str, str]] = []
    for s in samples:
        mail = mail_from_dict(s)
        p = classifier.classify(mail).label
        gold.append(s["label"])
        pred.append(p)
        if p != s["label"]:
            errors.append((s["id"], s["subject"], s["label"], p))
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    for g, p in zip(gold, pred, strict=True):
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
    )


def render_eval(r: EvalReport) -> str:
    lines = [
        f"Testset: {r.n} Mails",
        f"Genauigkeit (Label):   {r.accuracy:6.1%}",
        f"Genauigkeit (Gruppe):  {r.group_accuracy:6.1%}   (bewerbung / privat / werbung)",
        f"Macro-F1:              {r.macro_f1:6.3f}",
        f"An Mensch übergeben:   {r.unclear_rate:6.1%}   (Label 'unklar')",
        "",
        f"{'Label':<32}{'Precision':>10}{'Recall':>10}{'F1':>8}{'n':>5}",
    ]
    for m in r.per_label:
        lines.append(f"{m.label:<32}{m.precision:>10.2f}{m.recall:>10.2f}{m.f1:>8.2f}{m.support:>5}")
    if r.errors:
        lines.append("\nFehlklassifiziert:")
        for _id, subj, g, p in r.errors:
            lines.append(f"  {_id:<8} erwartet {g:<28} bekam {p:<28} {subj[:50]}")
    return "\n".join(lines)
