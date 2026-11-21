# Datenschutz: Hinweise für Vereine

> **Keine Rechtsberatung.** Diese Seite gibt Orientierung für Vereine, die Schiesshub betreiben. Sie ersetzt keine Prüfung im Einzelfall. Maßgeblich ist die Datenschutz-Aufsichtsbehörde des Bundeslands, in dem euer Verein seinen Sitz hat. Im Zweifel fragt euren Landesverband oder eine Fachanwältin bzw. einen Fachanwalt.

> **Stand der Software:** Schiesshub ist in früher Entwicklung. Viele der unten genannten Funktionen sind **geplant** und noch nicht vorhanden. Was es schon gibt, steht in der [Roadmap](ROADMAP.md).

## Wer ist verantwortlich?

**Der Verein**, der das Turnier ausrichtet und den Server betreibt, ist Verantwortlicher im Sinne der DSGVO (Art. 4 Nr. 7). Die Haushaltsausnahme für private Zwecke gilt für Vereine nicht.

Die Entwicklerinnen und Entwickler von Schiesshub stellen nur die Software bereit. Sie haben keinen Zugriff auf eure Daten: Schiesshub läuft auf eurem eigenen Rechner, ohne Cloud und ohne Telemetrie. Schickt deshalb bitte auch bei Fehlerberichten keine Datenbank-Auszüge oder Sicherungen mit echten Daten.

## Welche Daten verarbeitet Schiesshub?

Schiesshub ist bewusst sparsam gebaut.

| Daten | Wozu | Hinweis |
|---|---|---|
| Name der Teilnehmerin oder des Teilnehmers | Anmeldung, Startliste, Wertung | in der Datenbank verschlüsselt gespeichert (geplant) |
| Verein | Wertung, Anzeige | Anzeige je Person abschaltbar (geplant) |
| Klasse | Wertung | wird bei der Anmeldung gewählt |
| Starts, Bahn, Durchgang, Startgeld-Betrag | Ablauf am Stand | |
| Ergebnisse und Korrekturen | Wertung, Siegerliste, Einspruch | Korrekturen werden mit Person, Zeit und Grund protokolliert (geplant) |
| Helferinnen und Helfer mit Rolle und PIN | Anmeldung an den Stationen, Nachvollziehbarkeit der Erfassung | PINs nicht im Klartext speichern |

**Nicht** gespeichert werden: Geburtsdatum, Geburtsjahr, Anschrift, Telefonnummer, E-Mail, Waffen- oder WBK-Daten. Bitte tragt solche Angaben auch nicht in Freitextfelder ein. Angaben zu Gesundheit oder Behinderung (zum Beispiel „Auflage aus gesundheitlichen Gründen“) sind besonders geschützte Daten; bildet so etwas nur als neutrale Klasse ab.

## Rechtsgrundlage und Information

- Anmeldung, Startliste, Erfassung und Wertung sind in der Regel zur Durchführung des Wettkampfs erforderlich (Art. 6 Abs. 1 lit. b DSGVO).
- Informiert die Teilnehmenden **vorher**, welche Daten ihr verarbeitet und wo Ergebnisse erscheinen (Art. 13 DSGVO). Am einfachsten mit einem Hinweis in der Ausschreibung und an der Anmeldung. Eine Vorlage steht unten.
- Nehmt die Wettkampfverwaltung in euer Verzeichnis von Verarbeitungstätigkeiten auf (Art. 30 DSGVO).

## Aushang und Anzeige von Ergebnissen

