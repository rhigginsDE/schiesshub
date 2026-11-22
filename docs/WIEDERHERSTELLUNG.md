# Wiederherstellung aus der Sicherung

Für den Fall, dass die Datenbank des Servers verloren oder beschädigt ist oder der Server ersetzt
wird. Gebraucht werden der Sicherungs-Stick und das **Sicherungspasswort**. Ohne Passwort lassen
sich weder Sicherung noch Mitschrift lesen.

## Was auf dem Stick liegt

| Datei | Inhalt |
|---|---|
| `snapshots/snapshot-<Zeit>Z.shb` | verschlüsselte Sicherung: `manifest.json`, Datenbank-Abzug (`database.dump`) und das ganze Schlüsselverzeichnis des Servers (`keys/`) |
| `snapshots/…shb.sha256` | Prüfsumme der Datei |
| `journal/journal-<Tag>.<Schlüssel>.shbj` | verschlüsselte Mitschrift: alle Ergebnis-Ereignisse des Tages (UTC), auch die nach der letzten Sicherung |

Im Schlüsselverzeichnis stecken der **Namensschlüssel** `field-keys.json` (Namen und
Mitgliedsnummern sind damit in der Datenbank verschlüsselt) und der Sicherungsschlüssel
`backup-key.json`. Beide kommen bei der Wiederherstellung mit zurück. Ohne den Namensschlüssel
startet der Server nicht, sobald es Personen gibt („Die Schlüsseldatei … fehlt“). Ein lokaler
Abzug (`.dump` aus `DATA_DIR/backups/snapshots`) enthält **keine** Schlüssel. Er hilft nur, wenn
`DATA_DIR/keys` noch vorhanden ist.

Die Mitschrift enthält nur Ergebnis-Ereignisse (Start, Startnummer, Rohwerte, Grund, Zeit), aber
keine Namen, keine Personen, Anmeldungen oder Starts und keine Änderungen an Turnier oder Wertung.

## Schritt für Schritt

Alle Befehle laufen im Backend-Container. Dort hängt der Stick unter `/backup-usb`, und
`DATABASE_URL` liefert die Zugangsdaten.

1. **Stick einstecken.** Neueste Sicherung heraussuchen:

   ```bash
   docker compose exec backend ls -l /backup-usb/snapshots /backup-usb/journal
   ```

2. **In eine neue, leere Datenbank zurückspielen und die Mitschrift nachtragen.** Die laufende
   Datenbank wird nie überschrieben:

   ```bash
   docker compose exec -e SCHIESSHUB_BACKUP_PASSPHRASE='…' backend \
     python -m app.modules.backup.restore /backup-usb/snapshots/snapshot-<Zeit>Z.shb \
       --database-name schiesshub_neu --create-database --data-dir /data \
       --apply-journal /backup-usb/journal
   ```

   Ohne die Variable fragt der Befehl im Terminal nach dem Passwort. `--help` zeigt alle
   Schalter.
   - Schritte: entschlüsseln, Prüfsumme prüfen, Schlüssel nach `/data/keys` schreiben, Abzug
     einspielen, Mitschrift nachtragen.
   - Gleiche Schlüssel, die in `/data/keys` schon liegen (derselbe Server), bleiben stehen.
     Bei abweichenden bricht der Befehl ab, bevor er die Datenbank anfasst. Das passiert, wenn
     ein neuer Server schon einmal leer gestartet wurde und dabei einen eigenen, noch unbenutzten
     Namensschlüssel angelegt hat. Dann diese Datei beiseitelegen (umbenennen, nicht löschen) und
     den Befehl wiederholen.
   - Ist die Mitschrift mit einem früheren Passwort verschlüsselt (Passwort inzwischen
     geändert), wird das frühere Passwort gebraucht.

3. **Ausgabe lesen.** Erwartet:
   `Sicherung vom … gelesen, Prüfsumme in Ordnung.` · `Datenbank „schiesshub_neu“ wiederhergestellt.` ·
   `N Ereignisse nachgetragen, K waren schon in der Sicherung, M übersprungen, weil der Start in der Sicherung fehlt: Startnummer …`

   Exit-Code `0`: alles nachgetragen. Exit-Code `3`: wiederhergestellt, aber einzelne Starts
   fehlen oder passen nicht. Sie stehen mit Startnummer in der Ausgabe. Das Nachtragen lässt
   sich beliebig wiederholen, nichts wird doppelt eingetragen:

   ```bash
   docker compose exec -e SCHIESSHUB_BACKUP_PASSPHRASE='…' backend \
     python -m app.modules.backup.restore --database-name schiesshub_neu --apply-journal /backup-usb/journal
   ```

4. **Server auf die neue Datenbank umstellen.** `DATABASE_URL` auf die neue Datenbank zeigen
   lassen (Entwicklungsumgebung: `POSTGRES_DB=schiesshub_neu` in `.env`), dann
   `docker compose up -d backend`. `DATA_DIR` muss das Verzeichnis aus `--data-dir` sein.

5. **Prüfen:**
   - `GET /api/v1/health` meldet die Datenbank als in Ordnung. Startet der Server nicht und
     meldet einen fehlenden Schlüssel, liegt `field-keys.json` nicht in `DATA_DIR/keys`.
   - Teilnehmer: Die Namen sind lesbar.
   - Turnier, Startliste und Live-Wertung mit den letzten Startzetteln vergleichen.
   - System → Sicherung: Das Passwort ist gesetzt (der Sicherungsschlüssel kam mit). „Jetzt
     sichern“ läuft durch, und der Stick ist „in Ordnung“.

## Was von Hand nachzutragen ist

Was nach der letzten Sicherung geschah und nicht in der Mitschrift steht:

- **Starts aus der Ausgabe „übersprungen, weil der Start in der Sicherung fehlt“:** Diese Starts
  wurden erst nach der Sicherung gebucht. Person anlegen, anmelden, Start buchen, Ergebnis vom
  Startzettel erfassen. Die Rohwerte stehen auch in der Mitschrift:
  `python -m app.modules.backup.restore /backup-usb/journal/journal-<Tag>.<Schlüssel>.shbj --output /tmp/mitschrift.ndjson`
  (je Zeile ein Ereignis, mit `start_number` und `payload.raw`).
- **„nicht nachgetragen, weil die Mitschrift nicht zur Datenbank passt“:** Den Start in der
  Erfassung öffnen und mit dem Startzettel abgleichen.
- **„Die Wertung von … wurde nach der Sicherung geändert“:** die Änderung im Turnier wiederholen.
  Die Ergebnisse werden dann neu berechnet.
- **Ohne Meldung verloren:** neue Personen, Anmeldungen, Startgeld, Durchgänge, Bahnen und
  Aufrufe sowie Änderungen an Turnier, Anzeigen, Rollen und Geräten nach der Sicherung.
  Nachgetragene Korrekturen und Abbrüche bekommen im System-Protokoll den Zeitpunkt des
  Nachtragens. Am Ergebnis selbst stehen Zeit, Person und Gerät der ursprünglichen Eingabe.

Die Sicherung läuft standardmäßig alle 5 Minuten. Verloren gehen also höchstens die nicht
ergebnisbezogenen Änderungen dieser Minuten.
