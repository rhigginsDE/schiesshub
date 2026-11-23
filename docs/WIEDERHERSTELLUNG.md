# Wiederherstellung aus der Sicherung

Für den Fall, dass Daten verloren oder beschädigt sind oder der Server ersetzt wird. Gebraucht
werden die Sicherung (Stick oder Server) und für Sicherungen vom Stick das **Sicherungspasswort**.
Ohne Passwort lassen sich weder Sicherung noch Mitschrift vom Stick lesen.

Es gibt zwei Wege:

1. **In der App** (System → Sicherung → Wiederherstellen): geführt, mit Vorschau, nur für
   Administratoren mit PIN. Das ist der normale Weg.
2. **Auf der Server-Konsole**: der Notweg, wenn die App nicht startet, der Datenbank-Benutzer
   keine Datenbanken anlegen darf oder die Schlüssel nicht passen.

## Was auf dem Stick und dem Server liegt

| Datei | Inhalt |
|---|---|
| Stick `snapshots/snapshot-<Zeit>Z.shb` | verschlüsselte Sicherung: `manifest.json`, Datenbank-Abzug (`database.dump`) und das ganze Schlüsselverzeichnis des Servers (`keys/`) |
| Stick `snapshots/…shb.sha256` | Prüfsumme der Datei |
| Stick `journal/journal-<Tag>.<Schlüssel>.shbj` | verschlüsselte Mitschrift: alle Ergebnis-Ereignisse des Tages (UTC), auch die nach der letzten Sicherung |
| Server `DATA_DIR/backups/snapshots/snapshot-<Zeit>Z.dump` | lokaler Abzug, **ohne** Schlüssel |
| Server `DATA_DIR/backups/pre-restore/…dump` | Stand unmittelbar vor einer Wiederherstellung in der App (wird nicht rotiert) |
| Server `DATA_DIR/backups/journal/journal-<Tag>.ndjson` | lokale Mitschrift |

Im Schlüsselverzeichnis stecken der **Namensschlüssel** `field-keys.json` (Namen und
Mitgliedsnummern sind damit in der Datenbank verschlüsselt) und der Sicherungsschlüssel
`backup-key.json`. Ohne den Namensschlüssel startet der Server nicht, sobald es Personen gibt
(„Die Schlüsseldatei … fehlt“). Ein lokaler Abzug hilft deshalb nur, solange `DATA_DIR/keys`
noch vorhanden ist.

Die Mitschrift enthält nur Ergebnis-Ereignisse (Start, Startnummer, Rohwerte, Grund, Zeit), aber
keine Namen, keine Personen, Anmeldungen oder Starts und keine Änderungen an Turnier oder Wertung.

## Weg 1: in der App

Nur ein **angemeldeter Administrator** (Recht „Sicherung wiederherstellen“, `backup.restore`)
sieht diesen Weg. Die Standardrolle eines Geräts genügt nie. Die Turnierleitung darf die Sicherung
nur auslösen („Jetzt sichern“), nicht einrichten und nicht wiederherstellen.

1. **Sicherung wählen.** Die Liste zeigt alle Sicherungen auf dem Stick und dem Server, die
   neueste zuerst, mit Zeitpunkt, Ort, Größe, ob eine Prüfsumme und eine Mitschrift vorliegen.
2. **Prüfen lassen.** Für Sicherungen vom Stick das Sicherungspasswort eingeben. Die App prüft
   Prüfsumme und Passwort und zeigt eine Vorschau:
   - Zeitpunkt der Sicherung, App-Version und Datenbank-Stand. Eine ältere Sicherung wird nach dem
     Einspielen auf den Stand der App gebracht. Eine Sicherung einer **neueren** App wird abgelehnt.
   - die Turniere der Sicherung mit Status, Zahl der Starts und abgeschlossenen Ergebnisse,
   - den Vergleich mit dem jetzigen Stand: „Seit dieser Sicherung sind N Ergebnis-Ereignisse
     hinzugekommen; davon stehen M in der Mitschrift und werden nachgetragen, K gehen verloren“,
     mit Gründen (Start erst nach der Sicherung gebucht, nicht in der Mitschrift) und der Zahl der
     Starts, die nach der Sicherung gebucht wurden,
   - was mit den Schlüsseln geschieht und was mit deinem Zugang geschieht (siehe unten).
