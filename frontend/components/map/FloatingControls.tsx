"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useMapStore, WeatherLayer, LeadWeek } from "../../stores/mapStore";
import { api } from "../../lib/api";
import { Search, Mic, Droplets, CloudSun, AlertTriangle, Info, Sprout, ShieldAlert } from "lucide-react";

export function FloatingControls() {
  const {
    selectedLayer,
    setSelectedLayer,
    selectedWeek,
    setSelectedWeek,
    setSelectedPanchayat,
    isSimulatedBannerVisible,
  } = useMapStore();

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isListening, setIsListening] = useState(false);

  // Search handler
  const handleSearch = async (q: string) => {
    setSearchQuery(q);
    if (q.trim().length >= 2) {
      setIsSearching(true);
      try {
        const res = await api.geo.search(q);
        setSearchResults(res.results || []);
      } catch (err) {
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    } else {
      setSearchResults([]);
    }
  };

  // Voice Search (Web Speech API)
  const handleVoiceSearch = () => {
    if (typeof window !== "undefined" && ("webkitSpeechRecognition" in window || "SpeechRecognition" in window)) {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      const recognition = new SpeechRecognition();
      recognition.lang = "hi-IN"; // Default to Hindi/India regional
      recognition.interimResults = false;

      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          handleSearch(transcript);
        }
      };
      recognition.start();
    } else {
      alert("Voice search is not supported in this browser. Please type to search.");
    }
  };

  const weeks: { week: LeadWeek; days: string }[] = [
    { week: 1, days: "7 Days" },
    { week: 2, days: "14 Days" },
    { week: 3, days: "21 Days" },
    { week: 4, days: "28 Days" },
  ];

  const layers: { key: WeatherLayer; label: string; icon: any }[] = [
    { key: "onset", label: "Monsoon Onset", icon: Droplets },
    { key: "break", label: "Dry Spell (Break)", icon: CloudSun },
    { key: "excess", label: "Downpour Alert", icon: AlertTriangle },
  ];

  return (
    <div className="absolute top-4 inset-x-4 z-20 pointer-events-none flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
      {/* Search Bar & Voice Search */}
      <div className="relative pointer-events-auto w-full md:w-80 shadow-2xl">
        <div className="flex items-center bg-slate-900/90 backdrop-blur border border-slate-700/80 rounded-xl px-3 py-2 text-white">
          <Search className="w-4 h-4 text-slate-400 mr-2 shrink-0" />
          <input
            type="text"
            role="searchbox"
            aria-label="Search village, gram panchayat or district"
            placeholder="Search Panchayat or Block..."
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full bg-transparent text-sm focus:outline-none placeholder-slate-400"
          />
          <button
            type="button"
            aria-label="Voice search in regional language"
            onClick={handleVoiceSearch}
            className={`p-1.5 rounded-lg transition-colors ${
              isListening ? "bg-rose-600 text-white animate-pulse" : "hover:bg-slate-800 text-slate-400 hover:text-white"
            }`}
          >
            <Mic className="w-4 h-4" />
          </button>
        </div>

        {/* Search Results Dropdown */}
        {searchResults.length > 0 && (
          <ul
            role="listbox"
            aria-label="Search suggestions"
            className="absolute top-full left-0 right-0 mt-1.5 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-h-60 overflow-y-auto divide-y divide-slate-800 z-50 text-xs"
          >
            {searchResults.map((r: any) => (
              <li
                key={r.panchayat_id}
                role="option"
                aria-selected={false}
                tabIndex={0}
                onClick={() => {
                  setSelectedPanchayat({
                    id: r.panchayat_id,
                    name: r.panchayat_name,
                    block_name: r.block_name,
                    district_name: r.district_name,
                    state_name: r.state_name,
                    onset_prob: 0.5,
                    break_prob: 0.2,
                    excess_rain_prob: 0.2,
                    p10_rainfall_mm: 20,
                    p50_rainfall_mm: 40,
                    p90_rainfall_mm: 65,
                    confidence: 0.7,
                    data_source: "SIMULATED",
                    centroid_lon: r.lon,
                    centroid_lat: r.lat,
                  });
                  setSearchResults([]);
                  setSearchQuery("");
                }}
                className="p-3 hover:bg-sky-950/50 cursor-pointer text-slate-200 transition-colors"
              >
                <div className="font-semibold text-sky-400">{r.panchayat_name}</div>
                <div className="text-slate-400 text-[11px]">
                  Block: {r.block_name} &bull; {r.district_name}, {r.state_name}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Layer Toggles & Week Lead Pills */}
      <div className="pointer-events-auto flex flex-wrap items-center gap-2">
        {/* Layer Switchers */}
        <div
          role="radiogroup"
          aria-label="Monsoon Weather Layers"
          className="flex bg-slate-900/90 backdrop-blur border border-slate-700/80 p-1 rounded-xl shadow-lg"
        >
          {layers.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              role="radio"
              aria-checked={selectedLayer === key}
              onClick={() => setSelectedLayer(key)}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                selectedLayer === key
                  ? "bg-sky-700 text-white shadow-md"
                  : "text-slate-300 hover:text-white hover:bg-slate-800/60"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{label}</span>
            </button>
          ))}
        </div>

        {/* Lead Week Pills */}
        <div
          role="radiogroup"
          aria-label="Forecast Lead Week Outlook"
          className="flex bg-slate-900/90 backdrop-blur border border-slate-700/80 p-1 rounded-xl shadow-lg"
        >
          {weeks.map(({ week, days }) => (
            <button
              key={week}
              role="radio"
              aria-checked={selectedWeek === week}
              onClick={() => setSelectedWeek(week)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                selectedWeek === week
                  ? "bg-amber-500 text-slate-950 shadow-md font-bold"
                  : "text-slate-300 hover:text-white hover:bg-slate-800/60"
              }`}
            >
              Week {week} ({days})
            </button>
          ))}
        </div>

        {/* Portal Links */}
        <div className="flex items-center space-x-1 bg-slate-900/90 backdrop-blur border border-slate-700/80 p-1 rounded-xl shadow-lg">
          <Link
            href="/farmer"
            aria-label="Open Farmer Dashboard PWA"
            className="flex items-center space-x-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-emerald-400 hover:text-emerald-300 hover:bg-slate-800/80 transition-colors"
          >
            <Sprout className="w-3.5 h-3.5" />
            <span>Farmer</span>
          </Link>
          <Link
            href="/officer"
            aria-label="Open Extension Officer Portal"
            className="flex items-center space-x-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-sky-400 hover:text-sky-300 hover:bg-slate-800/80 transition-colors"
          >
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>Officer</span>
          </Link>
        </div>

        {/* Data Honesty Badge */}
        {isSimulatedBannerVisible && (
          <div
            role="status"
            aria-label="Forecast Data Source: Simulated"
            className="flex items-center space-x-1.5 bg-amber-500/10 border border-amber-500/30 text-amber-300 px-3 py-1.5 rounded-xl text-xs font-medium shadow-md backdrop-blur"
          >
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
            <span className="tracking-wide uppercase font-bold text-[11px]">DATA: SIMULATED</span>
          </div>
        )}
      </div>
    </div>
  );
}
