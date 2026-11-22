import { Button, TextInput } from "@mantine/core";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, MonitorSmartphone, ShieldX } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiSenden } from "../../api/client";
import type { AuthStatus } from "../../api/typenSystem";
import { useAnmeldung } from "../../app/anmeldung";
import { FehlerHinweis } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import s from "./auth.module.css";
import { codeGruppiert, codeNormalisieren } from "./eingaben";

/** Gerät mit einem Kopplungscode koppeln. Der Code kann über `/pair?code=…` mitkommen. */
export function KoppelnSeite({ code: vorgabe }: { code?: string }) {
  const { t } = useTranslation("auth");
  const navigate = useNavigate();
  const { status, lage, grund, uebernehmen } = useAnmeldung();
  // Gesperrt: Das ist kein „noch nicht gekoppelt“. Erst sagen, was passiert ist und wer hilft.
  const gesperrt = grund === "gesperrt";
  const [code, setCode] = useState(() => (vorgabe ? codeGruppiert(vorgabe) : ""));
  const [name, setName] = useState("");
  const [fehlerCode, setFehlerCode] = useState<string>();

  const koppeln = useMutation({
    mutationFn: () =>
      apiSenden<AuthStatus>(
        "POST",
        "/auth/pair",
        { code: codeNormalisieren(code), device_name: name.trim() || null },
        { still: true },
      ),
    onSuccess: (neu) => {
      uebernehmen(neu);
      zeigeMeldung({ ton: "erfolg", titel: t("koppeln.fertig", { name: neu.device?.name ?? "" }) });
      void navigate({ to: neu.role ? "/" : "/anmelden" });
    },
  });

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    if (!codeNormalisieren(code)) {
      setFehlerCode(t("koppeln.fehler_code"));
      return;
    }
    setFehlerCode(undefined);
    koppeln.mutate();
  };

  return (
    <section className={`panel ${s.karte}`} aria-labelledby="koppeln-titel">
      <header className={s.kopf}>
        <span className={s.symbol}>
          {gesperrt ? <ShieldX aria-hidden /> : <MonitorSmartphone aria-hidden />}
        </span>
        <h1 className="h-display" id="koppeln-titel">
          {gesperrt ? t("koppeln.gesperrt_titel") : t("koppeln.titel")}
        </h1>
        <p className="gedaempft">
          {gesperrt ? t("koppeln.gesperrt_text") : t("koppeln.einleitung")}
        </p>
      </header>
      {status?.device && (
        <p className={s.notiz}>{t("koppeln.bereits", { name: status.device.name })}</p>
      )}
      <form className={s.formular} onSubmit={absenden} noValidate>
        <TextInput
          size="lg"
          label={t("koppeln.code")}
          description={t("koppeln.code_hinweis")}
          inputWrapperOrder={["label", "input", "description", "error"]}
          value={code}
          onChange={(e) => setCode(e.currentTarget.value.toUpperCase())}
          error={fehlerCode}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={40}
          classNames={{ input: `num ${s.codeFeld}` }}
        />
        <TextInput
          size="md"
          label={t("koppeln.name")}
          description={t("koppeln.name_hinweis")}
          placeholder={t("koppeln.name_platzhalter")}
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          maxLength={100}
        />
        <FehlerHinweis fehler={koppeln.error} />
        <Button type="submit" size="lg" loading={koppeln.isPending}>
          {t("koppeln.absenden")}
        </Button>
      </form>
      {status?.setup_required && (
        <Link to="/einrichtung" className={s.link}>
          {t("koppeln.zur_einrichtung")}
        </Link>
      )}
      {/* Im offenen Betrieb ist Koppeln freiwillig: immer ein Weg zurück. */}
      {!lage.sperren && (
        <div className={s.auswege}>
          <p className={s.offenHinweis}>{t("koppeln.offen_hinweis")}</p>
          <Button component={Link} to="/" variant="default" leftSection={<ArrowLeft aria-hidden />}>
            {t("koppeln.abbrechen")}
          </Button>
        </div>
      )}
    </section>
  );
}