3. **Bestätigen.** Die App führt dann der Reihe nach aus und zeigt jeden Schritt an:
   1. Sicherung erneut prüfen.
   2. **Eingaben anhalten.** Ab hier lehnt der Server Eingaben an allen Stationen ab („Die
      Sicherung wird gerade wiederhergestellt …“). Begonnene Eingaben dürfen noch fertig werden.
   3. **Jetzigen Stand sichern.** Schlägt das fehl, bricht die Wiederherstellung ab. Die Sicherung
      liegt danach zusätzlich unter `DATA_DIR/backups/pre-restore`.
   4. Abzug in eine **neue** Datenbank einspielen. Die laufende Datenbank bleibt unberührt.
   5. Bei einer älteren Sicherung: die neue Datenbank aktualisieren.
   6. Mitschrift nachtragen (wie auf der Konsole, Bericht siehe unten).
   7. Neue Datenbank prüfen (Datenbank-Stand, Administrator-Rolle, Namen lesbar).
   8. **Datenbank tauschen.** Wenige Sekunden lang antwortet der Server gar nicht. Die bisherige
      Datenbank bleibt unter dem Namen `<name>_pre_restore_<Zeit>` erhalten. Danach laufen alle
      Module wie nach einem Neustart.
   9. Protokolleintrag „Sicherung wiederhergestellt“, sofort eine neue Sicherung, Eingaben wieder frei.

Schlägt ein Schritt vor dem Tausch fehl (falsches Passwort, beschädigte Datei, kein Platz …),
wird die neue Datenbank gelöscht. Die laufende ist dann unverändert, auch die Eingaben sind wieder
frei. Es läuft immer nur eine Wiederherstellung.

