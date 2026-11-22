import { Button, Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { TFunction } from "i18next";
import { ArrowRight, Check, ClipboardX, Unplug, UsersRound } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Chip, type ChipTon } from "../components/Chip";
import { ExportKnoepfe } from "../components/ExportKnoepfe";
import { Kachel, KachelRaster } from "../components/Kachel";
import { TurnierAuswahl, TurnierWechsel } from "../components/TurnierWahl";
import { useAktivesTurnier } from "../components/useAktivesTurnier";
import { Fehlerzustand, Leerzustand } from "../components/Zustand";
import { formatUhrzeit } from "../lib/format";
import { startlisteAbfrage } from "../modules/anmeldung/api";
import { uebersichtAbfrage } from "../modules/turnier/abfragen";
import { TurnierAnlegen } from "../modules/turnier/TurnierAnlegen";
import { offenePunkte } from "../modules/turnier/vollstaendigkeit";
import {
  type AblaufAktion,
  type AblaufSchritt,
  ablauf,
  type SchrittId,
  type SchrittStand,
  type SicherungEingabe,
  turnierFuerAblauf,
  zaehleStarts,
} from "./ablauf";
import { AnzeigeGeraetStart, useIstAnzeigeGeraet } from "./anzeigeGeraet";
import { useDarf } from "./berechtigungen";
import { type ModulManifest, useModule, useStationen } from "./modul";
import s from "./Startseite.module.css";
import { useServerStatus } from "./serverStatus";
import { useSicherungsLage } from "./sicherungsLage";

/** Module, die ein Schritt des Ablaufs abdeckt; alle anderen erscheinen unter „Weitere Bereiche“. */
const MODUL_JE_SCHRITT: Record<SchrittId, readonly string[]> = {
  turnier: ["turnier"],
  anmeldung: ["anmeldung"],
  erfassung: ["erfassung", "stand"],
  anzeige: ["anzeige"],
  sicherung: [],
};
const IM_ABLAUF = new Set(Object.values(MODUL_JE_SCHRITT).flat());

/** Aktion eines Schritts, wenn er für diese Rolle dran ist, ohne der nächste im Ablauf zu sein. */
const STANDARD_AKTION: Record<SchrittId, AblaufAktion> = {
  turnier: "turnier_einrichten",
  anmeldung: "zur_anmeldung",
  erfassung: "ergebnisse_erfassen",
  anzeige: "anzeige_oeffnen",
  sicherung: "zur_sicherung",
};

const STAND_TON: Record<SchrittStand, ChipTon> = {
  offen: "neutral",
  in_arbeit: "info",
  erledigt: "neutral",
  ok: "neutral",
  wartet: "neutral",
  gestoert: "warn",
  unbekannt: "neutral",
};

/**
 * Startseite: der Ablauf eines Turniers als Aufgabenliste (Schritte mit Zustand, der nächste ist
 * hervorgehoben und trägt die eine Hauptaktion), darunter die übrigen Bereiche. Es erscheinen nur
 * die Schritte, die die Rolle übernehmen darf. Ohne Leserecht für Turniere bleibt es bei der
 * Stationsauswahl; ein reines Anzeige-Gerät geht direkt auf seinen Bildschirm.
 */
export function Startseite() {
  const darfTurniere = useDarf("tournament.read");
  const anzeigeGeraet = useIstAnzeigeGeraet();
  if (anzeigeGeraet) return <AnzeigeGeraetStart />;
  return darfTurniere ? <AblaufSeite /> : <Stationsauswahl />;
}

/** Nichts freigegeben: sagen, warum die Seite leer ist und wer hilft. */
function KeineAufgabe() {
  const { t } = useTranslation();
  return (
    <div className="panel">
      <Leerzustand
        icon={ClipboardX}
        titel={t("shell:start.keine_aufgabe_titel")}
        text={t("shell:start.keine_aufgabe_text")}
      >
        <Button
          component={Link}
          to="/anmelden"
          variant="default"
          leftSection={<UsersRound aria-hidden />}
        >
          {t("shell:anmeldung.person_wechseln")}
        </Button>
      </Leerzustand>
    </div>
  );
}

