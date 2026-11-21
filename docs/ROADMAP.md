# Roadmap

Schiesshub wird in Modulen gebaut. Die erste Version enthält nur, was ein Verein für ein einfaches Turnier braucht. Alles Weitere kommt als eigenes Modul dazu.

## Version 1: Grundfunktionen

Ziel ist ein internes Testturnier mit BDS-Fallscheibe.

- Disziplin-Katalog aus `catalog/` einlesen
- Turnier anlegen: Wettbewerbe aus dem Katalog, Klassen, Mehrfachstart, Startgeld als Betrag
- Anmeldung: Teilnehmer erfassen, Starts buchen, zu zahlenden Betrag anzeigen
- Reihenfolge am Stand ohne feste Zeiten
- Erfassungsterminal: Einzelschuss oder Seriensumme, Zeit und Zuschläge
- Wertung, Ranglisten je Wettbewerb und Klasse
- Anzeige am Bildschirm: Startliste, Live-Wertung, Siegerliste
- Export: Startliste und Siegerliste als PDF und CSV
- Rollen und Geräte-Kopplung
- Verschlüsselte Sicherung auf USB-Stick mit Warnung, wenn der Stick fehlt
- Helles und dunkles Design, Oberfläche auf Deutsch

## Geplante Module

Die Reihenfolge ist offen. Wer an einem Modul mitarbeiten will, meldet sich bitte vorher in einem Issue.

| Modul | Inhalt |
|---|---|
| Kasse | Zahlungen verbuchen, Zahlarten, Tagesabschluss |
| Startzettel | Ausdruck mit QR-Code, optional über Bondrucker |
| Voranmeldung | Anmeldung vor dem Wettkampftag, Import einer fertigen Turnier-Konfiguration |
| Mannschaftswertung | Mannschaften bilden und werten |
| Urkunden | Vorlagen und Ausdruck |
| Ergebnisse im Internet | Ergebnislisten veröffentlichen |
| Verbandsportal | Austausch mit dem Meisterschaftsportal des BDS |
| Elektronische Scheiben | Ergebnisse aus Messanlagen übernehmen |
| Kamera-Auswertung | Treffer per Kamera erkennen |
| Weitere Verbände | Kataloge für DSB, BDMP und andere |
| Weitere BDS-Teile | IPSC, Steel Challenge, Western, Wurfscheibe, Long Range |

## Betrieb des Servers

- WLAN: Der Server soll selbst Access Point sein und optional Internet vom LAN-Anschluss weitergeben
- Anzeige im Kiosk-Modus am HDMI- oder DisplayPort-Ausgang
- Installation und Updates ohne Internet
- Hardware-Empfehlungen

## Offene Fragen

- Wie das Sicherungspasswort verwaltet wird, wenn mehrere Personen wiederherstellen können sollen
- Gleichstand bei Speed und Fallscheibe: Das Sporthandbuch nennt keine Regel
- Einrichtung des Zertifikats auf Tablets und Handys möglichst ohne Handarbeit
