/**
 * CSV im Browser: nur für die Importvorschau (Name und Verein je Zeile anzeigen) und die
 * Beispieldatei. Geprüft und gespeichert wird ausschließlich auf dem Server.
 */

export interface CsvDatensatz {
  /** Physische Zeile, in der der Datensatz endet (wie `line_num` des Python-CSV-Lesers) */
  zeile: number;
  zellen: string[];
}

/** Trennzeichen wie das Backend: aus der ersten nicht leeren Zeile, `;` gewinnt bei Gleichstand. */
export function trennzeichen(text: string): ";" | "," {
  const kopf = text.split(/\r\n|\n|\r/).find((zeile) => zeile.trim() !== "") ?? "";
  const komma = kopf.split(",").length - 1;
  const semikolon = kopf.split(";").length - 1;
  return komma > semikolon ? "," : ";";
}

/** Liest CSV nach RFC 4180 (Anführungszeichen, verdoppelte Anführungszeichen, Umbrüche in Feldern). */
export function csvLesen(eingabe: string): CsvDatensatz[] {
  const text = eingabe.startsWith("﻿") ? eingabe.slice(1) : eingabe;
  const trenner = trennzeichen(text);
  const datensaetze: CsvDatensatz[] = [];
  let zellen: string[] = [];
  let zelle = "";
  let inAnfuehrung = false;
  let zeile = 1;
  let begonnen = false;

  const zelleFertig = () => {
    zellen.push(zelle);
    zelle = "";
  };
  const datensatzFertig = () => {
    zelleFertig();
    datensaetze.push({ zeile, zellen });
    zellen = [];
    begonnen = false;
  };

  for (let i = 0; i < text.length; i += 1) {
    const zeichen = text[i];
    if (inAnfuehrung) {
      if (zeichen === '"') {
        if (text[i + 1] === '"') {
          zelle += '"';
          i += 1;
        } else {
          inAnfuehrung = false;
        }
      } else {
        if (zeichen === "\n" || (zeichen === "\r" && text[i + 1] !== "\n")) zeile += 1;
        zelle += zeichen;
      }
      continue;
    }
    if (zeichen === '"' && zelle === "") {
      inAnfuehrung = true;
      begonnen = true;
    } else if (zeichen === trenner) {
      begonnen = true;
      zelleFertig();
    } else if (zeichen === "\r" || zeichen === "\n") {
      if (zeichen === "\r" && text[i + 1] === "\n") i += 1;
      datensatzFertig();
      zeile += 1;
    } else {
      begonnen = true;
      zelle += zeichen;
    }
  }
  if (begonnen || zelle !== "" || zellen.length > 0) datensatzFertig();
  return datensaetze;
}

const NAME_SPALTEN = new Set(["name"]);
const VEREIN_SPALTEN = new Set(["club", "verein"]);

function spaltenname(roh: string): string {
  return roh.trim().toLowerCase().split(/\s+/).join(" ");
}

export interface VorschauZeile {
  name: string;
  verein: string;
}

/** Name und Verein je Zeilennummer, um die Ergebnisse des Servers lesbar zu machen. */
export function vorschauZeilen(text: string): Map<number, VorschauZeile> {
  const ergebnis = new Map<number, VorschauZeile>();
  const datensaetze = csvLesen(text).filter((d) => d.zellen.some((z) => z.trim() !== ""));
  const [kopf, ...rest] = datensaetze;
  if (!kopf) return ergebnis;
  const spalten = kopf.zellen.map(spaltenname);
  const nameIndex = spalten.findIndex((s) => NAME_SPALTEN.has(s));
  const vereinIndex = spalten.findIndex((s) => VEREIN_SPALTEN.has(s));
  const ohneSchutz = (wert: string) =>
    wert.length > 1 && wert[0] === "'" && "=+-@".includes(wert[1] ?? "") ? wert.slice(1) : wert;
  for (const datensatz of rest) {
    ergebnis.set(datensatz.zeile, {
      name: nameIndex >= 0 ? ohneSchutz(datensatz.zellen[nameIndex]?.trim() ?? "") : "",
      verein: vereinIndex >= 0 ? ohneSchutz(datensatz.zellen[vereinIndex]?.trim() ?? "") : "",
    });
  }
  return ergebnis;
}

/** Beispieldatei mit erfundenen Personen (deutsche Spaltennamen, wie der Import sie versteht). */
export function beispielCsv(): string {
  const zeilen = [
    ["Name", "Verein", "Mitgliedsnummer", "Anzeige", "Verein anzeigen"],
    ["Erika Beispiel", "SV Tell Musterstadt", "10 0001", "voll", "ja"],
    ["Max Mustermann", "SSV Hubertus Altdorf", "", "kurz", "ja"],
    ["Lena Probe", "SGi Neustadt 1862", "20 0042", "voll", "nein"],
    ["Hans-Peter Vorlage", "", "", "verborgen", ""],
  ];
  return `﻿${zeilen.map((zeile) => zeile.join(";")).join("\r\n")}\r\n`;
}

/** Bietet einen Text als Datei zum Speichern an (im Browser erzeugt, ohne Server). */
export function dateiAnbieten(dateiname: string, inhalt: string, typ = "text/csv;charset=utf-8") {
  blobAnbieten(dateiname, new Blob([inhalt], { type: typ }));
}

/** Bietet Daten als Datei zum Speichern an. */
export function blobAnbieten(dateiname: string, inhalt: Blob) {
  const url = URL.createObjectURL(inhalt);
  const link = document.createElement("a");
  link.href = url;
  link.download = dateiname;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
