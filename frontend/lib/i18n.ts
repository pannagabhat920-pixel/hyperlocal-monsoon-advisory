/**
 * Internationalization helper for Pannaga UI messages across all 6 regional languages.
 */
import en from "../messages/en.json";
import hi from "../messages/hi.json";
import mr from "../messages/mr.json";
import kn from "../messages/kn.json";
import te from "../messages/te.json";
import pa from "../messages/pa.json";

export const LOCALES = ["en", "hi", "mr", "kn", "te", "pa"] as const;
export type Locale = (typeof LOCALES)[number];

export const LANGUAGES = [
  { code: "en", name: "English", label: "English" },
  { code: "hi", name: "Hindi", label: "हिंदी" },
  { code: "mr", name: "Marathi", label: "मराठी" },
  { code: "kn", name: "Kannada", label: "ಕನ್ನಡ" },
  { code: "te", name: "Telugu", label: "తెలుగు" },
  { code: "pa", name: "Punjabi", label: "ਪੰਜਾਬੀ" },
] as const;

export const MESSAGES: Record<Locale, typeof en> = {
  en,
  hi,
  mr,
  kn,
  te,
  pa,
};

export function getMessages(locale: string = "en"): typeof en {
  const norm = locale.toLowerCase().slice(0, 2) as Locale;
  return MESSAGES[norm] || MESSAGES.en;
}
