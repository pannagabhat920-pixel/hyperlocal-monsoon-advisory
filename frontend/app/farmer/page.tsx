"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Volume2,
  VolumeX,
  RefreshCw,
  Globe,
  Bell,
  CheckCircle,
  AlertTriangle,
  Info,
  ShieldAlert,
  WifiOff,
  Sprout,
  ArrowRight,
  Phone,
  MessageSquare,
  Check,
} from "lucide-react";
import { api } from "../../lib/api";
import { getMessages } from "../../lib/i18n";

const CROP_STAGES = [
  { id: "NOT_STARTED", label: "Not Started", icon: "🌱" },
  { id: "SOWN", label: "Sown", icon: "🚜" },
  { id: "VEGETATIVE", label: "Vegetative", icon: "🌿" },
  { id: "FLOWERING_PODDING", label: "Flowering / Podding", icon: "🌸" },
  { id: "HARVEST_READY", label: "Harvest Ready", icon: "🌾" },
];

const STAGE_I18N_KEYS: Record<string, "not_started" | "sown" | "vegetative" | "flowering_podding" | "harvest_ready"> = {
  NOT_STARTED: "not_started",
  SOWN: "sown",
  VEGETATIVE: "vegetative",
  FLOWERING_PODDING: "flowering_podding",
  HARVEST_READY: "harvest_ready",
};

const LANGUAGES = [
  { code: "en", name: "English", label: "English" },
  { code: "hi", name: "Hindi", label: "हिंदी" },
  { code: "kn", name: "Kannada", label: "ಕನ್ನಡ" },
  { code: "te", name: "Telugu", label: "తెలుగు" },
  { code: "mr", name: "Marathi", label: "मराठी" },
  { code: "pa", name: "Punjabi", label: "ਪੰਜਾਬੀ" },
];

