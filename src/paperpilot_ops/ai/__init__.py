"""KI-Schicht: Sprachmodelle als austauschbare Adapter und der KI-Klassifizierer.

Aufbau (docs/adr/0003-ki-fest-eingebaut.md, docs/adr/0007-ki-schicht.md):

- `http.py`: kleinster HTTP-Baustein auf Basis der Standardbibliothek, in Tests ersetzbar.
- `openai_compatible.py`: Adapter für Anbieter mit OpenAI-kompatibler Schnittstelle (heute Groq).
- `anthropic.py`: Adapter für Claude über das offizielle SDK (optionales Extra `[llm]`).
- `fallback.py`: Reserve-Kette, fragt den nächsten Anbieter, wenn einer ausfällt.
- `providers.py`: bekannte Anbieter, Standardmodelle und der Aufbau aus Konfiguration und Zugangsdaten.
- `classifier.py`: `AIClassifier` (Prompt, strenge Prüfung der Antwort) und `PrefilteredClassifier`.
"""

from .classifier import AIClassifier, PrefilteredClassifier
from .fallback import FallbackModel
from .providers import MissingAIKeyError, build_language_model

__all__ = ["AIClassifier", "FallbackModel", "MissingAIKeyError", "PrefilteredClassifier", "build_language_model"]
