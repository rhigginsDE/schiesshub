import { Button, CloseButton, Select, Skeleton, TextInput } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, GitMerge, Pencil, Plus, Search, SearchX, Shield, Trash2 } from "lucide-react";
import { type FormEvent, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { formatZahl } from "../../lib/format";
import { bereinigen, vergleichsform } from "./anzeigename";
import {
  fehlertext,
  teilnehmerSchluessel,
  type Verein,
  vereinAendern,
  vereinAnlegen,
  vereineAbfrage,
  vereineZusammenfuehren,
  vereinLoeschen,
} from "./api";
import { Kopf } from "./Kopf";
import s from "./teilnehmer.module.css";

/** Vereine: anlegen, umbenennen, Kürzel, löschen, zusammenführen. Seiten-Layout. */
export function VereineSeite() {
  const { t, i18n } = useTranslation("teilnehmer");
  const vereine = useQuery(vereineAbfrage());
  const [filter, setFilter] = useState("");
  const [meldung, setMeldung] = useState<string | null>(null);
  const [zusammenfuehren, setZusammenfuehren] = useState<Verein | null>(null);
  const [loeschen, setLoeschen] = useState<Verein | null>(null);

  const suche = vergleichsform(filter);
  const sichtbar = (vereine.data ?? []).filter(
    (verein) =>
      !suche ||
      vergleichsform(verein.name).includes(suche) ||
      (verein.short ? vergleichsform(verein.short).includes(suche) : false),
  );

  return (
    <div className={s.seiteFluss}>
      <Kopf aktiv="vereine" />
      <div className={s.vereineRaster}>
        <VereinAnlegen
          onAngelegt={(verein) => setMeldung(t("vereine.angelegt", { name: verein.name }))}
        />

        <section className={`panel ${s.vereineListe}`} aria-labelledby="vereine-liste">
          <div className="panel-kopf">
            <h2 className="h-section" id="vereine-liste">
              {t("vereine.titel")}
            </h2>
            {vereine.data && (
              <span className="gedaempft">
                {t("vereine.anzahl", {
                  count: vereine.data.length,
                  anzahl: formatZahl(vereine.data.length, {}, i18n.language),
                })}
              </span>
            )}
          </div>
          <p className={s.status} role="status">
            {meldung && (
              <>
                <Check aria-hidden />
                {meldung}
              </>
            )}
          </p>
          {(vereine.data?.length ?? 0) > 5 && (
            <TextInput
              type="search"
              value={filter}
              onChange={(ereignis) => setFilter(ereignis.currentTarget.value)}
              placeholder={t("vereine.filter")}
              aria-label={t("vereine.filter")}
              leftSection={<Search aria-hidden />}
              rightSection={
                filter ? (
                  <CloseButton aria-label={t("suche.leeren")} onClick={() => setFilter("")} />
                ) : null
              }
            />
          )}

          {vereine.isPending ? (
            <div className={s.skelett} aria-busy="true">
              {[0, 1, 2, 3].map((nr) => (
                <Skeleton key={nr} height={56} radius="sm" />
              ))}
            </div>
          ) : vereine.isError ? (
            <Fehlerzustand fehler={vereine.error} onErneut={() => void vereine.refetch()} />
          ) : vereine.data.length === 0 ? (
            <Leerzustand
              icon={Shield}
              titel={t("vereine.leer_titel")}
              text={t("vereine.leer_text")}
            />
          ) : sichtbar.length === 0 ? (
            <Leerzustand
              icon={SearchX}
              titel={t("vereine.leer_filter_titel")}
              text={t("vereine.leer_filter_text", { q: filter.trim() })}
            />
          ) : (
            <ul className={s.vereine}>
              {sichtbar.map((verein) => (
                <VereinZeile
                  key={verein.id}
                  verein={verein}
                  onMeldung={setMeldung}
                  onZusammenfuehren={() => setZusammenfuehren(verein)}
                  onLoeschen={() => setLoeschen(verein)}
                />
              ))}
            </ul>
          )}
        </section>
      </div>

      <ZusammenfuehrenDialog
        verein={zusammenfuehren}
        alle={vereine.data ?? []}
        onSchliessen={() => setZusammenfuehren(null)}
        onFertig={(von, nach) => {
          setZusammenfuehren(null);
          setMeldung(t("vereine.zusammengefuehrt", { von: von.name, nach: nach.name }));
        }}
      />
      <LoeschenDialog
        verein={loeschen}
        onSchliessen={() => setLoeschen(null)}
        onZusammenfuehren={(verein) => {
          setLoeschen(null);
          setZusammenfuehren(verein);
        }}
        onFertig={(verein) => {
          setLoeschen(null);
          setMeldung(t("vereine.geloescht", { name: verein.name }));
        }}
      />
    </div>
  );
}

function VereinAnlegen({ onAngelegt }: { onAngelegt: (verein: Verein) => void }) {
  const { t } = useTranslation("teilnehmer");
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [kurz, setKurz] = useState("");
  const [nameFehlt, setNameFehlt] = useState(false);
  const anlegen = useMutation({
    mutationFn: () => vereinAnlegen({ name: bereinigen(name), short: kurz.trim() || null }),
    onSuccess: (verein) => {
      void queryClient.invalidateQueries({ queryKey: teilnehmerSchluessel.alle });
      setName("");
      setKurz("");
      onAngelegt(verein);
    },
  });
  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    if (!bereinigen(name)) {
      setNameFehlt(true);
      return;
    }
    anlegen.mutate();
  };

  return (
    <section className={`panel ${s.vereinNeuPanel}`} aria-labelledby="verein-anlegen">
      <h2 className="h-section" id="verein-anlegen">
        {t("vereine.anlegen_titel")}
      </h2>
      <form className={s.formular} onSubmit={absenden} noValidate>
        <TextInput
          size="md"
          label={t("vereine.name")}
          value={name}
          onChange={(ereignis) => {
            setName(ereignis.currentTarget.value);
            setNameFehlt(false);
            anlegen.reset();
          }}
          error={
            nameFehlt
              ? t("formular.name_fehlt")
              : anlegen.isError
                ? (fehlertext(anlegen.error) ?? t("fehler.titel"))
                : undefined
          }
          maxLength={200}
          required
          autoComplete="off"
        />
        <TextInput
          size="md"
          label={
            <>
              {t("vereine.kuerzel")} <span className={s.optional}>({t("formular.optional")})</span>
            </>
          }
          description={t("vereine.kuerzel_hilfe")}
          value={kurz}
          onChange={(ereignis) => setKurz(ereignis.currentTarget.value)}
          maxLength={40}
          autoComplete="off"
        />
        <div>
          <Button
            type="submit"
            size="md"
            leftSection={<Plus aria-hidden />}
            loading={anlegen.isPending}
          >
            {t("vereine.anlegen")}
          </Button>
        </div>
      </form>
    </section>
  );
}

