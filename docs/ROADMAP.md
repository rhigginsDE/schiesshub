# Roadmap

Schiesshub wird in Modulen gebaut. Die erste Version enthält nur, was ein Verein für ein einfaches Turnier braucht. Alles Weitere kommt als eigenes Modul dazu.

## Version 1: Grundfunktionen

Ziel ist ein internes Testturnier mit BDS-Fallscheibe.

- Disziplin-Katalog aus `catalog/` einlesen
- Turnier anlegen: Wettbewerbe aus dem Katalog, Klassen, Mehrfachstart, Startgeld als Betrag
- Anmeldung: Teilnehmer erfassen, Starts buchen, zu zahlenden Betrag anzeigen
- Ablauf am Stand je Wettbewerb einstellbar: Reihenfolge ohne feste Zeiten oder Zeitplan mit Durchgängen
- Erfassungsterminal: Einzelschuss oder Seriensumme, Zeit und Zuschläge
- Wertung, Ranglisten je Wettbewerb und Klasse
- Anzeige am Bildschirm: Startliste, Live-Wertung, Siegerliste
- Export: Startliste und Siegerliste als PDF und CSV
- Rollen und Geräte-Kopplung
- Verschlüsselte Sicherung auf USB-Stick mit Warnung, wenn der Stick fehlt
- Helles und dunkles Design, Oberfläche auf Deutsch

## Geplante Module

Die Reihenfolge ist offen. Zu jedem Modul gibt es ein Issue mit den Labels `modul` und `geplant`. Dort ist Platz für Wünsche und Erfahrungen; wer mitarbeiten will, meldet sich bitte vorher dort.

| Modul | Inhalt | Issue |
|---|---|---|
| Kasse | Zahlungen verbuchen, Zahlarten, Tagesabschluss | [#1](https://github.com/rhigginsDE/schiesshub/issues/1) |
| Startzettel | Ausdruck mit QR-Code, optional über Bondrucker | [#2](https://github.com/rhigginsDE/schiesshub/issues/2) |
| Voranmeldung | Anmeldung vor dem Wettkampftag, Import einer fertigen Turnier-Konfiguration | [#3](https://github.com/rhigginsDE/schiesshub/issues/3) |
| Mannschaftswertung | Mannschaften bilden und werten | [#4](https://github.com/rhigginsDE/schiesshub/issues/4) |
| Urkunden | Vorlagen und Ausdruck | [#5](https://github.com/rhigginsDE/schiesshub/issues/5) |
| Ergebnisse im Internet | Ergebnislisten veröffentlichen | [#6](https://github.com/rhigginsDE/schiesshub/issues/6) |
| Verbandsportal | Austausch mit dem Meisterschaftsportal des BDS | [#7](https://github.com/rhigginsDE/schiesshub/issues/7) |
| Elektronische Scheiben | Ergebnisse aus Messanlagen übernehmen | [#8](https://github.com/rhigginsDE/schiesshub/issues/8) |
| Kamera-Auswertung | Treffer per Kamera erkennen | [#9](https://github.com/rhigginsDE/schiesshub/issues/9) |
| Weitere Verbände | Kataloge für DSB, BDMP und andere | [#10](https://github.com/rhigginsDE/schiesshub/issues/10) |
| Weitere BDS-Teile | IPSC, Steel Challenge, Western, Wurfscheibe, Long Range | [#11](https://github.com/rhigginsDE/schiesshub/issues/11) |

## Betrieb des Servers

- WLAN: Der Server soll selbst Access Point sein und optional Internet vom LAN-Anschluss weitergeben
- Anzeige im Kiosk-Modus am HDMI- oder DisplayPort-Ausgang
- Installation und Updates ohne Internet
- Hardware-Empfehlungen

## Offene Fragen

- Wie das Sicherungspasswort verwaltet wird, wenn mehrere Personen wiederherstellen können sollen
- Gleichstand bei Speed und Fallscheibe: Das Sporthandbuch nennt keine Regel
- Einrichtung des Zertifikats auf Tablets und Handys möglichst ohne Handarbeit
