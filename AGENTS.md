# Arbeitsanweisungen für Agents

## Workflow: Plan → Implementierung → Review

Sobald ein Plan für eine Änderung steht (egal ob im Plan-Modus erstellt oder
im Chat abgestimmt), wird er **nicht direkt im Hauptchat umgesetzt**.
Stattdessen gilt folgende Schleife:

1. **Implementierung – Subagent mit Sonnet**
   - Starte einen Subagent (`Agent`-Tool, `subagent_type: "general-purpose"`,
     `model: "sonnet"`).
   - Gib ihm den vollständigen Plan mit: Ziel, betroffene Dateien,
     konkrete Schritte, Akzeptanzkriterien und – ab der zweiten Runde – die
     offenen Review-Anmerkungen, die er beheben soll.
   - Der Subagent setzt um und meldet zurück, was er geändert hat.

2. **Review – Subagent mit Opus**
   - Starte danach einen *neuen* Subagent (`subagent_type: "general-purpose"`,
     `model: "opus"`) für das Review.
   - Er bekommt den Plan und prüft die tatsächlichen Änderungen
     (`git diff` bzw. die geänderten Dateien) auf Korrektheit, Vollständigkeit
     gegenüber dem Plan, Bugs, Seiteneffekte und Stil.
   - Er ändert selbst **keinen** Code, sondern liefert entweder
     - eine nummerierte Liste konkreter Anmerkungen, oder
     - exakt die Aussage **„Keine Anmerkungen“**.
   - Dies ist das **einzige** Review – der Hauptchat prüft nicht zusätzlich.

3. **Schleife**
   - Hat das Review Anmerkungen → zurück zu Schritt 1: neuer
     Sonnet-Implementierungs-Subagent mit Plan + Anmerkungen, danach wieder
     ein Review-Subagent.
   - Das wiederholt sich, bis ein Review **„Keine Anmerkungen“** liefert.

4. **Abschluss**
   - Erst wenn das Review ohne Anmerkungen ist, meldet der Hauptchat die
     Aufgabe als **fertig** – mit kurzer Zusammenfassung der Änderungen und
     der Anzahl der Runden.
   - Vorher wird nichts als „fertig“ bezeichnet.
   - Sollte die Schleife nach 5 Runden noch nicht konvergieren (z. B. weil
     Reviewer und Implementierer sich widersprechen), hält der Hauptchat an
     und legt dem Nutzer die strittigen Punkte zur Entscheidung vor.

Der Hauptchat übernimmt in diesem Ablauf nur Planung, Koordination und die
Weitergabe der Ergebnisse – er schreibt den Code nicht selbst. Er führt auch
**kein eigenes Review** durch (kein eigenes Prüfen oder Gegenlesen des Diffs,
keine eigenen zusätzlichen Anmerkungen, kein Nachprüfen des
Subagent-Ergebnisses). Das Review findet ausschließlich im Review-Subagenten
statt; der Hauptchat übernimmt dessen Ergebnis unverändert: „Keine
Anmerkungen“ → fertig, Anmerkungen → nächste Runde (nach 5 Runden ohne
Konvergenz Rückfrage beim Nutzer, siehe Schritt 4).

## Branch-Namen

Branches bekommen **sprechende Namen** nach dem Schema `<typ>/<stichwort>`.
Automatisch generierte Namen wie `claude/*` werden **nicht** verwendet.

- **Typ** (Präfix):
  - `feature/` – neue Funktionen (Standard, wenn nichts anderes passt)
  - `fix/` – Bugfixes
  - `docs/` – reine Doku-Änderungen
  - `chore/` – Wartung, Refactoring, Konfiguration
- **Stichwort**: kurz (1–4 Wörter), kleingeschrieben, kebab-case, nur
  `a-z`, `0-9` und Bindestriche. Es beschreibt das Feature bzw. die
  Änderung, z. B. `feature/dark-mode`, `feature/kontaktformular`,
  `fix/navigation-mobile`.

Das gilt auch, wenn eine Umgebung oder ein Tool einen Branch-Namen wie
`claude/...` vorgibt: Dann wird stattdessen ein passender Name nach dem
obigen Schema verwendet.