interface VereinZeileProps {
  verein: Verein;
  onMeldung: (text: string) => void;
  onZusammenfuehren: () => void;
  onLoeschen: () => void;
}

function VereinZeile({ verein, onMeldung, onZusammenfuehren, onLoeschen }: VereinZeileProps) {
  const { t, i18n } = useTranslation("teilnehmer");
  const queryClient = useQueryClient();
  const id = useId();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [name, setName] = useState(verein.name);
  const [kurz, setKurz] = useState(verein.short ?? "");

  const speichern = useMutation({
    mutationFn: () =>
      vereinAendern(verein.id, { name: bereinigen(name), short: kurz.trim() || null }),
    onSuccess: (neu) => {
      void queryClient.invalidateQueries({ queryKey: teilnehmerSchluessel.alle });
      setBearbeiten(false);
      onMeldung(t("vereine.gespeichert", { name: neu.name }));
    },
  });

  const oeffnen = () => {
    // Beim Öffnen den aktuellen Stand übernehmen; während der Bearbeitung bleibt die Eingabe stehen.
    setName(verein.name);
    setKurz(verein.short ?? "");
    speichern.reset();
    setBearbeiten(true);
  };

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    if (!bereinigen(name)) return;
    speichern.mutate();
  };

  const personen = t("vereine.personen", {
    count: verein.person_count,
    anzahl: formatZahl(verein.person_count, {}, i18n.language),
  });

  if (bearbeiten) {
    return (
      <li className={s.vereinZeile} data-bearbeiten>
        <form className={s.vereinForm} onSubmit={absenden} noValidate>
          <TextInput
            label={t("vereine.name")}
            value={name}
            onChange={(ereignis) => setName(ereignis.currentTarget.value)}
            error={
              !bereinigen(name)
                ? t("formular.name_fehlt")
                : speichern.isError
                  ? (fehlertext(speichern.error) ?? t("fehler.titel"))
                  : undefined
            }
            maxLength={200}
            autoFocus
            autoComplete="off"
            onKeyDown={(ereignis) => {
              if (ereignis.key === "Escape") setBearbeiten(false);
            }}
          />
          <TextInput
            label={t("vereine.kuerzel")}
            value={kurz}
            onChange={(ereignis) => setKurz(ereignis.currentTarget.value)}
            maxLength={40}
            autoComplete="off"
            onKeyDown={(ereignis) => {
              if (ereignis.key === "Escape") setBearbeiten(false);
            }}
          />
          <div className={s.vereinFormAktionen}>
            <Button type="submit" variant="default" loading={speichern.isPending}>
              {t("vereine.speichern")}
            </Button>
            <Button variant="subtle" color="gray" onClick={() => setBearbeiten(false)}>
              {t("vereine.abbrechen")}
            </Button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li className={s.vereinZeile}>
      <div className={s.vereinText} id={id}>
        <strong>{verein.name}</strong>
        <span>
          {verein.short && (
            <>
              <span className={s.kuerzel}>{verein.short}</span>
              {" · "}
            </>
          )}
          <span className="num">{personen}</span>
        </span>
      </div>
      <div className={s.vereinAktionen}>
        <Button
          variant="default"
          size="sm"
          leftSection={<Pencil aria-hidden />}
          onClick={oeffnen}
          aria-describedby={id}
        >
          {t("vereine.bearbeiten")}
        </Button>
        <Button
          variant="default"
          size="sm"
          leftSection={<GitMerge aria-hidden />}
          onClick={onZusammenfuehren}
          aria-describedby={id}
        >
          {t("vereine.zusammenfuehren")}
        </Button>
        <Button
          variant="default"
          size="sm"
          className={s.gefahr}
          leftSection={<Trash2 aria-hidden />}
          onClick={onLoeschen}
          aria-describedby={id}
        >
          {t("vereine.loeschen")}
        </Button>
      </div>
    </li>
  );
}