**Ergebnisbericht:** wie auf der Konsole („N Ereignisse nachgetragen, K waren schon in der
Sicherung, M übersprungen …“), dazu der Name der alten Datenbank und der Sicherung „vor
Wiederherstellung“. Was danach noch fehlt, steht unter
[Was von Hand nachzutragen ist](#was-von-hand-nachzutragen-ist).

### Was nicht zurückgespielt wird

- **Einrichtung der Sicherung** (Ziel, Takt, Verschlüsselung) und das **heutige
  Sicherungspasswort** bleiben. Sie gehören zum Server, nicht zum Datenstand.
- **Berechtigungsprüfung:** Ist sie jetzt eingeschaltet, bleibt sie eingeschaltet, auch wenn sie
  in der Sicherung aus war. Ausschalten geht nur auf der Konsole. War sie in der Sicherung an und
  ist jetzt aus, ist sie danach an.
- **Schlüssel:** Vorhandene Schlüssel werden nie überschrieben. Fehlende kommen aus der Sicherung.
  Enthält der Namensschlüssel des Servers alle Schlüssel der Sicherung (Schlüsselwechsel nach der
  Sicherung), bleibt er. Gibt es noch keine Personen, ist der Namensschlüssel des Servers unbenutzt.
  Er wird dann umbenannt (`field-keys.json.unused-<Zeit>`) und der aus der Sicherung verwendet. In
  allen anderen Fällen lehnt die App ab: Konsole verwenden.

### Zugang nach der Wiederherstellung

Konten, Rollen, Geräte und Anmeldungen kommen aus der Sicherung. Die Vorschau sagt, was das für dich
bedeutet:

- **Konto und Gerät sind in der Sicherung:** Du bleibst angemeldet. Fehlt deine Anmeldung in der
  Sicherung, meldest du dich neu an, mit der PIN, die zur Zeit der Sicherung galt. Die Vorschau
  warnt, wenn sich deine PIN seitdem geändert hat.
- **Dein Konto, deine Administrator-Rolle oder dieses Gerät fehlt in der Sicherung:** Du kommst
  an diesem Gerät danach nicht mehr in die Verwaltung. Die App verlangt dafür eine eigene
  Bestätigung. Danach hilft ein anderer Administrator aus der Sicherung, oder der Notzugang auf der
  Server-Konsole:

  ```bash
  docker compose exec backend python -m app.modules.auth.cli ensure-admin "Name"
  docker compose exec backend python -m app.modules.auth.cli pairing-code --name "Laptop"
  ```

- Ist die Berechtigungsprüfung aus, ändert sich am Zugang nichts.

### Voraussetzung: Rechte des Datenbank-Benutzers

Die App legt eine Datenbank an und benennt Datenbanken um. Ihr Datenbank-Benutzer braucht dafür
`CREATEDB` und muss Eigentümer der laufenden Datenbank sein. Der Benutzer aus `POSTGRES_USER` im
offiziellen PostgreSQL-Image ist Superuser und darf das. Fehlt das Recht, meldet die Vorschau es,
und es bleibt der Weg über die Konsole. Freigeben auf dem Server:

```sql
ALTER ROLE schiesshub CREATEDB;
```

Alte Datenbanken (`…_pre_restore_…`) löscht die App nie. Aufräumen, wenn alles stimmt:

```bash
docker compose exec db psql -U schiesshub -d postgres -c '\l'
docker compose exec db psql -U schiesshub -d postgres -c 'DROP DATABASE "schiesshub_pre_restore_…"'
```

## Weg 2: auf der Konsole (Notweg)

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

   Ist die Sicherung älter als die App, vor dem Umstellen die neue Datenbank aktualisieren:
   `docker compose exec -e DATABASE_URL=…/schiesshub_neu backend alembic upgrade heads`
   (der Server macht das beim Start sonst selbst).

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

Gilt für beide Wege. Was nach der Sicherung geschah und nicht in der Mitschrift steht:

- **Starts aus der Ausgabe „übersprungen, weil der Start in der Sicherung fehlt“:** Diese Starts
  wurden erst nach der Sicherung gebucht. Person anlegen, anmelden, Start buchen, Ergebnis vom
  Startzettel erfassen. Die Rohwerte stehen auch in der Mitschrift:
  `python -m app.modules.backup.restore /backup-usb/journal/journal-<Tag>.<Schlüssel>.shbj --output /tmp/mitschrift.ndjson`
  (je Zeile ein Ereignis, mit `start_number` und `payload.raw`). Nach einer Wiederherstellung in
  der App steht außerdem der ganze vorherige Stand in der alten Datenbank `…_pre_restore_…`.
- **„nicht nachgetragen, weil die Mitschrift nicht zur Datenbank passt“:** Den Start in der
  Erfassung öffnen und mit dem Startzettel abgleichen.
- **„Die Wertung von … wurde nach der Sicherung geändert“:** die Änderung im Turnier wiederholen.
  Die Ergebnisse werden dann neu berechnet.
- **Ohne Meldung verloren:** neue Personen, Anmeldungen, Startgeld, Durchgänge, Schützenstände und
  Aufrufe sowie Änderungen an Turnier, Anzeigen, Rollen und Geräten nach der Sicherung.
  Nachgetragene Korrekturen und Abbrüche bekommen im System-Protokoll den Zeitpunkt des
  Nachtragens. Am Ergebnis selbst stehen Zeit, Person und Gerät der ursprünglichen Eingabe.

Die Sicherung läuft standardmäßig alle 5 Minuten. Verloren gehen also höchstens die nicht
ergebnisbezogenen Änderungen dieser Minuten.
