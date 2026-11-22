import { Radio, Stack, Textarea } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Bestaetigung } from "../../components/Bestaetigung";
import { useFehlerText } from "../../components/FehlerHinweis";
import { ABBRUCHGRUENDE, type Abbruchgrund } from "./api";
import s from "./erfassung.module.css";

interface VorgangProps {
  offen: boolean;
  laedt: boolean;
  fehler: unknown;
  onSchliessen: () => void;
}

export function AbschlussDialog({
  offen,
  laedt,
  fehler,
  onSchliessen,
  onBestaetigen,
  ergebnis,
  wer,
}: VorgangProps & { onBestaetigen: () => void; ergebnis: string; wer: string }) {
  const { t } = useTranslation("erfassung");
  const fehlerText = useFehlerText();
  return (
    <Bestaetigung
      offen={offen}
      titel={t("abschluss.titel")}
      text={
        <div className={s.dialogErgebnis}>
          <span>{wer}</span>
          <strong className="num">{ergebnis}</strong>
          <span className="gedaempft">{t("abschluss.text")}</span>
        </div>
      }
      bestaetigen={t("abschluss.bestaetigen")}
      abbrechen={t("dialog.abbrechen")}
      laedt={laedt}
      fehler={fehler ? fehlerText(fehler) : undefined}
      onSchliessen={onSchliessen}
      onBestaetigen={onBestaetigen}
    />
  );
}

export function AbbruchDialog({
  offen,
  laedt,
  fehler,
  onSchliessen,
  onBestaetigen,
  wer,
}: VorgangProps & {
  onBestaetigen: (grund: Abbruchgrund, text: string | null) => void;
  wer: string;
}) {
  const { t } = useTranslation("erfassung");
  const fehlerText = useFehlerText();
  const [grund, setGrund] = useState<Abbruchgrund | null>(null);
  const [text, setText] = useState("");
  return (
    <Bestaetigung
      offen={offen}
      titel={t("abbruch.titel")}
      text={t("abbruch.text", { wer })}
      bestaetigen={t("abbruch.bestaetigen")}
      abbrechen={t("dialog.abbrechen")}
      ton="gefahr"
      laedt={laedt}
      gesperrt={grund === null}
      fehler={fehler ? fehlerText(fehler) : undefined}
      onSchliessen={onSchliessen}
      onBestaetigen={() => grund && onBestaetigen(grund, text.trim() || null)}
    >
      <Radio.Group
        value={grund}
        onChange={(wert) => setGrund(wert as Abbruchgrund)}
        label={t("abbruch.art")}
      >
        <Stack gap="xs" mt="xs">
          {ABBRUCHGRUENDE.map((g) => (
            <Radio
              key={g}
              value={g}
              label={t(`abbruch.lang.${g}`)}
              size="md"
              classNames={{ root: s.radioZeile }}
            />
          ))}
        </Stack>
      </Radio.Group>
      <Textarea
        label={t("abbruch.grund")}
        value={text}
        onChange={(e) => setText(e.currentTarget.value)}
        maxLength={500}
        autosize
        minRows={2}
      />
    </Bestaetigung>
  );
}

/** Rückfrage mit Pflichtgrund (Korrektur speichern, wieder öffnen). */
export function GrundDialog({
  offen,
  laedt,
  fehler,
  onSchliessen,
  onBestaetigen,
  titel,
  text,
  bestaetigen,
}: VorgangProps & {
  onBestaetigen: (grund: string) => void;
  titel: string;
  text: string;
  bestaetigen: string;
}) {
  const { t } = useTranslation("erfassung");
  const fehlerText = useFehlerText();
  const [grund, setGrund] = useState("");
  return (
    <Bestaetigung
      offen={offen}
      titel={titel}
      text={text}
      bestaetigen={bestaetigen}
      abbrechen={t("dialog.abbrechen")}
      laedt={laedt}
      gesperrt={grund.trim() === ""}
      fehler={fehler ? fehlerText(fehler) : undefined}
      onSchliessen={onSchliessen}
      onBestaetigen={() => onBestaetigen(grund.trim())}
    >
      <Textarea
        label={t("dialog.grund")}
        description={t("dialog.grund_hilfe")}
        value={grund}
        onChange={(e) => setGrund(e.currentTarget.value)}
        maxLength={500}
        autosize
        minRows={2}
        required
        data-autofocus
      />
    </Bestaetigung>
  );
}