function Stationsauswahl() {
  const { t } = useTranslation();
  const stationen = useStationen();
  const einzige = stationen.length === 1 ? stationen[0] : undefined;
  // Nur eine Station: Sie ist die Hauptaktion, mit ihrem Zweck statt einer Auswahl.
  if (einzige) {
    return (
      <div className={s.einzige}>
        <h1 className="h-display">{t(`${einzige.namensraum}:titel`)}</h1>
        <p className="gedaempft">{t(`${einzige.namensraum}:zweck`)}</p>
        <Button
          size="lg"
          rightSection={<ArrowRight aria-hidden />}
          renderRoot={(props) => <Link {...props} to={einzige.navigation.pfad} />}
        >
          {t("shell:start.zur_station", { titel: t(`${einzige.namensraum}:titel`) })}
        </Button>
      </div>
    );
  }
  return (
    <>
      <div className={s.kopf}>
        <h1 className="h-display">{t("shell:start.stationen_ueberschrift")}</h1>
        <p className="gedaempft">{t("shell:start.stationen_einleitung")}</p>
      </div>
      {stationen.length === 0 && <KeineAufgabe />}
      <KachelRaster gross>
        {stationen.map((modul) => (
          <Kachel
            key={modul.id}
            gross
            pfad={modul.navigation.pfad}
            icon={modul.navigation.icon}
            titel={t(`${modul.namensraum}:titel`)}
            text={t(`${modul.namensraum}:zweck`)}
          />
        ))}
      </KachelRaster>
    </>
  );
}

interface Ziel {
  pfad: string;
  suche?: Record<string, string>;
}

