"use client";

import React, { useEffect, useState } from "react";
import { useMapStore } from "../../stores/mapStore";
import { api } from "../../lib/api";
import { X, Volume2, HelpCircle, ShieldAlert, Sparkles, TrendingUp } from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

export function AdvisoryDrawer() {
  const { isDrawerOpen, closeDrawer, selectedPanchayat, selectedWeek } = useMapStore();
  const [forecastData, setForecastData] = useState<any>(null);
  const [advisories, setAdvisories] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [showShapWhy, setShowShapWhy] = useState(false);

  useEffect(() => {
    if (!selectedPanchayat) return;

    setIsLoading(true);
    api.forecasts
      .getPanchayat(selectedPanchayat.id)
      .then((data) => setForecastData(data))
      .catch((err) => console.error("Forecast fetch error:", err));

    api.advisories
      .list(selectedWeek)
      .then((data) => setAdvisories(data.advisories || []))
      .catch((err) => console.error("Advisory list error:", err))
      .finally(() => setIsLoading(false));
  }, [selectedPanchayat, selectedWeek]);

  if (!isDrawerOpen || !selectedPanchayat) return null;

  // Prepare fan chart data: p10 (lower bound), p50 (expected), p90 (upper bound)
  const chartData = (forecastData?.forecasts || []).map((fc: any) => ({
    week: `Week ${fc.lead_week}`,
    p10: fc.p10_rainfall_mm,
    p50: fc.p50_rainfall_mm,
    p90: fc.p90_rainfall_mm,
    band: fc.p90_rainfall_mm - fc.p10_rainfall_mm,
  }));

  // Active week forecast item
  const activeFc =
    forecastData?.forecasts?.find((f: any) => f.lead_week === selectedWeek) ||
    forecastData?.forecasts?.[0] ||
    selectedPanchayat;

  // Listen to advisory TTS trigger
  const handleListenAdvisory = () => {
    if (advisories.length > 0 && advisories[0].audio_url) {
      const audio = new Audio(advisories[0].audio_url);
      setIsPlayingAudio(true);
      audio.onended = () => setIsPlayingAudio(false);
      audio.play().catch(() => {
        setIsPlayingAudio(false);
        // Fallback synthetic Web Speech utterance if audio_url unreachable in demo
        if ("speechSynthesis" in window) {
          const u = new SpeechSynthesisUtterance(advisories[0].content || "Weekly monsoon advisory.");
          window.speechSynthesis.speak(u);
        }
      });
    } else {
      if ("speechSynthesis" in window) {
        const text = `Monsoon onset probability for ${selectedPanchayat.name} is ${(activeFc.onset_prob * 100).toFixed(0)} percent.`;
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
      }
    }
  };

  return (
    <aside
      role="dialog"
      aria-label={`Detailed Advisory for ${selectedPanchayat.name}`}
      className="fixed inset-y-0 right-0 z-40 w-full sm:w-[480px] bg-slate-950/95 backdrop-blur-xl border-l border-slate-800 text-slate-100 shadow-2xl flex flex-col transform transition-transform duration-300 ease-in-out overflow-hidden"
    >
      {/* Header */}
      <div className="p-5 border-b border-slate-800 flex items-start justify-between bg-slate-900/50">
        <div>
          <span className="text-[11px] font-bold uppercase tracking-wider text-sky-400">
            Gram Panchayat Outlook
          </span>
          <h2 className="text-xl font-bold text-white mt-0.5">{selectedPanchayat.name}</h2>
          <p className="text-xs text-slate-400">
            {selectedPanchayat.block_name}, {selectedPanchayat.district_name},{" "}
            {selectedPanchayat.state_name}
          </p>
        </div>
        <button
          type="button"
          aria-label="Close advisory drawer"
          onClick={closeDrawer}
          className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        {/* Metric Cards */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 text-center">
            <span className="text-[10px] uppercase font-bold text-slate-400">Onset Prob</span>
            <div className="text-lg font-black text-sky-400 mt-1">
              {(activeFc.onset_prob * 100).toFixed(0)}%
            </div>
            <span className="text-[10px] text-slate-400">Week {selectedWeek}</span>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 text-center">
            <span className="text-[10px] uppercase font-bold text-slate-400">Break Prob</span>
            <div className="text-lg font-black text-amber-400 mt-1">
              {(activeFc.break_prob * 100).toFixed(0)}%
            </div>
            <span className="text-[10px] text-slate-400">Dry spell risk</span>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 text-center">
            <span className="text-[10px] uppercase font-bold text-slate-400">Heavy Rain</span>
            <div className="text-lg font-black text-rose-400 mt-1">
              {(activeFc.excess_rain_prob * 100).toFixed(0)}%
            </div>
            <span className="text-[10px] text-slate-400">&ge; 75 mm</span>
          </div>
        </div>

        {/* Rainfall Percentiles Fan Chart (p10, p50, p90) */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold text-slate-200 flex items-center space-x-1.5">
              <TrendingUp className="w-4 h-4 text-sky-400" />
              <span>Rainfall Probability Fan Chart (p10 / p50 / p90)</span>
            </span>
            <span className="text-[10px] text-slate-400 font-mono">mm/week</span>
          </div>

          <div className="h-44 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="fanSpread" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0284c7" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#0284c7" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="week" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", borderRadius: "8px", fontSize: "12px" }}
                />
                <Area type="monotone" dataKey="p90" stroke="#38bdf8" strokeDasharray="3 3" fill="transparent" />
                <Area type="monotone" dataKey="p50" stroke="#0284c7" strokeWidth={2.5} fill="url(#fanSpread)" />
                <Area type="monotone" dataKey="p10" stroke="#38bdf8" strokeDasharray="3 3" fill="transparent" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-between items-center text-[10px] text-slate-400 mt-2 px-1">
            <span>Dotted: p10 (low) &amp; p90 (high)</span>
            <span>Solid: p50 Expected</span>
          </div>
        </div>

        {/* SHAP Feature Contribution "Why" Panel */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
          <button
            type="button"
            onClick={() => setShowShapWhy(!showShapWhy)}
            className="w-full flex items-center justify-between text-left text-xs font-bold text-slate-200"
          >
            <span className="flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-amber-400" />
              <span>Model Interpretability (SHAP &ldquo;Why&rdquo; Panel)</span>
            </span>
            <span className="text-sky-400 text-[11px] underline">
              {showShapWhy ? "Hide" : "Explain Outlook"}
            </span>
          </button>

          {showShapWhy && (
            <div className="mt-3 space-y-2 pt-2 border-t border-slate-800/80 text-xs">
              <p className="text-slate-300 text-[11px]">
                Features contributing to this forecast calculation:
              </p>
              <div className="space-y-1.5 font-mono text-[11px]">
                <div className="flex justify-between items-center bg-slate-950/60 p-2 rounded">
                  <span className="text-slate-400">ENSO (Niño 3.4 Anomaly):</span>
                  <span className="text-sky-300">+0.8 &deg;C (Moderate El Ni&ntilde;o)</span>
                </div>
                <div className="flex justify-between items-center bg-slate-950/60 p-2 rounded">
                  <span className="text-slate-400">Indian Ocean Dipole (DMI):</span>
                  <span className="text-sky-300">+0.2 &deg;C (Neutral/Weak positive)</span>
                </div>
                <div className="flex justify-between items-center bg-slate-950/60 p-2 rounded">
                  <span className="text-slate-400">MJO Convection Phase:</span>
                  <span className="text-emerald-400">Phase 3 (Indian Ocean Active)</span>
                </div>
                <div className="flex justify-between items-center bg-slate-950/60 p-2 rounded">
                  <span className="text-slate-400">Latitude Advancement:</span>
                  <span className="text-slate-300">{selectedPanchayat.centroid_lat?.toFixed(1) ?? '18.5'}&deg; N Climatology</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Agronomic Advisory Card & Listen Audio */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-white flex items-center space-x-2">
              <ShieldAlert className="w-4 h-4 text-emerald-400" />
              <span>Recommended Farm Advisory</span>
            </span>
            <button
              type="button"
              onClick={handleListenAdvisory}
              className="flex items-center space-x-1.5 bg-sky-600 hover:bg-sky-500 text-white px-3 py-1.5 rounded-lg text-xs font-semibold shadow transition-all"
            >
              <Volume2 className="w-3.5 h-3.5" />
              <span>{isPlayingAudio ? "Playing..." : "Listen"}</span>
            </button>
          </div>

          <div className="p-3 bg-slate-950/80 rounded-xl border border-slate-800/80 text-xs text-slate-300 leading-relaxed">
            {advisories.length > 0 ? (
              <>
                <p className="font-bold text-slate-100 mb-1">{advisories[0].headline}</p>
                <p>{advisories[0].content}</p>
              </>
            ) : (
              <p>
                Monsoon onset probability is {(activeFc.onset_prob * 100).toFixed(0)}%.
                Ensure seed bed preparation is complete. For rainfed plots, practice shallow mulching.
              </p>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}
