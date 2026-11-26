# Changelog

## 0.1.0 – 2026-11-26

Erste Version.

- Mail-Quellen: JSON/JSONL (Demo, Tests) und IMAP strikt lesend
- Regelbasierter Klassifizierer mit zweistufigen Gruppen, `unklar` unter Mindest-Score
- Optionaler LLM-Klassifizierer (Claude API, strukturierte Ausgabe), noch nicht gegen die echte API gemessen
- Ablage nach Namenskonvention `JJJJ-MM-TT_Absender_Thema.ext`, ohne Überschreiben
- Duplikat-Index (SHA-256) und Lauf-Stand für idempotente Läufe
- Fristen- und Terminerkennung, Export als `fristen.csv` und `fristen.ics`
- Bewerbungs-Tracker mit Spalte `neu_aus_mail`
- Evaluation: Genauigkeit, Precision/Recall/F1, Übergabequote; Testset mit 52 Mails
- CLI: `demo`, `run`, `eval`, `init`; CI auf Python 3.11–3.13
