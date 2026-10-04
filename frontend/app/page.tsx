"use client";

import React from "react";
import dynamic from "next/dynamic";
import { FloatingControls } from "../components/map/FloatingControls";
import { AdvisoryDrawer } from "../components/map/AdvisoryDrawer";

// Dynamically import map component (client-side only to ensure WebGL/window availability)
const TerrainMap3D = dynamic(
  () => import("../components/map/TerrainMap3D").then((mod) => mod.TerrainMap3D),
  { ssr: false }
);

export default function Home() {

  return (
    <main className="relative w-screen h-screen overflow-hidden bg-slate-950 font-sans">
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
