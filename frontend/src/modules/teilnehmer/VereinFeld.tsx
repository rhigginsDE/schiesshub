import { Combobox, InputBase, Loader, useCombobox } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { bereinigen, vergleichsform } from "./anzeigename";
import {
  fehlertext,
  teilnehmerSchluessel,
  type Verein,
  vereinAnlegen,
  vereineAbfrage,
} from "./api";
import s from "./teilnehmer.module.css";

const NEU = "$neu";
const KEIN = "$kein";

interface VereinFeldProps {
  /** ID des gewählten Vereins, `null` = kein Verein */
  wert: string | null;
  onAendern: (id: string | null) => void;
  label: string;
  description?: string;
}

/**
 * Vereinsauswahl mit Suche. Passt kein Verein, lässt sich der getippte Name direkt als neuer
 * Verein anlegen; er ist danach gewählt.
 */
export function VereinFeld({ wert, onAendern, label, description }: VereinFeldProps) {
  const { t } = useTranslation("teilnehmer");
  const queryClient = useQueryClient();
  const vereine = useQuery(vereineAbfrage());
  // null = es wird nicht getippt, das Feld zeigt den gewählten Verein
  const [suche, setSuche] = useState<string | null>(null);
  const [hinweis, setHinweis] = useState<string | null>(null);

  const combobox = useCombobox({
    onDropdownClose: () => {
      combobox.resetSelectedOption();
      setSuche(null);
    },
  });

  const anlegen = useMutation({
    mutationFn: (name: string) => vereinAnlegen({ name }),
    onSuccess: (verein) => {
      queryClient.setQueryData<Verein[]>(teilnehmerSchluessel.vereine(), (alt) =>
        [...(alt ?? []).filter((v) => v.id !== verein.id), verein].sort((a, b) =>
          a.name.localeCompare(b.name, "de"),
        ),
      );
      void queryClient.invalidateQueries({ queryKey: teilnehmerSchluessel.vereine() });
      setHinweis(t("vereinfeld.angelegt", { name: verein.name }));
      onAendern(verein.id);
    },
  });

  const alle = vereine.data ?? [];
  const gewaehlt = alle.find((verein) => verein.id === wert);
  const filter = vergleichsform(suche ?? "");
  const passend = filter
    ? alle.filter(
        (verein) =>
          vergleichsform(verein.name).includes(filter) ||
          (verein.short ? vergleichsform(verein.short).includes(filter) : false),
      )
    : alle;
  // Erst anbieten, wenn die Liste geladen ist; sonst entstünde beim schnellen Tippen eine Dublette.
  const neuMoeglich =
    vereine.isSuccess &&
    filter !== "" &&
    !alle.some((verein) => vergleichsform(verein.name) === filter);

  // Nach jeder Eingabe den besten Treffer vorwählen, damit Enter ihn übernimmt.
  // biome-ignore lint/correctness/useExhaustiveDependencies: nur bei neuem Suchtext, nicht bei jedem Render
  useEffect(() => {
    if (filter) combobox.selectFirstOption();
  }, [filter]);

  const fehler = anlegen.isError
    ? (fehlertext(anlegen.error) ?? t("vereinfeld.fehler"))
    : undefined;

  return (
    <Combobox
      store={combobox}
      onOptionSubmit={(auswahl) => {
        if (auswahl === NEU) {
          anlegen.mutate(bereinigen(suche ?? ""));
        } else {
          anlegen.reset();
          setHinweis(null);
          onAendern(auswahl === KEIN ? null : auswahl);
        }
        setSuche(null);
        combobox.closeDropdown();
      }}
    >
      <Combobox.Target>
        <InputBase
          size="md"
          label={label}
          description={hinweis ?? description}
          placeholder={t("vereinfeld.platzhalter")}
          value={suche ?? gewaehlt?.name ?? ""}
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
              anlegen.reset();
              setHinweis(null);
              onAendern(erster.id);
            } else if (neuMoeglich) {
              anlegen.mutate(bereinigen(suche ?? ""));
            }
            setSuche(null);
            combobox.closeDropdown();
          }}
          rightSection={anlegen.isPending ? <Loader size="xs" /> : <Combobox.Chevron />}
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
              {!filter && wert && (
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
              {neuMoeglich && (
                <Combobox.Option value={NEU} className={s.vereinNeu}>
                  <Plus aria-hidden />
                  {t("vereinfeld.neu", { name: bereinigen(suche ?? "") })}
                </Combobox.Option>
              )}
              {passend.length === 0 && !neuMoeglich && !(!filter && wert) && (
                <Combobox.Empty>{t("vereinfeld.leer")}</Combobox.Empty>
              )}
            </>
          )}
        </Combobox.Options>
      </Combobox.Dropdown>
    </Combobox>
  );
}
