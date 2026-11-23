import { Fragment } from "react";
import { useTranslation } from "react-i18next";
import { formatDatum } from "../../../lib/format";
import s from "./ausschreibung.module.css";
import type { DruckBaustein, DruckModell } from "./dokument";

interface BlattProps {
  modell: DruckModell;
  /** Datum im Fuß („Stand …“) */
  erstellt: Date;
}

/** Die Ausschreibung als Blatt: dieselbe Darstellung für Vorschau und Druck. */
export function Blatt({ modell, erstellt }: BlattProps) {
  const { t, i18n } = useTranslation("turnier");
  return (
    <article className={s.blatt}>
      <header className={s.blattKopf}>
        {modell.veranstalter && <p className={s.absender}>{modell.veranstalter}</p>}
        <h1>{modell.titel}</h1>
        <p className={s.unterzeile}>
          {modell.turnier} · <span className="num">{modell.zeitraum}</span>
        </p>
      </header>

      {modell.eckdaten.length > 0 && (
        <dl className={s.eckdaten}>
          {modell.eckdaten.map((zeile) => (
            <div key={zeile.bezeichnung}>
              <dt>{zeile.bezeichnung}</dt>
              <dd>{zeile.text}</dd>
            </div>
          ))}
        </dl>
      )}

      {modell.bausteine.map((baustein) => (
        <BausteinBlatt key={baustein.id} baustein={baustein} />
      ))}

      <footer className={s.blattFuss}>
        <span>
          {t("ausschreibung.druck.stand", { datum: formatDatum(erstellt, i18n.language) })}
        </span>
        <span>{t("ausschreibung.druck.erstellt_mit")}</span>
      </footer>
    </article>
  );
}

/** Text, der nur zwischen Wörtern umbricht (nicht an Bindestrichen wie in „15-m-Stand“). */
function Woerter({ text }: { text: string }) {
  const woerter = text.split(" ").filter(Boolean);
  // Leerzeichen zwischen den Spans: nur dort darf die Zeile umbrechen.
  return woerter.map((wort, nr) => (
    // biome-ignore lint/suspicious/noArrayIndexKey: Wörter eines festen Textes, Stelle ist eindeutig
    <Fragment key={nr}>
      {nr > 0 && " "}
      <span className={s.wort}>{wort}</span>
    </Fragment>
  ));
}

export function BausteinBlatt({ baustein }: { baustein: DruckBaustein }) {
  const { t } = useTranslation("turnier");
  return (
    <section className={s.abschnitt}>
      {baustein.ueberschrift && <h2>{baustein.ueberschrift}</h2>}

      {baustein.art === "wettbewerbe" && baustein.wettbewerbe.length > 0 && (
        <table className={s.tabelle}>
          <thead>
            <tr>
              <th scope="col">{baustein.spalten.kennziffer}</th>
              <th scope="col">{t("ausschreibung.druck.wettbewerb")}</th>
              <th scope="col">{t("ausschreibung.druck.ablauf")}</th>
              <th scope="col">{baustein.spalten.schiessstand}</th>
              {baustein.mitGeld && (
                <th scope="col" className={s.rechts}>
                  {t("ausschreibung.druck.startgeld", { startgeld: baustein.spalten.startgeld })}
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {baustein.wettbewerbe.map((w) => (
              <tr key={w.id}>
                <td className="num">{w.kennziffer}</td>
                <td>
                  <strong>{w.name}</strong>
                  <span className={s.klein}>{w.starts}</span>
                </td>
                <td>{w.ablauf}</td>
                <td>
                  <Woerter text={w.stand} />
                </td>
                {baustein.mitGeld && <td className={`num ${s.rechts}`}>{w.startgeld}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {baustein.art === "gebuehren" && baustein.zeilen.length > 0 && (
        <table className={s.tabelle}>
          <thead>
            <tr>
              <th scope="col">{t("ausschreibung.druck.wettbewerb")}</th>
              <th scope="col" className={s.rechts}>
                {t("ausschreibung.druck.erster_start")}
              </th>
              <th scope="col" className={s.rechts}>
                {t("ausschreibung.druck.nachkauf")}
              </th>
            </tr>
          </thead>
          <tbody>
            {baustein.zeilen.map((z) => (
              <tr key={z.id}>
                <td>
                  {z.kennziffer && <span className={`num ${s.kennziffer}`}>{z.kennziffer}</span>}
                  {z.name}
                </td>
                <td className={`num ${s.rechts}`}>{z.startgeld}</td>
                <td className={`num ${s.rechts}`}>{z.nachkauf ?? "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {baustein.art === "klassen" && baustein.klassen.length > 0 && (
        <ul className={s.aufzaehlung}>
          {baustein.klassen.map((k) => (
            <li key={k}>{k}</li>
          ))}
        </ul>
      )}

      {baustein.art === "staende" && baustein.zeilen.length > 0 && (
        <ul className={s.aufzaehlung}>
          {baustein.zeilen.map((z) => (
            <li key={z}>{z}</li>
          ))}
        </ul>
      )}

      {baustein.art === "termine" && baustein.zeilen.length > 0 && (
        <dl className={s.termine}>
          {baustein.zeilen.map((z) => (
            <div key={z.bezeichnung}>
              <dt>{z.bezeichnung}</dt>
              <dd className="num">{z.text}</dd>
            </div>
          ))}
        </dl>
      )}

      {baustein.absaetze.map((absatz) => (
        <p key={absatz} className={s.absatz}>
          {absatz}
        </p>
      ))}
    </section>
  );
}