interface ZusammenfuehrenDialogProps {
  verein: Verein | null;
  alle: Verein[];
  onSchliessen: () => void;
  onFertig: (von: Verein, nach: Verein) => void;
}

function ZusammenfuehrenDialog({
  verein,
  alle,
  onSchliessen,
  onFertig,
}: ZusammenfuehrenDialogProps) {
  const { t } = useTranslation("teilnehmer");
  const queryClient = useQueryClient();
  const [zielId, setZielId] = useState<string | null>(null);
  const [offenFuer, setOffenFuer] = useState<string | null>(null);
  if ((verein?.id ?? null) !== offenFuer) {
    setOffenFuer(verein?.id ?? null);
    setZielId(null);
  }
  const ziele = alle.filter((eintrag) => eintrag.id !== verein?.id);
  const ziel = ziele.find((eintrag) => eintrag.id === zielId);

  const ausfuehren = useMutation({
    mutationFn: () => vereineZusammenfuehren(verein?.id ?? "", zielId ?? ""),
    onSuccess: (nach) => {
      void queryClient.invalidateQueries({ queryKey: teilnehmerSchluessel.alle });
      if (verein) onFertig(verein, nach);
    },
  });

  const name = verein?.name ?? "";
  return (
    <Bestaetigung
      offen={verein !== null}
      titel={t("vereine.zf_titel")}
      text={t("vereine.zf_text", { name })}
      bestaetigen={
        ziel
          ? t("vereine.zf_bestaetigen", { von: name, nach: ziel.name })
          : t("vereine.zusammenfuehren")
      }
      abbrechen={t("vereine.abbrechen")}
      ton="gefahr"
      laedt={ausfuehren.isPending}
      gesperrt={!ziel}
      fehler={ausfuehren.isError ? (fehlertext(ausfuehren.error) ?? t("fehler.titel")) : undefined}
      onBestaetigen={() => ausfuehren.mutate()}
      onSchliessen={() => {
        ausfuehren.reset();
        onSchliessen();
      }}
    >
      {ziele.length === 0 ? (
        <p className={s.hinweisWarn}>{t("vereine.zf_kein_ziel", { name })}</p>
      ) : (
        <Select
          size="md"
          label={t("vereine.zf_ziel")}
          placeholder={t("vereine.zf_ziel_platzhalter")}
          data={ziele.map((eintrag) => ({
            value: eintrag.id,
            label: eintrag.short ? `${eintrag.name} (${eintrag.short})` : eintrag.name,
          }))}
          value={zielId}
          onChange={setZielId}
          searchable
          nothingFoundMessage={t("vereinfeld.leer")}
          comboboxProps={{ withinPortal: false }}
          data-autofocus
        />
      )}
      {ziel && verein && (
        <p className={s.hinweisWarn}>
          {t("vereine.zf_folge", { count: verein.person_count, von: name, nach: ziel.name })}
        </p>
      )}
    </Bestaetigung>
  );
}

interface LoeschenDialogProps {
  verein: Verein | null;
  onSchliessen: () => void;
  onZusammenfuehren: (verein: Verein) => void;
  onFertig: (verein: Verein) => void;
}

function LoeschenDialog({
  verein,
  onSchliessen,
  onZusammenfuehren,
  onFertig,
}: LoeschenDialogProps) {
  const { t } = useTranslation("teilnehmer");
  const queryClient = useQueryClient();
  const loeschen = useMutation({
    mutationFn: (id: string) => vereinLoeschen(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: teilnehmerSchluessel.alle });
      if (verein) onFertig(verein);
    },
  });
  const belegt = (verein?.person_count ?? 0) > 0;

  const name = verein?.name ?? "";
  return (
    <Bestaetigung
      offen={verein !== null}
      titel={t("vereine.loeschen_titel")}
      text={
        belegt
          ? t("vereine.loeschen_belegt", { count: verein?.person_count ?? 0, name })
          : t("vereine.loeschen_text", { name })
      }
      bestaetigen={belegt ? t("vereine.zusammenfuehren") : t("vereine.loeschen_bestaetigen")}
      abbrechen={t("vereine.abbrechen")}
      ton={belegt ? "normal" : "gefahr"}
      laedt={loeschen.isPending}
      fehler={loeschen.isError ? (fehlertext(loeschen.error) ?? t("fehler.titel")) : undefined}
      onBestaetigen={() => {
        if (!verein) return;
        if (belegt) onZusammenfuehren(verein);
        else loeschen.mutate(verein.id);
      }}
      onSchliessen={() => {
        loeschen.reset();
        onSchliessen();
      }}
    />
  );
}