- **Bildschirm und Aushang im Vereinsheim:** Startlisten und Ergebnisse während des Wettkampfs sind nach Einschätzung der Aufsichtsbehörde Baden-Württemberg in der Regel zulässig. Zeigt nur, was nötig ist: Name, Verein, Klasse, Ergebnis.
- **Ergebnisse im Internet** sind etwas anderes: ein unbestimmter Personenkreis, dauerhaft auffindbar. Nach derselben Orientierungshilfe ist das nur kurzzeitig, nach vorheriger Information und mit Widerspruchsmöglichkeit vertretbar, und nach angemessener Zeit wieder zu löschen. Schiesshub hat dafür noch keine Funktion; ein Modul ist geplant ([Issue #6](https://github.com/rhigginsDE/schiesshub/issues/6)).
- Bedenkt: Eine Disziplin in einer öffentlichen Liste kann auf Waffenbesitz schließen lassen. Wer nicht öffentlich genannt werden möchte, hat dafür einen nachvollziehbaren Grund.

## Anzeige-Einstellung je Person (geplant)

Geplant ist eine Einstellung je Person, wie sie auf der Anzeige und in Listen erscheint:

- voller Name oder abgekürzt (zum Beispiel „M. Brandt“)
- Verein anzeigen oder nicht

Bis diese Funktion da ist: Fragt bei der Anmeldung nach und berücksichtigt Wünsche von Hand, zum Beispiel bei Aushängen.

## Widerspruch, Auskunft, Löschen und Export

Teilnehmende haben unter anderem das Recht auf Auskunft (Art. 15), Berichtigung (Art. 16), Löschung (Art. 17) und Widerspruch (Art. 21 DSGVO). Eine Auskunft muss innerhalb eines Monats erfolgen.

- **Geplant:** Export aller zu einer Person gespeicherten Daten sowie Löschen oder Anonymisieren einzelner Personen und ganzer Turniere.
- **Geplant für Version 1:** Startliste und Siegerliste als PDF und CSV.
- Legt fest, wie lange ihr Ergebnisse mit Namen aufbewahrt. Es gibt keine gesetzliche Frist für Ergebnislisten; die Daten dürfen nur so lange gespeichert werden, wie ihr sie braucht, zum Beispiel für Einsprüche, Vereinsranglisten oder Meldungen an den Verband. Danach Namen löschen oder anonymisieren. Daten von Gästen anderer Vereine nach Abschluss und Einspruchsfrist besonders prüfen.

## Minderjährige

- Erfassung und Wertung sind auch bei Jugendlichen zur Durchführung des Wettkampfs nötig.
- Bei Kindern und Jugendlichen überwiegen bei einer Abwägung regelmäßig ihre Schutzinteressen. Die Aufsichtsbehörde Baden-Württemberg nennt dafür eine Grenze von 16 Jahren.
- Für die Veröffentlichung von Daten Minderjähriger **im Internet** holt eine Einwilligung der Sorgeberechtigten ein.
- Für die Anzeige im Vereinsheim ist eine zurückhaltende Darstellung sicherer, zum Beispiel abgekürzter Name (sobald die Anzeige-Einstellung vorhanden ist).
- Schiesshub speichert kein Geburtsdatum. Ob jemand minderjährig ist, ergibt sich höchstens aus der Klasse.

## Sicherung

- Geplant ist eine verschlüsselte Sicherung auf USB-Stick. Zum Wiederherstellen braucht man das Sicherungspasswort, das bei der Einrichtung festgelegt wird.
- Bewahrt Stick und Passwort getrennt und sicher auf. Ohne Passwort sind die Daten nicht wiederherstellbar.
- Geht ein Stick oder der Server verloren oder wird gestohlen, prüft, ob eine Datenschutzverletzung vorliegt. Meldepflichtige Verletzungen sind binnen 72 Stunden der Aufsichtsbehörde zu melden (Art. 33 DSGVO). Bei einer wirksam verschlüsselten Sicherung ist das Risiko für die Betroffenen deutlich geringer; dokumentiert den Vorfall trotzdem.
- Sicherungen nicht auf private Rechner oder in Cloud-Speicher kopieren.

Technische Hinweise zum sicheren Betrieb stehen in [SECURITY.md](../SECURITY.md).

## Quellen

- DSGVO: <https://eur-lex.europa.eu/eli/reg/2016/679/oj?locale=de>
- Landesbeauftragter für den Datenschutz und die Informationsfreiheit Baden-Württemberg: [Orientierungshilfe „Datenschutz im Verein nach der DSGVO“, Stand 24.06.2020](https://www.baden-wuerttemberg.datenschutz.de/wp-content/uploads/2020/06/OH-Datenschutz-im-Verein-nach-der-DSGVO.pdf) (insbesondere Nr. 1.3, 5.3, 5.6) und [Praxisratgeber für Vereine](https://www.baden-wuerttemberg.datenschutz.de/wp-content/uploads/2020/06/Praxisratgeber-f%C3%BCr-Vereine.pdf)

Andere Bundesländer können im Detail abweichen.

---

## Vorlage: Datenschutzhinweis für Teilnehmer

> Zum Anpassen. Eckige Klammern ersetzen, Nichtzutreffendes streichen. Für Ausschreibung, Anmeldung und Aushang.

**Datenschutzhinweis zum [Name des Turniers] am [Datum]**

**Verantwortlich:** [Vereinsname], [Anschrift], vertreten durch [Vorstand]. Kontakt für Datenschutzfragen: [E-Mail oder Ansprechperson]. [Falls vorhanden: Datenschutzbeauftragte/r: Kontakt.]

**Welche Daten:** Name, Verein, Klasse, gebuchte Starts, Startgeld-Betrag und Ergebnisse. Wir erfassen kein Geburtsdatum und keine Anschrift.

**Wozu:** Durchführung und Auswertung des Wettkampfs, Startliste, Siegerliste, Bearbeitung von Einsprüchen [, Meldung an den Verband: Name des Verbands].

**Rechtsgrundlage:** Art. 6 Abs. 1 lit. b DSGVO (Teilnahme am Wettkampf) [; für Veröffentlichungen im Internet Art. 6 Abs. 1 lit. f DSGVO bzw. bei Minderjährigen Einwilligung der Sorgeberechtigten].

**Wo erscheinen Ergebnisse:**

- auf dem Bildschirm und am Aushang im Vereinsheim während der Veranstaltung
- [in der Siegerliste, die an Teilnehmende ausgegeben wird]
- [auf der Website des Vereins bis [Zeitraum]]
- [in der Vereinszeitung / Presse]

Auf Wunsch zeigen wir deinen Namen abgekürzt oder ohne Verein. Sag uns das bei der Anmeldung.

**Wer hat Zugriff:** Turnierleitung und Helferinnen und Helfer des Vereins. Die Daten liegen auf einem Rechner des Vereins im Vereinsheim, nicht in einer Cloud. [Weitergabe an: Verband, falls zutreffend.]

**Wie lange:** Ergebnisse mit Namen speichern wir bis [Zeitraum, zum Beispiel Ende der nächsten Saison]. Danach löschen oder anonymisieren wir sie. [Ausnahme: Vereinsrekorde.]

**Deine Rechte:** Du kannst Auskunft über deine Daten verlangen, ihre Berichtigung oder Löschung, eine Einschränkung der Verarbeitung, und du kannst einer Veröffentlichung widersprechen. Wende dich dafür an [Kontakt]. Du kannst dich außerdem bei einer Datenschutz-Aufsichtsbehörde beschweren, zum Beispiel bei [zuständige Behörde des Bundeslands].

**Minderjährige:** Ergebnisse von Teilnehmenden unter [16] Jahren veröffentlichen wir im Internet nur mit Einwilligung der Sorgeberechtigten.