function AblaufSeite() {
  const { t, i18n } = useTranslation("shell");
  const wahl = useAktivesTurnier();
  const { verbindung } = useServerStatus();
  const module = useModule();
  const sichtbar = new Set(module.map((modul) => modul.id));
  const darfEinrichten = useDarf("tournament.edit");
  const darfStarts = useDarf("start.read");
  const darfSicherung = useDarf("backup.read") && sichtbar.has("system");
  // Ohne Rechte an der Erfassung, aber mit Aufrufen am Stand (Standaufsicht): Der Schritt führt
  // zum Stand. Wer am Stand nur liest (Kasse), übernimmt den Schritt nicht.
  const darfAufrufen = useDarf("start.call");
  const nurStand = !sichtbar.has("erfassung") && sichtbar.has("stand") && darfAufrufen;
  const sicherungsLage = useSicherungsLage(false);
  const [wechselOffen, setWechselOffen] = useState(false);
  const [anlegen, setAnlegen] = useState(false);

  const turnier = turnierFuerAblauf(wahl.turnier, wahl.turniere);
  // Startseite und Stationen meinen dasselbe Turnier: Was die Startseite zeigt, wird die Wahl
  // dieses Geräts, sobald keine (gültige) gespeichert ist. Die Stationen fragen dann nicht erneut.
  const vermutetId = wahl.turnier ? null : (turnier?.id ?? null);
  const { waehlen } = wahl;
  useEffect(() => {
    if (vermutetId) waehlen(vermutetId);
  }, [vermutetId, waehlen]);
  const uebersicht = useQuery({
    ...uebersichtAbfrage(turnier?.id ?? ""),
    enabled: turnier !== null,
  });
  const startliste = useQuery({
    ...startlisteAbfrage(turnier?.id ?? ""),
    enabled: turnier !== null && turnier.status !== "draft" && darfStarts,
  });

  const getrennt = verbindung === "getrennt";

  if (wahl.abfrage.isPending) {
    return (
      <div className={s.seite} aria-busy="true">
        <Kopf />
        <Skeleton height={420} radius="lg" aria-label={t("start.laden")} />
      </div>
    );
  }
  if (wahl.abfrage.isError) {
    return (
      <div className={s.seite}>
        <Kopf />
        <div className="panel">
          <Fehlerzustand fehler={wahl.abfrage.error} onErneut={() => void wahl.abfrage.refetch()} />
        </div>
        <WeitereBereiche module={module} />
      </div>
    );
  }

  const status = sicherungsLage.status;
  const letzte = status?.last_snapshot?.ok ? new Date(status.last_snapshot.finished_at) : null;
  const sicherung: SicherungEingabe | undefined = !status
    ? undefined
    : status.warning
      ? {
          art: "warnung",
          code: status.warning.code,
          behebbar: sicherungsLage.darfVerwalten,
          nieGesichert: letzte === null,
        }
      : letzte
        ? { art: "ok", zeit: formatUhrzeit(letzte, i18n.language) }
        : { art: "keine" };

  const lage = ablauf({
    turnier,
    offenePunkte:
      turnier?.status === "draft" && uebersicht.data ? offenePunkte(uebersicht.data) : undefined,
    wettbewerbe: uebersicht.data?.competitions.length,
    starts: startliste.data ? zaehleStarts(startliste.data) : undefined,
    sicherung,
  });

  /** Wohin Titel und Hauptaktion eines Schritts führen; `null` = keine Berechtigung. */
  const ziel = (id: SchrittId): Ziel | null => {
    switch (id) {
      case "turnier":
        if (!sichtbar.has("turnier")) return null;
        return turnier ? { pfad: `/turnier/${turnier.id}` } : { pfad: "/turnier" };
      case "anmeldung":
        return sichtbar.has("anmeldung") ? { pfad: "/anmeldung" } : null;
      case "erfassung":
        if (sichtbar.has("erfassung")) return { pfad: "/erfassung" };
        return nurStand ? { pfad: "/erfassung/stand" } : null;
      case "anzeige":
        // Die Anzeige dieses Turniers (oder deren Einrichtung), nicht irgendeine.
        if (!sichtbar.has("anzeige")) return null;
        return turnier
          ? { pfad: "/anzeige", suche: { turnier: turnier.id } }
          : { pfad: "/anzeige" };
      case "sicherung":
        return darfSicherung ? { pfad: "/system/sicherung" } : null;
    }
  };

  /**
   * Nur die Schritte, die die Rolle übernehmen darf. „Turnier einrichten“ nur mit
   * `tournament.edit`: Wer das Turnier nur ansehen darf, richtet es nicht ein.
   */
  const sichtbareSchritte = lage.schritte.filter((schritt) =>
    schritt.id === "turnier"
      ? darfEinrichten && ziel("turnier") !== null
      : ziel(schritt.id) !== null,
  );
  const alleSchritte = sichtbareSchritte.length === lage.schritte.length;
  // Ist der nächste Schritt nicht Sache dieser Rolle, ist ihr erster offener Schritt dran.
  const eigenerNaechster: AblaufSchritt | undefined =
    sichtbareSchritte.find((schritt) => schritt.id === lage.naechster) ??
    sichtbareSchritte.find(
      (schritt) =>
        schritt.id !== "sicherung" && (schritt.stand === "offen" || schritt.stand === "in_arbeit"),
    );
  const naechsteAktion: AblaufAktion | undefined = !eigenerNaechster
    ? undefined
    : eigenerNaechster.id === lage.naechster
      ? lage.aktion
      : STANDARD_AKTION[eigenerNaechster.id];

  /**
   * Die Aktion eines Schritts, sofern die Rolle sie erlaubt: grün nur für den nächsten Schritt,
   * sonst nachrangig (z. B. eine gestörte Sicherung, die noch nicht dran ist).
   */
  const schrittAktion = (id: SchrittId, aktion: AblaufAktion, haupt: boolean) => {
    const text =
      id === "erfassung" && nurStand ? t("ablauf.aktion.zum_stand") : t(`ablauf.aktion.${aktion}`);
    const pfeil = <ArrowRight aria-hidden />;
    const variante = haupt ? undefined : "default";
    if (aktion === "turnier_anlegen") {
      return darfEinrichten ? (
        <Button size="md" variant={variante} rightSection={pfeil} onClick={() => setAnlegen(true)}>
          {text}
        </Button>
      ) : null;
    }
    if ((aktion === "turnier_einrichten" || aktion === "turnier_starten") && !darfEinrichten) {
      return null;
    }
    if (aktion === "passwort_festlegen" && !sicherungsLage.darfVerwalten) return null;
    const z = ziel(id);
    if (!z) return null;
    const suche = aktion === "turnier_starten" ? { bereich: "zusammenfassung" } : z.suche;
    return (
      <Button
        size="md"
        variant={variante}
        rightSection={pfeil}
        renderRoot={(props) => <Link {...props} to={z.pfad} search={suche} />}
      >
        {text}
      </Button>
    );
  };

  return (
    <div className={s.seite}>
      <Kopf einleitung={alleSchritte ? undefined : t("start.einleitung_eigene")}>
        {turnier && <TurnierWechsel turnier={turnier} onWechseln={() => setWechselOffen(true)} />}
      </Kopf>

      {getrennt && (
        <p className={s.offline} role="status">
          <Unplug aria-hidden />
          {t("start.offline")}
        </p>
      )}

      {wechselOffen && (
        <TurnierAuswahl
          turniere={wahl.turniere}
          aktivId={turnier?.id}
          onWahl={(id) => {
            wahl.waehlen(id);
            setWechselOffen(false);
          }}
          onAbbrechen={() => setWechselOffen(false)}
          hinweis={t("start.auswahl_hinweis")}
        />
      )}

      {sichtbareSchritte.length === 0 && <KeineAufgabe />}
      <section aria-labelledby="ablauf-titel" hidden={sichtbareSchritte.length === 0}>
        <h2 id="ablauf-titel" className="nur-screenreader">
          {t("ablauf.titel")}
        </h2>
        <ol className={s.ablauf}>
          {sichtbareSchritte.map((schritt, index) => {
            const naechster = schritt.id === eigenerNaechster?.id;
            const z = ziel(schritt.id);
            const aktion =
              naechster && naechsteAktion
                ? schrittAktion(schritt.id, naechsteAktion, true)
                : schritt.id === "sicherung" && lage.sicherungAktion
                  ? schrittAktion(schritt.id, lage.sicherungAktion, false)
                  : null;
            // Zum Aushang: die Siegerliste drucken, sobald es Ergebnisse gibt (leiser Weg).
            const drucken =
              schritt.id === "anzeige" &&
              turnier !== null &&
              (schritt.text === "anzeige_siegerliste" || schritt.text === "anzeige_live");
            const titel =
              schritt.id === "erfassung" && nurStand
                ? t("ablauf.schritt.erfassung_stand")
                : t(`ablauf.schritt.${schritt.id}`);
            const erledigt = schritt.stand === "erledigt" || schritt.stand === "ok";
            return (
              <li
                key={schritt.id}
                className={[
                  s.schritt,
                  naechster && s.naechster,
                  schritt.stand === "wartet" && s.wartet,
                ]
                  .filter(Boolean)
                  .join(" ")}
                aria-current={naechster ? "step" : undefined}
              >
                <span
                  className={[s.nummer, erledigt && s.nummerErledigt].filter(Boolean).join(" ")}
                >
                  {erledigt ? <Check aria-label={t("ablauf.stand.erledigt")} /> : index + 1}
                </span>
                <div className={s.inhalt}>
                  <h3 className={s.titel}>
                    {z ? (
                      <Link to={z.pfad} search={z.suche} className={s.titelLink}>
                        {titel}
                      </Link>
                    ) : (
                      titel
                    )}
                  </h3>
                  <p className={s.text}>
                    {schrittText(schritt, t)}
                    {schritt.id === "erfassung" &&
                      sichtbar.has("stand") &&
                      !nurStand &&
                      schritt.stand !== "wartet" && (
                        <>
                          {" "}
                          <Link to="/erfassung/stand" className={s.nebenLink}>
                            {t("ablauf.stand_link")}
                          </Link>
                        </>
                      )}
                  </p>
                  {naechster && !aktion && (
                    <p className={s.hinweis}>
                      {schritt.id === "sicherung"
                        ? t("sicherung.was_tun_ohne_recht")
                        : t("ablauf.ohne_recht")}
                    </p>
                  )}
                </div>
                <div className={s.rechts}>
                  {naechster && <span className={s.marke}>{t("ablauf.naechster")}</span>}
                  {schritt.stand !== "unbekannt" && (
                    <Chip ton={STAND_TON[schritt.stand]}>{t(`ablauf.stand.${schritt.stand}`)}</Chip>
                  )}
                  {drucken && (
                    <ExportKnoepfe
                      turnierId={turnier.id}
                      uebersicht={uebersicht.data}
                      knopfText={t("ablauf.siegerliste_drucken")}
                      nur="winners"
                    />
                  )}
                  {aktion}
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      <WeitereBereiche module={module} />
      {anlegen && <TurnierAnlegen offen onSchliessen={() => setAnlegen(false)} />}
    </div>
  );
}

function Kopf({ children, einleitung }: { children?: ReactNode; einleitung?: string }) {
  const { t } = useTranslation("shell");
  return (
    <div className={s.kopf}>
      <div className={s.kopfText}>
        <h1 className="h-display">{t("start.ueberschrift")}</h1>
        <p className="gedaempft">{einleitung ?? t("start.einleitung")}</p>
      </div>
      {children}
    </div>
  );
}

/** Text unter dem Schrittnamen, mit den Zahlen des Servers. */
function schrittText(schritt: AblaufSchritt, t: TFunction<"shell">): string {
  const werte: Record<string, string | number> = { ...schritt.werte };
  if (schritt.punkt) {
    werte.punkt = t(`turnier:offen.${schritt.punkt.schluessel}`, { ...schritt.punkt.werte });
  }
  if (schritt.text === "sicherung_warnung") {
    werte.was = t(`sicherung.chip_${String(werte.code)}`, {
      defaultValue: t("sicherung.chip_warnung"),
    });
  }
  return t(`ablauf.text.${schritt.text}`, werte);
}

/** Bereiche und Stationen, die kein Schritt des Ablaufs abdeckt (System, Personen, Katalog …). */
function WeitereBereiche({ module }: { module: ModulManifest[] }) {
  const { t } = useTranslation();
  const weitere = module
    .filter((modul) => !IM_ABLAUF.has(modul.id))
    .sort((a, b) => {
      const station = (m: ModulManifest) => (m.navigation.art === "station" ? 1 : 0);
      return station(a) - station(b) || a.navigation.reihenfolge - b.navigation.reihenfolge;
    });
  if (weitere.length === 0) return null;
  return (
    <section className={s.weitere} aria-labelledby="weitere-titel">
      <h2 id="weitere-titel" className="h-label">
        {t("shell:start.weitere")}
      </h2>
      <KachelRaster>
        {weitere.map((modul) => (
          <Kachel
            key={modul.id}
            pfad={modul.navigation.pfad}
            icon={modul.navigation.icon}
            titel={t(`${modul.namensraum}:titel`)}
            text={t(`${modul.namensraum}:zweck`)}
          />
        ))}
      </KachelRaster>
    </section>
  );
}
