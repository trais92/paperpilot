"""Reserve-Kette: fragt Anbieter der Reihe nach, bis einer antwortet (docs/adr/0003)."""

from __future__ import annotations

from typing import Any

from ..models import Completion
from ..ports import LanguageModel, ProviderError


class FallbackModel:
    """Ein `LanguageModel` aus mehreren. Der nächste wird nur bei `ProviderError` gefragt.

    Eine inhaltlich unbrauchbare Antwort (falsches Label, kein JSON) ist kein Anlass für die Reserve:
    Sie würde dieselbe Mail ein zweites Mal nach außen schicken. Das entscheidet der Klassifizierer.
    """

    def __init__(self, *models: LanguageModel):
        if not models:
            raise ValueError("Mindestens ein Modell nötig.")
        self._models = models

    def __repr__(self) -> str:
        return f"FallbackModel({', '.join(map(repr, self._models))})"

    @property
    def name(self) -> str:
        return " → ".join(m.name for m in self._models)

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> Completion:
        errors: list[ProviderError] = []
        for model in self._models:
            try:
                return model.complete_json(system, user, schema)
            except ProviderError as err:
                errors.append(err)
        summary = "; ".join(f"{e.provider} ({e.kind})" for e in errors)
        raise ProviderError(self.name, errors[-1].kind, f"kein Anbieter erreichbar: {summary}")
