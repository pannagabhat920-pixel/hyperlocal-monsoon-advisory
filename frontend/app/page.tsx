"use client";

import React from "react";
import dynamic from "next/dynamic";
import { FloatingControls } from "../components/map/FloatingControls";
import { AdvisoryDrawer } from "../components/map/AdvisoryDrawer";
import { useMapStore } from "../stores/mapStore";
import { AlertCircle } from "lucide-react";

// Dynamically import map component (client-side only to ensure WebGL/window availability)
const TerrainMap3D = dynamic(
  () => import("../components/map/TerrainMap3D").then((mod) => mod.TerrainMap3D),
  { ssr: false }
);

export default function Home() {
  const { isSimulatedBannerVisible } = useMapStore();

  return (
    <main className="relative w-screen h-screen overflow-hidden bg-slate-950 font-sans">
      {/* Persistent Data Honesty Banner */}
      {isSimulatedBannerVisible && (
        <aside
          role="alert"
          aria-label="Simulated Climate Data Notice"
          className="w-full bg-amber-500 text-slate-950 px-4 py-1.5 text-xs font-bold text-center flex items-center justify-center space-x-2 z-30 relative shadow-md"
        >
          <AlertCircle className="w-4 h-4 text-slate-950 shrink-0" />
          <span>
            DATA HONESTY NOTICE: Model pipeline is running with SIMULATED data &mdash; real forecasts are blocked from delivery until trained on observed IMD/CHIRPS data.
          </span>
        </aside>
      )}

      {/* Floating Interactive Controls */}
      <FloatingControls />

      {/* 3D Map with automatic 2D Choropleth Fallback */}
      <div className="w-full h-full">
        <TerrainMap3D />
      </div>

      {/* Slide-out Farmer/Officer Advisory Drawer */}
      <AdvisoryDrawer />
    </main>
  );
}
