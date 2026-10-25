# Manus Kulturprogramm – Online-Startpaket

Dies ist ein **technischer Prototyp**, kein bereits vollständig getesteter Veranstaltungs-Import. Die fünf bestätigten Kategorien und Farben bleiben gleich.

## GitHub Pages einrichten (ohne Kommandozeile)

1. Auf github.com kostenlos anmelden und ein neues **öffentliches** Repository erstellen, zum Beispiel `manus-kulturprogramm`. Bei GitHub Pages auf dem kostenlosen Konto ist ein öffentliches Repository der einfachste Weg. **Keine privaten Daten** im Repository speichern.
2. **Alle Dateien und Ordner aus diesem ZIP** in das Repository hochladen, insbesondere `index.html`, `scraper.py`, `requirements.txt`, `sources.json` und die versteckte Datei `.github/workflows/update.yml`. GitHub Web-Upload unterstützt Ordner per Drag-and-drop; die versteckte `.github`-Datei auf dem Mac ggf. über Cmd+Shift+Punkt einblenden. Alternativ GitHub Desktop verwenden.
3. Unter **Settings → Actions → General → Workflow permissions** `Read and write permissions` aktivieren, wenn erforderlich.
4. Unter **Actions** den Workflow `Manus Kulturprogramm Termine aktualisieren` öffnen und mit **Run workflow** starten. Danach im Ausführungsprotokoll auf Fehler prüfen; bei Erfolg wird `events.json` erzeugt.
5. Unter **Settings → Pages → Build and deployment**: `Deploy from a branch`, Branch `main`, Folder `/ (root)` → Save. Die angezeigte Pages-Adresse verwenden (typisch `https://BENUTZERNAME.github.io/manus-kulturprogramm/`).

## Weitere URLs hinzufügen

Die Datei `sources.json` im GitHub-Repository über den Stift bearbeiten. Einen Eintrag im gleichen Format hinzufügen, z. B.:

```json
{ "name": "Neuer Veranstaltungsort", "url": "https://beispiel.de/termine", "enabled": true }
```

Zwischen allen Einträgen steht ein Komma; **nach dem letzten nicht**. Commit changes klicken, danach unter Actions den Aktualisierungslauf manuell starten oder den täglichen Lauf abwarten.

Ein neuer Link wird damit als Quelle registriert. **Das bedeutet nicht automatisch, dass Termine erkannt werden**: Wenn die Seite keine strukturierten Event-Daten veröffentlicht, braucht sie einen spezifischen Parser. Im Quellenstatus heißt das `needs_parser`, `error` oder `ok`. `ok` bedeutet nur, dass der Parser bei dieser Abfrage mindestens einen Termin fand, nicht dass das Programm vollständig ist.

## Wichtige Grenzen

- Die Datenerfassung für 13 Startquellen wurde nicht vollständig auf GitHub Actions geprüft. Nur einige Quellen besitzen vorläufige Parser.
- Die mitgelieferten Offline-Beispielveranstaltungen sind eine **Momentaufnahme von Oktober 2026** und dürfen nicht als live geprüft verstanden werden. Nach Erstellung von `events.json` werden nur dort erfasste Termine gezeigt; fehlende Termine bedeuten nicht zwangsläufig, dass es keine Veranstaltungen gibt.
- Die Filter für Kino-/Kinderprogramm sind heuristisch, daher alle Ergebnisse stichprobenartig kontrollieren.
- Automatischer Lauf täglich; GitHub-Actions-Zeitpläne können verzögert oder durch GitHub-Einstellungen deaktiviert werden.
- Die spätere Schaltfläche „Veranstaltungsort hinzufügen“ direkt in der App ist **noch nicht umgesetzt**, weil dazu eine sichere Schreibanbindung nötig ist. Vorläufig funktioniert die Ergänzung unkompliziert über `sources.json` in GitHub.

## Lokal ausführen

```bash
python -m pip install -r requirements.txt
python scraper.py
python -m http.server 8000
```

Danach `http://localhost:8000` öffnen. Nur öffentlich zugängliche Webseiten auslesen und keine Zugriffssperren umgehen.
