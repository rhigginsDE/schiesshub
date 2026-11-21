import { Pagination, Skeleton } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { geraeteAbfrage, personenAbfrage, protokollAbfrage } from "../../api/abfragen";
import type { AuditEintrag } from "../../api/typenSystem";
import { useDarf } from "../../app/berechtigungen";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { formatZahl } from "../../lib/format";
import { formatZeitpunkt } from "./format";
import { textSchluessel } from "./rollenMatrix";
import s from "./system.module.css";

export const PROTOKOLL_SEITE = 50;

/** Details kurz als „schlüssel: wert“; verschachtelte Werte als JSON. */
export function detailsText(details: Record<string, unknown>): string {
  return Object.entries(details)
    .filter(([, wert]) => wert !== null && wert !== undefined && wert !== "")
    .map(
      ([schluessel, wert]) =>
        `${schluessel}: ${typeof wert === "object" ? JSON.stringify(wert) : String(wert)}`,
    )
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
  const namen = useMemo(() => {
    const karte = new Map<string, string>();
    for (const person of personen.data ?? []) karte.set(person.id, person.name);
    for (const geraet of geraete.data ?? []) karte.set(geraet.id, geraet.name);
    return karte;
  }, [personen.data, geraete.data]);

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
                <span className={s.details}>{detailsText(eintrag.details)}</span>
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
