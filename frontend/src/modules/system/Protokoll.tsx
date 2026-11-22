import { Pagination, Skeleton } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  geraeteAbfrage,
  personenAbfrage,
  protokollAbfrage,
  rollenAbfrage,
} from "../../api/abfragen";
import type { AuditEintrag } from "../../api/typenSystem";
import { useDarf } from "../../app/berechtigungen";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { formatZahl } from "../../lib/format";
import { formatZeitpunkt } from "./format";
import { textSchluessel } from "./rollenMatrix";
import s from "./system.module.css";

export const PROTOKOLL_SEITE = 50;

/** Übersetzungen für `detailsText`; ohne Angabe bleiben Schlüssel und Werte roh. */
export interface DetailsHilfen {
  /** Beschriftung eines Felds, z. B. `fee_cents` → „Startgeld“ */
  feld: (schluessel: string) => string;
  /** Klartext eines Werts, z. B. `dns` → „nicht angetreten“ */
  wert: (wert: string) => string;
  /** Name zu einer ID, soweit bekannt */
  name: (id: string) => string | undefined;
  /** Cent als Betrag, z. B. `800` → „8,00 €“ */
  geld: (cent: number) => string;
  jaNein: (wert: boolean) => string;
}

const ROH: DetailsHilfen = {
  feld: (schluessel) => schluessel,
  wert: (wert) => wert,
  name: () => undefined,
  geld: (cent) => String(cent),
  jaNein: (wert) => String(wert),
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** Nur solche Werte sind Fachbegriffe des Servers (`dns`, `called`), alles andere bleibt, wie es ist. */
const CODE = /^[a-z][a-z_.*]*$/;

function leer(wert: unknown): boolean {
  return (
    wert === null || wert === undefined || wert === "" || (Array.isArray(wert) && !wert.length)
  );
}

/** Ein Wert in Klartext, IDs nur als Name; `null`, wenn nichts Lesbares übrig bleibt. */
function wertText(wert: unknown, h: DetailsHilfen, geld: boolean): string | null {
  if (leer(wert)) return null;
  if (typeof wert === "boolean") return h.jaNein(wert);
  if (typeof wert === "number") return geld ? h.geld(wert) : String(wert);
  if (typeof wert === "string") {
    if (UUID.test(wert)) return h.name(wert) ?? null;
    return CODE.test(wert) ? h.wert(wert) : wert;
  }
  if (Array.isArray(wert)) {
    const teile = wert.map((teil) => wertText(teil, h, geld)).filter((teil) => teil !== null);
    return teile.length ? teile.join(geld ? " + " : ", ") : null;
  }
  if (typeof wert === "object") {
    const objekt = wert as Record<string, unknown>;
    if ("before" in objekt && "after" in objekt && Object.keys(objekt).length === 2) {
      const vorher = wertText(objekt.before, h, geld) ?? "–";
      const nachher = wertText(objekt.after, h, geld) ?? "–";
      return `${vorher} → ${nachher}`;
    }
    const text = detailsText(objekt, h);
    return text ? text.replaceAll(" · ", ", ") : null;
  }
  return String(wert);
}

/**
 * Details eines Protokolleintrags kurz als „Feld: Wert · Feld: Wert“. IDs erscheinen nur, wenn
 * ein Name bekannt ist; Startgeld in Euro.
 */
export function detailsText(details: Record<string, unknown>, h: DetailsHilfen = ROH): string {
  return Object.entries(details)
    .map(([schluessel, wert]) => {
      const text = wertText(wert, h, schluessel.endsWith("_cents"));
      // IDs ohne bekannten Namen fallen in `wertText` weg; sie sagen niemandem etwas.
      return text === null ? null : `${h.feld(schluessel)}: ${text}`;
    })
    .filter((teil) => teil !== null)
    .join(" · ");
}

export function ProtokollBereich({
  seite,
  onSeite,
}: {
  seite: number;
  onSeite: (seite: number) => void;
}) {
  const { t, i18n } = useTranslation("system");
  const offset = (seite - 1) * PROTOKOLL_SEITE;
  const protokoll = useQuery({
    ...protokollAbfrage(PROTOKOLL_SEITE, offset),
    placeholderData: keepPreviousData,
  });
  // Namen statt IDs, soweit lesbar.
  const personen = useQuery({ ...personenAbfrage(), enabled: useDarf("user.manage") });
  const geraete = useQuery({ ...geraeteAbfrage(), enabled: useDarf("device.manage") });
  const rollen = useQuery({ ...rollenAbfrage(), enabled: useDarf("role.manage") });
  const namen = useMemo(() => {
    const karte = new Map<string, string>();
    for (const person of personen.data ?? []) karte.set(person.id, person.name);
    for (const geraet of geraete.data ?? []) karte.set(geraet.id, geraet.name);
    for (const rolle of rollen.data ?? []) karte.set(rolle.id, rolle.name);
    return karte;
  }, [personen.data, geraete.data, rollen.data]);

  const hilfen: DetailsHilfen = {
    feld: (schluessel) => t(`protokoll.felder.${schluessel}`, { defaultValue: schluessel }),
    wert: (wert) =>
      t(`protokoll.werte.${wert}`, {
        defaultValue: t(`berechtigungen.${textSchluessel(wert)}`, { defaultValue: wert }),
      }),
    name: (id) => namen.get(id),
    geld: (cent) =>
      t("protokoll.euro", { betrag: formatZahl(cent / 100, { nachkommastellen: 2 }, sprache) }),
    jaNein: (wert) => (wert ? t("allgemein.ja") : t("allgemein.nein")),
  };

  const wer = (eintrag: AuditEintrag) => {
    if (eintrag.user_id) return namen.get(eintrag.user_id) ?? t("protokoll.unbekannt");
    if (eintrag.device_id)
      return t("protokoll.geraet", {
        name: namen.get(eintrag.device_id) ?? t("protokoll.unbekannt"),
      });
    return t("protokoll.system");
  };

  const sprache = i18n.language;
  const gesamt = protokoll.data?.total ?? 0;
  const seiten = Math.max(1, Math.ceil(gesamt / PROTOKOLL_SEITE));

  return (
    <section className="panel" aria-labelledby="protokoll-titel">
      <h2 className="h-section" id="protokoll-titel">
        {t("protokoll.titel")}
      </h2>
      <p className={s.einleitung}>{t("protokoll.einleitung")}</p>
      {protokoll.isPending ? (
        <Skeleton height={320} radius="md" />
      ) : protokoll.isError ? (
        <Fehlerzustand fehler={protokoll.error} onErneut={() => void protokoll.refetch()} />
      ) : protokoll.data.items.length === 0 ? (
        <Leerzustand
          icon={ScrollText}
          titel={t("protokoll.leer_titel")}
          text={t("protokoll.leer_text")}
        />
      ) : (
        <>
          <ul className={s.protokoll} aria-labelledby="protokoll-titel">
            <li className={`${s.protokollZeile} ${s.protokollKopf}`} aria-hidden>
              <span>{t("protokoll.zeit")}</span>
              <span>{t("protokoll.aktion")}</span>
              <span>{t("protokoll.wer")}</span>
              <span>{t("protokoll.details")}</span>
            </li>
            {protokoll.data.items.map((eintrag) => (
              <li
                key={eintrag.id}
                className={s.protokollZeile}
                style={{ opacity: protokoll.isPlaceholderData ? 0.6 : 1 }}
              >
                <span className="num">{formatZeitpunkt(eintrag.at, sprache)}</span>
                <span>
                  <strong>
                    {t(`protokoll.aktionen.${textSchluessel(eintrag.action)}`, {
                      defaultValue: eintrag.action,
                    })}
                  </strong>
                  <span className="gedaempft">
                    {" · "}
                    {t(`protokoll.gegenstaende.${eintrag.entity}`, {
                      defaultValue: eintrag.entity,
                    })}
                    {eintrag.entity_id && namen.has(eintrag.entity_id)
                      ? ` ${namen.get(eintrag.entity_id)}`
                      : ""}
                  </span>
                </span>
                <span>{wer(eintrag)}</span>
                <span className={s.details}>{detailsText(eintrag.details, hilfen)}</span>
              </li>
            ))}
          </ul>
          <div className={s.seitenwahl}>
            <span className="gedaempft num">
              {t("protokoll.bereich", {
                von: formatZahl(offset + 1, {}, sprache),
                bis: formatZahl(Math.min(offset + PROTOKOLL_SEITE, gesamt), {}, sprache),
                gesamt: formatZahl(gesamt, {}, sprache),
              })}
            </span>
            {seiten > 1 && (
              <Pagination
                total={seiten}
                value={seite}
                onChange={onSeite}
                size="lg"
                siblings={1}
                aria-label={t("protokoll.seiten")}
              />
            )}
          </div>
        </>
      )}
    </section>
  );
}
