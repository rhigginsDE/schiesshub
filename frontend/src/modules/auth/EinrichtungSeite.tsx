import { Button, PasswordInput, TextInput } from "@mantine/core";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { CircleCheck, ShieldPlus } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiSenden } from "../../api/client";
import type { AuthStatus } from "../../api/typenSystem";
import { useAnmeldung } from "../../app/anmeldung";
import { FehlerHinweis } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { Leerzustand } from "../../components/Zustand";
import s from "./auth.module.css";
import { PIN_MAX_LAENGE, PIN_MIN_LAENGE, pinGueltig } from "./eingaben";

interface Fehler {
  name?: string;
  pin?: string;
  pin2?: string;
  geraet?: string;
}

/** Ersteinrichtung: erste Person mit allen Rechten anlegen und dieses Gerät koppeln. */
export function EinrichtungSeite() {
  const { t } = useTranslation("auth");
  const navigate = useNavigate();
  const { status, uebernehmen } = useAnmeldung();
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [pin2, setPin2] = useState("");
  const [geraet, setGeraet] = useState("");
  const [fehler, setFehler] = useState<Fehler>({});

  const gekoppelt = status?.device ?? null;

  const einrichten = useMutation({
    mutationFn: () =>
      apiSenden<AuthStatus>(
        "POST",
        "/auth/setup",
        { name: name.trim(), pin, device_name: gekoppelt?.name ?? geraet.trim() },
        { still: true },
      ),
    onSuccess: (neu) => {
      uebernehmen(neu);
      zeigeMeldung({
        ton: "erfolg",
        titel: t("einrichtung.fertig_titel"),
        text: t("einrichtung.fertig_text"),
      });
      void navigate({ to: "/system/sicherung" });
    },
  });

  if (status && !status.setup_required) {
    return (
      <section className={`panel ${s.karte}`}>
        <Leerzustand
          icon={CircleCheck}
          titel={t("einrichtung.erledigt_titel")}
          text={t("einrichtung.erledigt_text")}
        >
          <Button component={Link} to="/">
            {t("allgemein:aktion.zur_startseite")}
          </Button>
        </Leerzustand>
      </section>
    );
  }

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    const neu: Fehler = {};
    if (!name.trim()) neu.name = t("einrichtung.fehler_name");
    if (!pinGueltig(pin)) neu.pin = t("einrichtung.fehler_pin", { anzahl: PIN_MIN_LAENGE });
    else if (pin !== pin2) neu.pin2 = t("einrichtung.fehler_pin_gleich");
    if (!gekoppelt && !geraet.trim()) neu.geraet = t("einrichtung.fehler_geraet");
    setFehler(neu);
    if (Object.keys(neu).length === 0) einrichten.mutate();
  };

  return (
    <section className={`panel ${s.karte}`} aria-labelledby="einrichtung-titel">
      <header className={s.kopf}>
        <span className={s.symbol}>
          <ShieldPlus aria-hidden />
        </span>
        <h1 className="h-display" id="einrichtung-titel">
          {t("einrichtung.titel")}
        </h1>
        <p className="gedaempft">{t("einrichtung.einleitung")}</p>
      </header>
      <form className={s.formular} onSubmit={absenden} noValidate>
        <TextInput
          size="md"
          label={t("einrichtung.name")}
          description={t("einrichtung.name_hinweis")}
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          error={fehler.name}
          autoComplete="name"
          maxLength={100}
          data-autofocus
        />
        <PasswordInput
          visibilityToggleButtonProps={{ "aria-label": t("shell:sichtbar_umschalten") }}
          size="md"
          label={t("einrichtung.pin")}
          description={t("einrichtung.pin_hinweis", { anzahl: PIN_MIN_LAENGE })}
          value={pin}
          onChange={(e) => setPin(e.currentTarget.value.replace(/\D/g, ""))}
          error={fehler.pin}
          inputMode="numeric"
          autoComplete="new-password"
          maxLength={PIN_MAX_LAENGE}
          classNames={{ innerInput: "num" }}
        />
        <PasswordInput
          visibilityToggleButtonProps={{ "aria-label": t("shell:sichtbar_umschalten") }}
          size="md"
          label={t("einrichtung.pin_wiederholen")}
          value={pin2}
          onChange={(e) => setPin2(e.currentTarget.value.replace(/\D/g, ""))}
          error={fehler.pin2}
          inputMode="numeric"
          autoComplete="new-password"
          maxLength={PIN_MAX_LAENGE}
          classNames={{ innerInput: "num" }}
        />
        {gekoppelt ? (
          <p className="gedaempft">{t("einrichtung.geraet_gekoppelt", { name: gekoppelt.name })}</p>
        ) : (
          <TextInput
            size="md"
            label={t("einrichtung.geraet")}
            description={t("einrichtung.geraet_hinweis")}
            value={geraet}
            onChange={(e) => setGeraet(e.currentTarget.value)}
            error={fehler.geraet}
            maxLength={100}
          />
        )}
        <FehlerHinweis fehler={einrichten.error} />
        <Button type="submit" size="lg" loading={einrichten.isPending}>
          {t("einrichtung.absenden")}
        </Button>
      </form>
    </section>
  );
}
