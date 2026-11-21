import { TextInput, type TextInputProps } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { formatBetrag, leseBetrag, waehrungsZeichen } from "./geld";

interface GeldEingabeProps
  extends Omit<TextInputProps, "value" | "onChange" | "defaultValue" | "rightSection"> {
  /** Betrag in Cent; `null` = leer */
  wert: number | null;
  onWert: (cent: number | null) => void;
  waehrung?: string;
  /** Meldung bei unlesbarer Eingabe, z. B. „Betrag wie 6,00 eingeben“ */
  meldungUnlesbar: string;
}

/**
 * Eingabe eines Geldbetrags in Euro mit Dezimalkomma; nach außen in Cent.
 * Unlesbare Eingaben bleiben stehen und werden markiert, bis sie berichtigt sind.
 */
export function GeldEingabe({
  wert,
  onWert,
  waehrung = "EUR",
  meldungUnlesbar,
  error,
  ...rest
}: GeldEingabeProps) {
  const { i18n } = useTranslation();
  const [text, setText] = useState(() => (wert === null ? "" : formatBetrag(wert, i18n.language)));
  const [bekannt, setBekannt] = useState(wert);
  const gelesen = leseBetrag(text);

  // Ändert sich der Wert von außen (z. B. Zurücksetzen), folgt das Feld.
  if (bekannt !== wert) {
    setBekannt(wert);
    if (gelesen !== wert) setText(wert === null ? "" : formatBetrag(wert, i18n.language));
  }

  return (
    <TextInput
      {...rest}
      inputMode="decimal"
      autoComplete="off"
      value={text}
      classNames={{ input: "num" }}
      styles={{ input: { textAlign: "right" } }}
      rightSection={<span aria-hidden>{waehrungsZeichen(waehrung, i18n.language)}</span>}
      error={gelesen === undefined ? meldungUnlesbar : error}
      onChange={(ereignis) => {
        const neu = ereignis.currentTarget.value;
        setText(neu);
        const cent = leseBetrag(neu);
        if (cent !== undefined) {
          setBekannt(cent);
          onWert(cent);
        }
      }}
      onBlur={(ereignis) => {
        if (gelesen !== undefined && gelesen !== null)
          setText(formatBetrag(gelesen, i18n.language));
        rest.onBlur?.(ereignis);
      }}
    />
  );
}
