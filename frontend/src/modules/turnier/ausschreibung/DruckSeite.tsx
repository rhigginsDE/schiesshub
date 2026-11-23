import { Button, Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Printer } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Fehlerzustand, Leerzustand } from "../../../components/Zustand";
import { useBegriffe } from "../../../lib/begriffe";
import { uebersichtAbfrage } from "../abfragen";
import { EINRICHTEN_PFAD } from "../pfade";
import { ausschreibungAbfrage, ausschreibungDokumentAbfrage } from "./abfragen";
import s from "./ausschreibung.module.css";
import { Blatt } from "./Blatt";
import { dokumentAusEntwurf, druckModell } from "./dokument";

/**
 * Für die Dauer der Druckansicht: App ausblenden (eigenes Blatt statt App-Leiste) und helles
 * Farbschema erzwingen – Papier ist hell, egal was am Gerät eingestellt ist.
 */
function useDruckRahmen() {
  useLayoutEffect(() => {
    const wurzel = document.documentElement;
    const vorher = wurzel.getAttribute("data-mantine-color-scheme");
    wurzel.setAttribute("data-druckansicht", "");
    wurzel.setAttribute("data-mantine-color-scheme", "light");
    return () => {
      wurzel.removeAttribute("data-druckansicht");
      if (vorher) wurzel.setAttribute("data-mantine-color-scheme", vorher);
    };
  }, []);
}

export function DruckSeite({ turnierId }: { turnierId: string }) {
  const { t, i18n } = useTranslation("turnier");
  const navigate = useNavigate();
  useDruckRahmen();
  const dokument = useQuery(ausschreibungDokumentAbfrage(turnierId));
  // Ersatz, solange das Backend `…/document` nicht kennt.
  const ersatz = dokument.isSuccess && dokument.data === null;
  const entwurf = useQuery({ ...ausschreibungAbfrage(turnierId), enabled: ersatz });
  // Auch mit Dokument: liefert die Kennziffern für die Startgeld-Tabelle.
  const turnier = useQuery(uebersichtAbfrage(turnierId));
  const [erstellt] = useState(() => new Date());
  // Nur für den Ersatz ohne Server-Dokument: Begriffe der Verbände (das Dokument bringt sie mit).
  const saetze = useBegriffe();

  const modell = useMemo(() => {
    const kennziffern = new Map(
      (turnier.data?.competitions ?? []).map((w) => [w.id, w.catalog_code ?? null] as const),
    );
    if (dokument.data) return druckModell(dokument.data, i18n.language, kennziffern);
    if (ersatz && entwurf.data && turnier.data) {
      return druckModell(
        dokumentAusEntwurf(entwurf.data, turnier.data, null, i18n.language, saetze),
        i18n.language,
        kennziffern,
      );
    }
    return null;
  }, [dokument.data, ersatz, entwurf.data, turnier.data, i18n.language, saetze]);

  useEffect(() => {
    if (!modell) return;
    const vorher = document.title;
    // Der Titel wird beim „Als PDF speichern“ zum Dateinamen.
    document.title = modell.titel;
    return () => {
      document.title = vorher;
    };
  }, [modell]);

  const zurueck = () =>
    void navigate({
      to: EINRICHTEN_PFAD,
      params: { turnierId },
      search: { bereich: "ausschreibung" },
    });

  const fehler = dokument.error ?? entwurf.error ?? turnier.error;
  const fehlt = ersatz && entwurf.isSuccess && entwurf.data === null;

  return createPortal(
    // `data-aushang`: Der Katalog blendet beim Drucken alle anderen Ebenen aus (aushang.module.css).
    <div className={s.druckSeite} data-aushang="">
      <div className={s.druckLeiste}>
        <Button variant="default" leftSection={<ArrowLeft aria-hidden />} onClick={zurueck}>
          {t("ausschreibung.druck.zurueck")}
        </Button>
        <span className={s.druckHinweis}>{t("ausschreibung.druck.hinweis")}</span>
        <Button
          leftSection={<Printer aria-hidden />}
          disabled={!modell}
          onClick={() => window.print()}
        >
          {t("ausschreibung.druck.drucken")}
        </Button>
      </div>
      <main className={s.druckPapier}>
        {fehler ? (
          <Fehlerzustand fehler={fehler} onErneut={() => void dokument.refetch()} />
        ) : fehlt ? (
          <Leerzustand
            icon={Printer}
            titel={t("ausschreibung.nicht_verfuegbar_titel")}
            text={t("ausschreibung.nicht_verfuegbar_text")}
          />
        ) : modell ? (
          <Blatt modell={modell} erstellt={erstellt} />
        ) : (
          <Skeleton height={600} />
        )}
      </main>
    </div>,
    document.body,
  );
}