export default function FarmerDashboard() {
  const [profile, setProfile] = useState<any>(null);
  const [advisories, setAdvisories] = useState<any[]>([]);
  const [hasSimulated, setHasSimulated] = useState<boolean>(false);
  const [currentLang, setCurrentLang] = useState<string>("en");
  const t = getMessages(currentLang);
  const [activeCropStatus, setActiveCropStatus] = useState<string>("NOT_STARTED");
  const [isUpdatingStatus, setIsUpdatingStatus] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string>("");

  // Consent states
  const [whatsappConsent, setWhatsappConsent] = useState<boolean>(true);
  const [smsConsent, setSmsConsent] = useState<boolean>(true);
  const [isOptedOut, setIsOptedOut] = useState<boolean>(false);

  // Audio state
  const [playingAudioId, setPlayingAudioId] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Offline detection
  const [isOffline, setIsOffline] = useState<boolean>(false);

  // Load initial data
  useEffect(() => {
    const handleOnline = () => setIsOffline(false);
    const handleOffline = () => setIsOffline(true);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    setIsOffline(!navigator.onLine);

    loadDashboardData();

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      if (audioRef.current) {
        audioRef.current.pause();
      }
    };
  }, []);

  const loadDashboardData = async () => {
    try {
      // 1. Load Farmer Profile (or fallback mock profile if unauthenticated)
      let prof = null;
      try {
        prof = await api.me.get();
        setProfile(prof);
        if (prof.preferred_language) setCurrentLang(prof.preferred_language);
        if (prof.crop_status) setActiveCropStatus(prof.crop_status);
        if (prof.whatsapp_consent !== undefined) setWhatsappConsent(prof.whatsapp_consent);
        if (prof.sms_consent !== undefined) setSmsConsent(prof.sms_consent);
        if (prof.opted_out_at) setIsOptedOut(true);
      } catch (err) {
        // Fallback for demo / unauthenticated preview
        const fallbackProf = {
          user_id: 1,
          phone_number: "+91 98765 43210",
          panchayat_id: 101,
          panchayat_name: "Channapatna Rural",
          district_name: "Ramanagara",
          crop_type: "PADDY",
          crop_status: "SOWING",
          preferred_language: "en",
          whatsapp_consent: true,
          sms_consent: true,
          opted_out_at: null,
        };
        setProfile(fallbackProf);
        setActiveCropStatus(fallbackProf.crop_status);
      }

      // 2. Load Advisories for the farmer's panchayat
      const advRes = await api.advisories.list();
      setAdvisories(advRes.advisories || []);
      setHasSimulated(advRes.simulated_banner || false);
    } catch (err) {
      console.warn("Failed to fetch advisories online, falling back to cache/mock:", err);
      // Fallback demo advisory if network down
      setAdvisories([
        {
          id: 101,
          severity: "CRITICAL",
          headline: "Severe 10-day Dry Spell Alert: Conserve Soil Moisture Immediately",
          content:
            "Monsoon break conditions detected over next 14 days. Probability of dry spell is 78%. Apply mulching, postpone non-essential chemical sprays, and prepare farm ponds for protective irrigation.",
          crop_type: "PADDY",
          data_source: "SIMULATED",
          simulated_banner: true,
          audio_url: null,
          created_at: new Date().toISOString(),
        },
        {
          id: 102,
          severity: "HIGH",
          headline: "Monsoon Onset Window Confirmed: Safe Sowing Window Active",
          content:
            "Cumulative rainfall expected to exceed 45mm in Week 2 with 72% confidence. Prepare seedbeds and ensure seed germination test before broadcast.",
          crop_type: "PADDY",
          data_source: "SIMULATED",
          simulated_banner: true,
          audio_url: null,
          created_at: new Date(Date.now() - 86400000).toISOString(),
        },
      ]);
      setHasSimulated(true);
    }
  };

  // 1-Tap Crop Status Update
  const handleCropStatusChange = async (statusId: string) => {
    setActiveCropStatus(statusId);
    setIsUpdatingStatus(true);
    try {
      await api.me.updateCropStatus(statusId);
      setStatusMessage(`Crop stage updated to ${statusId}`);
    } catch (err) {
      setStatusMessage(`Stage set to ${statusId} (cached)`);
    } finally {
      setIsUpdatingStatus(false);
      setTimeout(() => setStatusMessage(""), 3000);
    }
  };

  // Language Switcher
  const handleLanguageChange = async (langCode: string) => {
    setCurrentLang(langCode);
    try {
      await api.me.updateProfile({ preferred_language: langCode });
      // Reload advisories in selected language
      const advRes = await api.advisories.list();
      setAdvisories(advRes.advisories || []);
    } catch (err) {
      console.warn("Profile update failed or offline:", err);
    }
  };

  // Toggle Channel Consent
  const handleConsentToggle = async (channel: "whatsapp" | "sms") => {
    const newWhatsapp = channel === "whatsapp" ? !whatsappConsent : whatsappConsent;
    const newSms = channel === "sms" ? !smsConsent : smsConsent;

    if (channel === "whatsapp") setWhatsappConsent(newWhatsapp);
    if (channel === "sms") setSmsConsent(newSms);

    try {
      await api.me.updateProfile({
        whatsapp_consent: newWhatsapp,
        sms_consent: newSms,
      });
    } catch (err) {
      console.warn("Consent update error:", err);
    }
  };

  // Toggle Opt-Out
  const handleOptOutToggle = async () => {
    const nextOptOut = !isOptedOut;
    setIsOptedOut(nextOptOut);
    try {
      await api.me.updateProfile({ opt_out: nextOptOut });
      setStatusMessage(nextOptOut ? "Advisories paused (Opted out)" : "Advisories resumed");
    } catch (err) {
      console.warn("Opt-out update error:", err);
    } finally {
      setTimeout(() => setStatusMessage(""), 3000);
    }
  };

  // Bhashini Audio Playback
  const handlePlayAudio = (advisory: any) => {
    if (playingAudioId === advisory.id && audioRef.current) {
      audioRef.current.pause();
      setPlayingAudioId(null);
      return;
    }

    if (audioRef.current) {
      audioRef.current.pause();
    }

    const audioUrl = advisory.audio_url || `/api/v1/advisories/${advisory.id}/audio`;
    const audio = new Audio(audioUrl);
    audioRef.current = audio;
    setPlayingAudioId(advisory.id);

    audio.onended = () => setPlayingAudioId(null);
    audio.onerror = () => {
      // Synthesize browser TTS if server audio file not loaded
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        const utterance = new SpeechSynthesisUtterance(advisory.headline + ". " + advisory.content);
        utterance.lang = currentLang === "hi" ? "hi-IN" : currentLang === "kn" ? "kn-IN" : "en-IN";
        utterance.onend = () => setPlayingAudioId(null);
        window.speechSynthesis.speak(utterance);
      } else {
        alert("Audio playback failed and browser speech is not supported.");
        setPlayingAudioId(null);
      }
    };
    audio.play().catch(() => {
      // Fallback to Web Speech API
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        const utterance = new SpeechSynthesisUtterance(advisory.headline + ". " + advisory.content);
        utterance.lang = currentLang === "hi" ? "hi-IN" : "en-IN";
        utterance.onend = () => setPlayingAudioId(null);
        window.speechSynthesis.speak(utterance);
      }
    });
  };

  // Non-color accessibility styling: pattern + shape marker + text
  const getSeverityBadge = (severity: string) => {
    switch (severity?.toUpperCase()) {
      case "CRITICAL":
        return {
          bg: "bg-rose-950/80 border-rose-500 text-rose-200",
          symbol: "▲▲",
          label: "CRITICAL ALERT",
          pattern: "repeating-linear-gradient(45deg, rgba(244,63,94,0.15) 0, rgba(244,63,94,0.15) 10px, transparent 10px, transparent 20px)",
          icon: ShieldAlert,
        };
      case "HIGH":
        return {
          bg: "bg-amber-950/80 border-amber-500 text-amber-200",
          symbol: "▲",
          label: "HIGH ADVISORY",
          pattern: "repeating-linear-gradient(-45deg, rgba(245,158,11,0.15) 0, rgba(245,158,11,0.15) 8px, transparent 8px, transparent 16px)",
          icon: AlertTriangle,
        };
      case "MEDIUM":
      case "ADVISORY":
        return {
          bg: "bg-sky-950/80 border-sky-500 text-sky-200",
          symbol: "■",
          label: "MODERATE ADVISORY",
          pattern: "none",
          icon: Info,
        };
      default:
        return {
          bg: "bg-emerald-950/80 border-emerald-500 text-emerald-200",
          symbol: "●",
          label: "INFORMATIONAL",
          pattern: "none",
          icon: CheckCircle,
        };
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-16 font-sans">
      {/* ── 1. Offline & Data Honesty Banners ── */}
      {isOffline && (
        <div
          role="status"
          aria-live="polite"
          className="bg-amber-600 text-slate-950 px-4 py-2 text-xs font-bold flex items-center justify-center space-x-2"
        >
          <WifiOff className="w-4 h-4 shrink-0" />
          <span>OFFLINE MODE: Displaying your saved cached advisories.</span>
        </div>
      )}

      {hasSimulated && (
        <div
          role="alert"
          className="bg-amber-500/20 border-b border-amber-500/40 text-amber-300 px-4 py-2 text-xs font-medium flex items-center justify-between"
        >
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse shrink-0" />
            <span>
              <strong>DATA HONESTY NOTICE:</strong> Model is running with SIMULATED data for demonstration.
            </span>
          </div>
          <span className="text-[10px] uppercase font-bold tracking-wider bg-amber-500/30 px-2 py-0.5 rounded">
            Simulated
          </span>
        </div>
      )}

      {/* ── 2. Header & Language Switcher ── */}
      <header className="bg-slate-900/90 border-b border-slate-800 px-4 py-3 sticky top-0 z-30 backdrop-blur">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-sky-600 flex items-center justify-center text-white font-black text-lg">
              P
            </div>
            <div>
              <h1 className="text-base font-bold text-white tracking-tight" data-testid="farmer-portal-title">
                {t.farmer?.portalTitle || "Pannaga Farmer"}
              </h1>
              <p className="text-[11px] text-slate-400">
                {profile?.panchayat_name || "Gram Panchayat"} &bull; {profile?.crop_type || "Crop: Paddy"}
              </p>
            </div>
          </div>

          {/* Language Selector */}
          <div className="flex items-center space-x-1.5 bg-slate-800 rounded-lg p-1 border border-slate-700">
            <Globe className="w-3.5 h-3.5 text-slate-400 ml-1" />
            <select
              aria-label="Select Regional Language"
              data-testid="language-switcher"
              value={currentLang}
              onChange={(e) => handleLanguageChange(e.target.value)}
              className="bg-transparent text-xs text-slate-200 focus:outline-none pr-1 py-0.5 cursor-pointer"
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code} className="bg-slate-900 text-white">
                  {l.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      {/* Status Toast */}
      {statusMessage && (
        <div
          role="status"
          className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-emerald-600 text-white text-xs font-semibold px-4 py-2 rounded-full shadow-2xl flex items-center space-x-1.5 animate-bounce"
        >
          <Check className="w-3.5 h-3.5" />
          <span>{statusMessage}</span>
        </div>
      )}

      <main className="max-w-2xl mx-auto px-4 pt-4 space-y-6">
        {/* ── 3. 1-Tap Crop Stage Updater ── */}
        <section
          aria-labelledby="crop-stage-heading"
          className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 shadow-lg backdrop-blur"
        >
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Sprout className="w-4 h-4 text-emerald-400" />
              <h2 id="crop-stage-heading" data-testid="crop-stage-heading" className="text-sm font-bold text-white">
                {t.farmer?.cropStageTracker || "1-Tap Crop Status Tracker"}
              </h2>
            </div>
            <span className="text-[11px] text-slate-400">
              {t.farmer?.currentStage || "Current"}:{" "}
              <strong className="text-emerald-400">
                {t.stages[STAGE_I18N_KEYS[activeCropStatus]] || activeCropStatus}
              </strong>
            </span>
          </div>

          <div
            role="radiogroup"
            aria-label="Crop Growth Stages"
            className="grid grid-cols-4 gap-2"
          >
            {CROP_STAGES.map((stage) => {
              const isSelected = activeCropStatus === stage.id;
              const stageLabel = t.stages[STAGE_I18N_KEYS[stage.id]] || stage.label;
              return (
                <button
                  key={stage.id}
                  role="radio"
                  aria-checked={isSelected}
                  disabled={isUpdatingStatus}
                  onClick={() => handleCropStatusChange(stage.id)}
                  className={`flex flex-col items-center justify-center p-2 rounded-xl text-center border transition-all ${
                    isSelected
                      ? "bg-emerald-950/80 border-emerald-500 text-emerald-200 ring-2 ring-emerald-500/40 shadow-md font-bold scale-[1.02]"
                      : "bg-slate-800/40 border-slate-700/60 text-slate-400 hover:text-white hover:bg-slate-800"
                  }`}
                >
                  <span className="text-base mb-1" role="img" aria-hidden="true">
                    {stage.icon}
                  </span>
                  <span className="text-[11px] leading-tight font-medium">{stageLabel}</span>
                </button>
              );
            })}
          </div>
        </section>

        {/* ── 4. Active Agronomic Advisories List ── */}
        <section aria-labelledby="advisories-heading" className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 id="advisories-heading" data-testid="advisories-heading" className="text-base font-bold text-white flex items-center space-x-2">
              <Bell className="w-4 h-4 text-sky-400" />
              <span>{t.farmer?.advisoriesTitle || "Hyperlocal Agronomic Advisories"}</span>
            </h2>
            <button
              onClick={loadDashboardData}
              aria-label="Refresh advisories"
              className="text-xs text-sky-400 hover:text-sky-300 flex items-center space-x-1 p-1 rounded"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Refresh</span>
            </button>
          </div>

          {advisories.length === 0 ? (
            <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-6 text-center text-slate-400 text-sm">
              <CheckCircle className="w-8 h-8 text-emerald-400 mx-auto mb-2 opacity-60" />
              <p className="font-semibold text-slate-300">No active weather warnings</p>
              <p className="text-xs mt-1">Weather conditions are favorable for current crop stage.</p>
            </div>
          ) : (
            advisories.map((adv) => {
              const badge = getSeverityBadge(adv.severity);
              const isPlaying = playingAudioId === adv.id;

              return (
                <article
                  key={adv.id}
                  style={{ backgroundImage: badge.pattern }}
                  className={`border rounded-2xl p-4 transition-all shadow-md ${badge.bg} relative overflow-hidden`}
                >
                  {/* Severity & Non-color cue badge */}
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex items-center space-x-2">
                      <span
                        className="px-2 py-0.5 rounded text-[11px] font-black tracking-wide border flex items-center space-x-1"
                        style={{ borderColor: "currentColor" }}
                      >
                        <span aria-hidden="true" className="font-mono">
                          {badge.symbol}
                        </span>
                        <span>{badge.label}</span>
                      </span>

                      {adv.crop_type && (
                        <span className="text-[10px] uppercase font-semibold text-slate-400 bg-slate-900/60 px-2 py-0.5 rounded">
                          Crop: {adv.crop_type}
                        </span>
                      )}
                    </div>

                    {/* Bhashini Audio Playback Button */}
                    <button
                      type="button"
                      aria-label={isPlaying ? "Stop advisory audio" : "Listen to advisory audio placeholder (440 Hz synthetic tone)"}
                      onClick={() => handlePlayAudio(adv)}
                      className={`flex items-center space-x-1 px-3 py-1 rounded-full text-xs font-semibold shadow transition-all ${
                        isPlaying
                          ? "bg-rose-600 text-white animate-pulse"
                          : "bg-sky-700 hover:bg-sky-600 text-white"
                      }`}
                    >
                      {isPlaying ? (
                        <>
                          <VolumeX className="w-3.5 h-3.5" />
                          <span>Stop</span>
                        </>
                      ) : (
                        <>
                          <Volume2 className="w-3.5 h-3.5" />
                          <span>Listen (440Hz Placeholder Tone)</span>
                        </>
                      )}
                    </button>
                  </div>

                  <h3 className="text-base font-bold text-white mb-2 leading-snug">
                    {adv.headline}
                  </h3>

                  <p className="text-xs text-slate-200 leading-relaxed whitespace-pre-line mb-3 font-normal">
                    {adv.content}
                  </p>

                  <div className="flex items-center justify-between text-[11px] text-slate-400 pt-2 border-t border-slate-700/50">
                    <span>Issued: {new Date(adv.created_at).toLocaleDateString()}</span>
                    {adv.simulated_banner && (
                      <span className="font-mono text-amber-400 text-[10px] font-bold">
                        [DATA: SIMULATED]
                      </span>
                    )}
                  </div>
                </article>
              );
            })
          )}
        </section>

        {/* ── 5. Delivery Channel Preferences & Consent ── */}
        <section
          aria-labelledby="channels-heading"
          className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 space-y-4"
        >
          <div className="flex items-center justify-between">
            <h2 id="channels-heading" data-testid="channels-heading" className="text-sm font-bold text-white flex items-center space-x-2">
              <MessageSquare className="w-4 h-4 text-emerald-400" />
              <span>{t.farmer?.deliveryPreferences || "Direct Alert Channels (WhatsApp / SMS)"}</span>
            </h2>
            <span className="text-[11px] text-slate-400">{profile?.phone_number || "+91 Mobile"}</span>
          </div>

          <div className="space-y-2.5">
            {/* WhatsApp Consent */}
            <div className="flex items-center justify-between p-3 rounded-xl bg-slate-800/40 border border-slate-700/60">
              <div className="flex items-center space-x-2.5">
                <div className="w-7 h-7 rounded-lg bg-emerald-600/20 text-emerald-400 flex items-center justify-center font-bold text-xs">
                  WA
                </div>
                <div>
                  <div className="text-xs font-semibold text-white">{t.farmer?.whatsappConsent || "WhatsApp Alerts"}</div>
                  <div className="text-[10px] text-slate-400">Receive regional cards with audio links</div>
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-label="Toggle WhatsApp Alerts"
                aria-checked={whatsappConsent && !isOptedOut}
                disabled={isOptedOut}
                onClick={() => handleConsentToggle("whatsapp")}
                className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors ${
                  whatsappConsent && !isOptedOut ? "bg-emerald-600" : "bg-slate-700"
                }`}
              >
                <div
                  className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
                    whatsappConsent && !isOptedOut ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>

            {/* SMS Consent */}
            <div className="flex items-center justify-between p-3 rounded-xl bg-slate-800/40 border border-slate-700/60">
              <div className="flex items-center space-x-2.5">
                <div className="w-7 h-7 rounded-lg bg-sky-600/20 text-sky-400 flex items-center justify-center font-bold text-xs">
                  SMS
                </div>
                <div>
                  <div className="text-xs font-semibold text-white">{t.farmer?.smsConsent || "SMS Bulletins"}</div>
                  <div className="text-[10px] text-slate-400">Standard DLT-compliant text messages</div>
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-label="Toggle SMS Bulletins"
                aria-checked={smsConsent && !isOptedOut}
                disabled={isOptedOut}
                onClick={() => handleConsentToggle("sms")}
                className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors ${
                  smsConsent && !isOptedOut ? "bg-sky-600" : "bg-slate-700"
                }`}
              >
                <div
                  className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
                    smsConsent && !isOptedOut ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Opt-Out Button */}
          <div className="pt-2 border-t border-slate-800 flex items-center justify-between">
            <span className="text-xs text-slate-400">Pause receiving all weather advisories</span>
            <button
              type="button"
              onClick={handleOptOutToggle}
              className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                isOptedOut
                  ? "bg-emerald-900/60 text-emerald-300 border border-emerald-700"
                  : "bg-rose-900/40 hover:bg-rose-900/60 text-rose-300 border border-rose-800"
              }`}
            >
              {isOptedOut ? "Resume Advisories" : "Opt Out (Stop)"}
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}
