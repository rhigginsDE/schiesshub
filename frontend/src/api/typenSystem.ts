/**
 * Sprechende Namen für die Typen von Anmeldung, Rechten und Sicherung (Felder englisch, wie vom
 * Backend geliefert). Quelle ist `schema.gen.ts`; von Hand gepflegt wird nichts.
 */
import type { components } from "./schema.gen";

type Schemas = components["schemas"];

export type AuthStatus = Schemas["StatusOut"];
export type AuthPerson = Schemas["UserBrief"];
export type Geraet = Schemas["DeviceOut"];
export type Kopplungscode = Schemas["PairingCodeOut"];
export type Rolle = Schemas["RoleOut"];
export type Berechtigung = Schemas["PermissionOut"];
export type Person = Schemas["UserOut"];
export type AuditEintrag = Schemas["AuditEntryOut"];
export type AuditSeite = Schemas["AuditPageOut"];

export type SicherungsStatus = Schemas["BackupStatusOut"];
export type SicherungsEinstellungen = Schemas["BackupSettings"];
export type SicherungsLauf = Schemas["RunOut"];
export type SicherungsWarnung = Schemas["WarningOut"];
export type SicherungsPruefung = Schemas["VerifyOut"];
