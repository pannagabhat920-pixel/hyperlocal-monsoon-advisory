"use client";

import React, { useEffect, useState } from "react";
import { useMapStore, PanchayatFeature, WeatherLayer } from "../../stores/mapStore";
import { AlertTriangle, Droplets, CloudSun, ShieldAlert } from "lucide-react";

interface Props {
  geojson: any;
  onSelectPanchayat?: (p: PanchayatFeature) => void;
}

export function ChoroplethMap2D({ geojson, onSelectPanchayat }: Props) {
  const { selectedLayer, selectedWeek, selectedPanchayat, setSelectedPanchayat } = useMapStore();
  const [hoveredFeature, setHoveredFeature] = useState<any>(null);

  const features = geojson?.features || [];

  // Helper to determine probability and patterns (Colour is never the only cue)
  const getProbability = (props: any): number => {
    if (selectedLayer === "onset") return props.onset_prob ?? 0;
    if (selectedLayer === "break") return props.break_prob ?? 0;
    return props.excess_rain_prob ?? 0;
  };

  const getStyleForProbability = (prob: number) => {
    // Patterns and numeric tiers accompany colors for accessibility
    if (prob >= 0.70) {
      return {
        fill: "#1e3a8a", // Dark blue / urgent
        pattern: "url(#pattern-dense-cross)",
        border: "#0f172a",
        label: "HIGH",
        icon: "▲",
      };
    } else if (prob >= 0.40) {
      return {
        fill: "#0284c7", // Medium sky blue
        pattern: "url(#pattern-diagonal-stripes)",
        border: "#0369a1",
        label: "MOD",
        icon: "■",
      };
    } else {
      return {
        fill: "#bae6fd", // Light blue
        pattern: "url(#pattern-dots)",
        border: "#7dd3fc",
        label: "LOW",
        icon: "●",
      };
    }
  };

  return (
    <div
      role="region"
      aria-label="2D Accessible Choropleth Monsoon Map Fallback"
      className="relative w-full h-full bg-slate-900 overflow-hidden flex flex-col items-center justify-center p-4"
      id="choropleth-2d-fallback"
    >
      {/* 2D Fallback Notice Header */}
      <div className="absolute top-4 left-4 z-20 bg-slate-800/90 backdrop-blur border border-slate-700 text-slate-200 px-3 py-2 rounded-lg text-xs flex items-center space-x-2 shadow-lg">
        <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
        <span className="font-medium">2D Accessible Fallback Mode (WebGL off)</span>
      </div>

      {/* SVG Map Container */}
      <svg
        viewBox="68 8 30 30"
        className="w-full h-full max-h-[80vh] transform scale-y-[-1]"
        aria-label="Interactive India Gram Panchayat Map"
      >
        <defs>
          {/* Accessible Patterns so color is never the only cue */}
          <pattern id="pattern-dense-cross" width="6" height="6" patternUnits="userSpaceOnUse">
            <path d="M 0,0 L 6,6 M 6,0 L 0,6" stroke="#ffffff" strokeWidth="1.2" opacity="0.6" />
          </pattern>
          <pattern id="pattern-diagonal-stripes" width="6" height="6" patternUnits="userSpaceOnUse">
            <path d="M 0,6 L 6,0" stroke="#ffffff" strokeWidth="1.2" opacity="0.5" />
          </pattern>
          <pattern id="pattern-dots" width="6" height="6" patternUnits="userSpaceOnUse">
            <circle cx="3" cy="3" r="1.2" fill="#0f172a" opacity="0.4" />
          </pattern>
        </defs>

        {/* Render Panchayats / Boundaries */}
        {features.map((feat: any, idx: number) => {
          const props = feat.properties || {};
          const prob = getProbability(props);
          const style = getStyleForProbability(prob);
          const isSelected = selectedPanchayat?.id === props.id;

          // Compute simple SVG polygon or circle representation if synthetic
          const coords = feat.geometry?.coordinates;
          const lon = props.centroid_lon || (coords?.[0]?.[0]?.[0] ?? (74 + (idx % 6) * 2));
          const lat = props.centroid_lat || (coords?.[0]?.[0]?.[1] ?? (15 + Math.floor(idx / 6) * 3));

          return (
            <g
              key={props.id || idx}
              tabIndex={0}
              role="button"
              aria-label={`${props.name || 'Panchayat'}: ${(prob * 100).toFixed(0)}% probability, tier ${style.label}`}
              onClick={() => {
                setSelectedPanchayat(props);
                if (onSelectPanchayat) onSelectPanchayat(props);
              }}
              onMouseEnter={() => setHoveredFeature(props)}
              onMouseLeave={() => setHoveredFeature(null)}
              className="cursor-pointer transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-amber-400"
            >
              {/* Synthetic polygon boundary or circular centroid */}
              <circle
                cx={lon}
                cy={lat}
                r={isSelected ? 1.4 : 1.0}
                fill={style.fill}
                stroke={isSelected ? "#f59e0b" : style.border}
                strokeWidth={isSelected ? 0.3 : 0.15}
              />
              <circle
                cx={lon}
                cy={lat}
                r={isSelected ? 1.4 : 1.0}
                fill={style.pattern}
                opacity={0.8}
              />
            </g>
          );
        })}
      </svg>

      {/* Accessible Legend - Color + Pattern + Numeric + Icon */}
      <div
        aria-label="Map Legend"
        className="absolute bottom-6 right-6 z-20 bg-slate-900/95 border border-slate-700/80 rounded-xl p-4 text-xs shadow-2xl backdrop-blur max-w-xs"
      >
        <div className="font-semibold text-slate-100 mb-2 flex items-center space-x-2">
          {selectedLayer === "onset" && <Droplets className="w-4 h-4 text-sky-400" />}
          {selectedLayer === "break" && <CloudSun className="w-4 h-4 text-amber-400" />}
          {selectedLayer === "excess" && <AlertTriangle className="w-4 h-4 text-rose-400" />}
          <span className="capitalize">{selectedLayer} Probability (Week {selectedWeek})</span>
        </div>
        <div className="space-y-2 text-slate-300">
          <div className="flex items-center space-x-3">
            <div className="w-5 h-5 rounded border border-slate-900 bg-[#1e3a8a] flex items-center justify-center text-white font-bold text-[10px]">
              ▲
            </div>
            <span>High Risk (&ge; 70%) &mdash; Dense Cross</span>
          </div>
          <div className="flex items-center space-x-3">
            <div className="w-5 h-5 rounded border border-sky-700 bg-[#0284c7] flex items-center justify-center text-white font-bold text-[10px]">
              ■
            </div>
            <span>Moderate (40% &ndash; 69%) &mdash; Diagonal</span>
          </div>
          <div className="flex items-center space-x-3">
            <div className="w-5 h-5 rounded border border-sky-300 bg-[#bae6fd] flex items-center justify-center text-slate-800 font-bold text-[10px]">
              ●
            </div>
            <span>Low (&lt; 40%) &mdash; Dots</span>
          </div>
        </div>
        <p className="text-[10px] text-slate-400 mt-3 pt-2 border-t border-slate-800">
          Symbols, patterns, and numeric values provide cues for accessibility.
        </p>
      </div>

      {/* Hover tooltip */}
      {hoveredFeature && (
        <div className="absolute top-16 left-6 z-30 bg-slate-950 border border-sky-500/50 rounded-lg p-3 text-xs shadow-xl text-white pointer-events-none">
          <p className="font-bold text-sky-300">{hoveredFeature.name}</p>
          <p className="text-slate-400">{hoveredFeature.block_name}, {hoveredFeature.district_name}</p>
          <p className="mt-1 font-mono text-amber-300">
            {selectedLayer.toUpperCase()}: {(getProbability(hoveredFeature) * 100).toFixed(0)}%
          </p>
        </div>
      )}
    </div>
  );
}
