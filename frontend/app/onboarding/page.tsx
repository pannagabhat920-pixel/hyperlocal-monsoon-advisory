"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Sprout, Check, ShieldCheck, ArrowRight } from "lucide-react";
import { api } from "../../lib/api";

const CROPS = ["PADDY", "RAGI", "COTTON", "SOYBEAN", "MAIZE", "PULSES"];
const IRRIGATION_SOURCES = [
  { id: "CANAL", label: "Canal Irrigation" },
  { id: "BOREWELL_WELL", label: "Borewell / Open Well" },
  { id: "TANK_POND", label: "Tank / Farm Pond" },
  { id: "DRIP_SPRINKLER", label: "Drip / Sprinkler" },
  { id: "RAINFED", label: "Rainfed (No Irrigation)" },
];
const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "हिंदी (Hindi)" },
  { code: "kn", label: "ಕನ್ನಡ (Kannada)" },
  { code: "te", label: "తెలుగు (Telugu)" },
  { code: "mr", label: "मराठी (Marathi)" },
  { code: "pa", label: "ਪੰਜਾਬੀ (Punjabi)" },
];

export default function OnboardingPage() {
  const router = useRouter();
  const [cropType, setCropType] = useState("PADDY");
  const [irrigationSource, setIrrigationSource] = useState("RAINFED");
  const [farmSize, setFarmSize] = useState("2.5");
  const [preferredLang, setPreferredLang] = useState("en");
  const [hasConsent, setHasConsent] = useState(false);
  const [whatsappConsent, setWhatsappConsent] = useState(true);
  const [smsConsent, setSmsConsent] = useState(true);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!hasConsent) {
      alert("Please provide consent to receive weather-based agronomic advisories.");
      return;
    }

    setIsLoading(true);
    try {
      await api.me.updateProfile({
        crop_type: cropType,
        irrigation_source: irrigationSource,
        farm_size_acres: parseFloat(farmSize) || 2.0,
        preferred_language: preferredLang,
        whatsapp_consent: whatsappConsent,
        sms_consent: smsConsent,
      });
      router.push("/farmer");
    } catch (err) {
      // In local demo mode, proceed to dashboard
      router.push("/farmer");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-4 font-sans">
      <div className="bg-slate-900/90 border border-slate-800 rounded-3xl max-w-lg w-full p-8 shadow-2xl space-y-6 backdrop-blur">
        <div className="text-center space-y-1">
          <div className="w-10 h-10 rounded-xl bg-emerald-600/20 text-emerald-400 flex items-center justify-center mx-auto mb-2">
            <Sprout className="w-5 h-5" />
          </div>
          <h1 className="text-lg font-bold text-white tracking-tight">Farmer Farm Profile Onboarding</h1>
          <p className="text-xs text-slate-400">
            Customize advisories to your specific crop, water source, and language
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          {/* Primary Crop */}
          <div>
            <label className="block font-semibold text-slate-300 mb-1.5">Primary Kharif Crop</label>
            <div className="grid grid-cols-3 gap-2">
              {CROPS.map((c) => (
                <button
                  type="button"
                  key={c}
                  onClick={() => setCropType(c)}
                  className={`p-2 rounded-xl border text-center font-bold transition-all ${
                    cropType === c
                      ? "bg-emerald-600 border-emerald-500 text-white shadow-sm"
                      : "bg-slate-950 border-slate-800 text-slate-400 hover:text-white"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>

          {/* Irrigation Source */}
          <div>
            <label className="block font-semibold text-slate-300 mb-1.5">Irrigation Source</label>
            <select
              value={irrigationSource}
              onChange={(e) => setIrrigationSource(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
            >
              {IRRIGATION_SOURCES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          {/* Farm Size & Language */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="farm-size-input" className="block font-semibold text-slate-300 mb-1.5">
                Farm Size (Acres)
              </label>
              <input
                id="farm-size-input"
                type="number"
                step="0.1"
                value={farmSize}
                onChange={(e) => setFarmSize(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:border-sky-500"
                required
              />
            </div>

            <div>
              <label htmlFor="language-select" className="block font-semibold text-slate-300 mb-1.5">
                Preferred Language
              </label>
              <select
                id="language-select"
                value={preferredLang}
                onChange={(e) => setPreferredLang(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
              >
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Channel Consent & Opt-In Checkboxes */}
          <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
            <div className="font-semibold text-slate-300">Direct Alert Channels</div>
            <label className="flex items-center space-x-2 text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={whatsappConsent}
                onChange={(e) => setWhatsappConsent(e.target.checked)}
                className="rounded border-slate-700 text-emerald-600 focus:ring-0"
              />
              <span>Receive WhatsApp cards with Bhashini voice audio links</span>
            </label>
            <label className="flex items-center space-x-2 text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={smsConsent}
                onChange={(e) => setSmsConsent(e.target.checked)}
                className="rounded border-slate-700 text-sky-600 focus:ring-0"
              />
              <span>Receive DLT-compliant SMS emergency bulletins</span>
            </label>
          </div>

          {/* Explicit Informed Consent Checkbox */}
          <label className="flex items-start space-x-2.5 text-[11px] text-slate-300 cursor-pointer pt-1">
            <input
              type="checkbox"
              checked={hasConsent}
              onChange={(e) => setHasConsent(e.target.checked)}
              className="mt-0.5 rounded border-slate-700 text-sky-600 focus:ring-0"
              required
            />
            <span>
              I consent to receive weather-driven agronomic advisories from the Pannaga Monsoon Prediction System.
              I can pause or opt-out anytime via WhatsApp (reply STOP) or in my profile.
            </span>
          </label>

          <button
            type="submit"
            disabled={isLoading || !hasConsent}
            className="w-full py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold shadow-lg transition-all flex items-center justify-center space-x-1.5"
          >
            {isLoading ? (
              <span>Saving Profile...</span>
            ) : (
              <>
                <span>Complete Profile & Go to Dashboard</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>
      </div>
    </main>
  );
}
