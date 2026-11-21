# Sicherheit

## Sicherheitslücke melden

Bitte melde Sicherheitslücken **nicht** in einem öffentlichen Issue, Pull Request oder Forum.

Nutze stattdessen die vertrauliche Meldung von GitHub (Private Vulnerability Reporting):

1. Öffne im Repository den Reiter **Security**.
2. Wähle **Advisories** und dann **Report a vulnerability**.
3. Beschreibe die Lücke so, dass wir sie nachvollziehen können:
   - betroffener Teil (zum Beispiel Anmeldung, Sicherung, Anzeige) und Stand (Commit oder Datum)
   - Schritte zum Nachstellen
   - was ein Angreifer damit erreichen könnte
   - wenn möglich ein Vorschlag zur Behebung

Direktlink: <https://github.com/rhigginsDE/schiesshub/security/advisories/new>

Die Meldung sehen nur du und die Inhaber des Repositorys. Schiesshub ist ein Freiwilligenprojekt. Wir antworten so bald wie möglich, können aber keine festen Fristen zusagen. Bitte gib uns Zeit für eine Lösung, bevor du Details veröffentlichst. Wir nennen dich auf Wunsch, wenn wir die Lücke beheben.

Bitte keine echten Personendaten in die Meldung kopieren, auch keine Auszüge aus einer Vereinsdatenbank.

## Unterstützte Versionen

Schiesshub ist in früher Entwicklung und noch nicht für echte Wettkämpfe geeignet. Es gibt noch keine Releases.

| Stand | Sicherheitskorrekturen |
|---|---|
| aktueller Stand von `main` | ja |
| ältere Commits, Forks | nein |

Sobald es Releases gibt, steht hier, welche Versionen Korrekturen erhalten.

## Hinweise für Vereine, die Schiesshub betreiben

Schiesshub ist für den Betrieb auf einem eigenen Rechner im Vereinsheim gedacht. Was du als Betreiber tun kannst:

**Netz**

- Den Server nur im lokalen Netz des Vereinsheims betreiben. Keine Portfreigabe im Router, kein Zugriff aus dem Internet.
- Das WLAN mit einem eigenen, starken Passwort schützen (WPA2 oder WPA3). Gäste-WLAN und Wettkampf-WLAN trennen, wenn möglich.
- Nur Geräte koppeln, die der Verein kennt. Nicht mehr benötigte Geräte entfernen.

**Passwörter und PINs**

- Die Werte aus `.env.example` sind nur für die Entwicklung. Auf einem echten Server eigene, lange Passwörter setzen.
- Jede Person bekommt eine eigene PIN. PINs nicht weitergeben und nicht aufschreiben, wo andere sie sehen.
- Rollen sparsam vergeben: Wer nur erfasst, braucht keine Administrator-Rolle.

**Sicherung auf USB-Stick**

- Das Sicherungspasswort sicher und getrennt vom Stick aufbewahren, zum Beispiel versiegelt beim Vorstand. Ohne Passwort ist eine Wiederherstellung nicht möglich.
- Den Stick nach dem Wettkampf abziehen und sicher verwahren. Nicht für andere Zwecke verwenden.
- Geht ein Stick verloren, prüfen, ob eine Datenschutzverletzung zu melden ist. Siehe [docs/DATENSCHUTZ.md](docs/DATENSCHUTZ.md).

**Allgemein**

- Den Server aktuell halten: Betriebssystem und Schiesshub regelmäßig aktualisieren.
- Den Rechner so aufstellen, dass Unbefugte keinen direkten Zugang haben.
- Die Funktionen dazu werden gerade gebaut. Was schon vorhanden und was geplant ist, steht in der [Roadmap](docs/ROADMAP.md) und der [Architektur](docs/ARCHITEKTUR.md).
