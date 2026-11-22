import { Combobox, InputBase, useCombobox } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { bereinigen, vergleichsform } from "./anzeigename";
import { vereineAbfrage } from "./api";
import s from "./teilnehmer.module.css";
import { vereinTreffer } from "./vereinSuche";

const NEU = "$neu";
const KEIN = "$kein";

interface VereinFeldProps {
  /** ID des gewählten Vereins, `null` = kein Verein (oder ein vorgemerkter neuer) */
  wert: string | null;
  /** Vorgemerkter neuer Verein: Er wird erst beim Speichern der Person angelegt. */
  neu: string | null;
  /** Vorhandener Verein gewählt (oder `null` = kein Verein); hebt einen vorgemerkten auf */
  onAendern: (id: string | null) => void;
  /** Getippter Name als neuer Verein vorgemerkt */
  onNeu: (name: string) => void;
  label: string;
  description?: string;
  /** Fehler von außen, z. B. wenn der vorgemerkte Verein beim Speichern nicht angelegt werden konnte */
  fehler?: string;
}

/**
 * Vereinsauswahl mit Suche. Passt kein Verein, lässt sich der getippte Name als neuer Verein
 * vormerken. Angelegt wird er erst, wenn die Person gespeichert wird (siehe PersonFormular); so
 * bleibt kein Verein zurück, wenn die Eingabe verworfen wird.
 */
export function VereinFeld({
  wert,
  neu,
  onAendern,
  onNeu,
  label,
  description,
  fehler,
}: VereinFeldProps) {
  const { t } = useTranslation("teilnehmer");
  const vereine = useQuery(vereineAbfrage());
  // null = es wird nicht getippt, das Feld zeigt den gewählten Verein
  const [suche, setSuche] = useState<string | null>(null);

  const combobox = useCombobox({
    onDropdownClose: () => {
      combobox.resetSelectedOption();
      setSuche(null);
    },
  });

  const alle = vereine.data ?? [];
  const gewaehlt = alle.find((verein) => verein.id === wert);
  const filter = vergleichsform(suche ?? "");
  const { treffer: passend, aehnlich, exakt } = vereinTreffer(alle, suche ?? "");
  // Erst anbieten, wenn die Liste geladen ist; sonst entstünde beim schnellen Tippen eine Dublette.
  // Passt Name oder Kürzel genau, gibt es den Verein schon.
  const neuMoeglich = vereine.isSuccess && filter !== "" && !exakt;
  const hatAuswahl = wert !== null || neu !== null;

  // Nach jeder Eingabe den besten Treffer vorwählen, damit Enter ihn übernimmt. Gibt es nur ähnliche
  // Vereine, wird nichts vorgewählt: Dann soll niemand per Enter versehentlich einen fremden Verein
  // übernehmen oder einen doppelten anlegen. „Neu anlegen“ ist nur vorgewählt, wenn gar nichts passt.
  const nurAehnlich = passend.length === 0 && aehnlich.length > 0;
  // biome-ignore lint/correctness/useExhaustiveDependencies: nur bei neuem Suchtext, nicht bei jedem Render
  useEffect(() => {
    if (!filter) return;
    if (nurAehnlich) combobox.resetSelectedOption();
    else combobox.selectFirstOption();
  }, [filter, nurAehnlich]);

  const vormerken = () => onNeu(bereinigen(suche ?? ""));

  return (
    <Combobox
      store={combobox}
      onOptionSubmit={(auswahl) => {
        if (auswahl === NEU) vormerken();
        else onAendern(auswahl === KEIN ? null : auswahl);
        setSuche(null);
        combobox.closeDropdown();
      }}
    >
      <Combobox.Target>
        <InputBase
          size="md"
          label={label}
          description={neu !== null && suche === null ? t("vereinfeld.vorgemerkt") : description}
          placeholder={t("vereinfeld.platzhalter")}
          value={suche ?? neu ?? gewaehlt?.name ?? ""}
          onChange={(ereignis) => {
            setSuche(ereignis.currentTarget.value);
            combobox.openDropdown();
          }}
          onClick={() => combobox.openDropdown()}
          onFocus={() => combobox.openDropdown()}
          onBlur={() => combobox.closeDropdown()}
          onKeyDownCapture={(ereignis) => {
            // Enter wählt hier immer aus und schickt nie das umgebende Formular ab. Ist noch keine
            // Option vorgewählt (Liste beim schnellen Tippen noch nicht gezeichnet), gilt der beste Treffer.
            if (ereignis.key !== "Enter") return;
            ereignis.preventDefault();
            ereignis.stopPropagation();
            if (!combobox.dropdownOpened) {
              combobox.openDropdown();
              return;
            }
            if (combobox.getSelectedOptionIndex() !== -1) {
              combobox.clickSelectedOption();
              return;
            }
            if (!filter) return;
            const erster = passend[0];
            if (erster) {
              onAendern(erster.id);
            } else if (nurAehnlich) {
              // Liste offen lassen: Ähnlichen Verein wählen oder bewusst „neu anlegen“ antippen.
              return;
            } else if (neuMoeglich) {
              vormerken();
            }
            setSuche(null);
            combobox.closeDropdown();
          }}
          rightSection={<Combobox.Chevron />}
          rightSectionPointerEvents="none"
          error={fehler}
          autoComplete="off"
        />
      </Combobox.Target>

      <Combobox.Dropdown>
        <Combobox.Options className={s.vereinOptionen}>
          {vereine.isPending ? (
            <Combobox.Empty>{t("vereinfeld.laedt")}</Combobox.Empty>
          ) : (
            <>
              {!filter && hatAuswahl && (
                <Combobox.Option value={KEIN}>{t("vereinfeld.kein")}</Combobox.Option>
              )}
              {passend.map((verein) => (
                <Combobox.Option
                  key={verein.id}
                  value={verein.id}
                  active={verein.id === wert}
                  className={s.vereinOption}
                >
                  <span>{verein.name}</span>
                  {verein.short && <span className="gedaempft">{verein.short}</span>}
                </Combobox.Option>
              ))}
              {aehnlich.length > 0 && (
                <Combobox.Group label={t("vereinfeld.aehnlich")}>
                  {aehnlich.map((verein) => (
                    <Combobox.Option
                      key={verein.id}
                      value={verein.id}
                      active={verein.id === wert}
                      className={s.vereinOption}
                    >
                      <span>{verein.name}</span>
                      {verein.short && <span className="gedaempft">{verein.short}</span>}
                    </Combobox.Option>
                  ))}
                </Combobox.Group>
              )}
              {neuMoeglich && (
                <Combobox.Option value={NEU} className={s.vereinNeu}>
                  <Plus aria-hidden />
                  {t("vereinfeld.neu", { name: bereinigen(suche ?? "") })}
                </Combobox.Option>
              )}
              {passend.length === 0 &&
                aehnlich.length === 0 &&
                !neuMoeglich &&
                !(!filter && hatAuswahl) && <Combobox.Empty>{t("vereinfeld.leer")}</Combobox.Empty>}
            </>
          )}
        </Combobox.Options>
      </Combobox.Dropdown>
    </Combobox>
  );
}
