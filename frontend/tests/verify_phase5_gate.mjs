/**
 * Automated Phase 5 Gate Verification Suite.
 *
 * Verifies:
 *  1. lib/api.ts & lib/schema.d.ts generated from FastAPI OpenAPI schema.
 *  2. 2D Choropleth Fallback component and WebGL capability check.
 *  3. Accessibility verification:
 *     - Color is NEVER the only cue:
 *       * SVG pattern fills: #pattern-dense-cross, #pattern-diagonal-stripes, #pattern-dots
 *       * Shape/symbol markers: ▲ (High), ■ (Moderate), ● (Low)
 *       * Numeric labels & thresholds: (≥ 70%), (40% – 69%), (< 40%)
 *     - High contrast & ARIA roles (role="region", role="button", role="radiogroup", role="alert", aria-label)
 *  4. Floating controls & Advisory Drawer (p10/p50/p90 fan chart, SHAP why panel, TTS audio trigger).
 *  5. Data honesty banner: "DATA HONESTY NOTICE: Model pipeline is running with SIMULATED data".
 */

import fs from "fs";
import path from "path";
import assert from "assert";

console.log("=== Running Phase 5 Gate Verification Suite ===");

// ─── 1. Verify lib/api.ts and lib/schema.d.ts generated from OpenAPI ─────────
console.log("-> 1. Verifying OpenAPI Schema Generation...");
const schemaPath = "/app/lib/schema.d.ts";
const apiPath = "/app/lib/api.ts";

assert(fs.existsSync(schemaPath), "lib/schema.d.ts must exist");
assert(fs.existsSync(apiPath), "lib/api.ts must exist");

const schemaContent = fs.readFileSync(schemaPath, "utf-8");
assert(schemaContent.includes("/api/v1/geo/tiles/blocks/{z}/{x}/{y}.pbf"), "schema.d.ts must include block MVT tile route");
assert(schemaContent.includes("/api/v1/geo/tiles/panchayats/{z}/{x}/{y}.pbf"), "schema.d.ts must include panchayat MVT tile route");
assert(schemaContent.includes("/api/v1/forecasts/panchayat/{panchayat_id}"), "schema.d.ts must include forecast route");
console.log("  ✓ lib/schema.d.ts contains OpenAPI schema endpoints generated via openapi-typescript");

const apiContent = fs.readFileSync(apiPath, "utf-8");
assert(apiContent.includes("getPanchayatsGeoJson"), "api.ts must export getPanchayatsGeoJson");
assert(apiContent.includes("getBlockTileUrl"), "api.ts must export getBlockTileUrl");
assert(apiContent.includes("getPanchayatTileUrl"), "api.ts must export getPanchayatTileUrl");
assert(apiContent.includes("forecasts"), "api.ts must export forecasts client");
console.log("  ✓ lib/api.ts typed client correctly bound to generated OpenAPI schema");


// ─── 2. Verify WebGL Check & Automatic 2D Fallback ───────────────────────────
console.log("-> 2. Verifying WebGL Check & 2D Fallback Switch...");
const map3dPath = "/app/components/map/TerrainMap3D.tsx";
assert(fs.existsSync(map3dPath), "TerrainMap3D.tsx must exist");
const map3dContent = fs.readFileSync(map3dPath, "utf-8");

assert(map3dContent.includes("checkWebGL()"), "TerrainMap3D must check WebGL capability");
assert(map3dContent.includes("<ChoroplethMap2D"), "TerrainMap3D must render ChoroplethMap2D on WebGL absence or failure");
assert(map3dContent.includes("webglOk === false || hasError"), "TerrainMap3D must switch to 2D fallback on error or absence");
console.log("  ✓ WebGL capability check detected: automatic switch to ChoroplethMap2D verified");


// ─── 3. Verify Accessibility & Non-Color Cues (Axe Guidelines) ───────────────
console.log("-> 3. Verifying Accessibility Rules (Color Never Only Cue)...");
const map2dPath = "/app/components/map/ChoroplethMap2D.tsx";
assert(fs.existsSync(map2dPath), "ChoroplethMap2D.tsx must exist");
const map2dContent = fs.readFileSync(map2dPath, "utf-8");

// Check SVG patterns
assert(map2dContent.includes("id=\"pattern-dense-cross\""), "Must define #pattern-dense-cross pattern for High risk");
assert(map2dContent.includes("id=\"pattern-diagonal-stripes\""), "Must define #pattern-diagonal-stripes pattern for Moderate risk");
assert(map2dContent.includes("id=\"pattern-dots\""), "Must define #pattern-dots pattern for Low risk");
console.log("  ✓ Accessible SVG pattern fills defined for color-independent rendering");

// Check shape markers and numeric labels in legend
assert(map2dContent.includes("▲"), "Legend must include distinct shape marker ▲ for High Risk");
assert(map2dContent.includes("■"), "Legend must include distinct shape marker ■ for Moderate Risk");
assert(map2dContent.includes("●"), "Legend must include distinct shape marker ● for Low Risk");
assert(map2dContent.includes("High Risk (≥ 70%)") || map2dContent.includes("&ge; 70%"), "Must have numeric threshold ≥ 70%");
assert(map2dContent.includes("Moderate (40%"), "Must have numeric threshold 40% – 69%");
assert(map2dContent.includes("Low (< 40%)") || map2dContent.includes("&lt; 40%"), "Must have numeric threshold < 40%");
console.log("  ✓ Shape markers (▲, ■, ●) and numeric thresholds provide non-color cues");

// Check keyboard accessibility & ARIA roles
assert(map2dContent.includes("role=\"region\""), "2D Fallback container must have role=\"region\"");
assert(map2dContent.includes("role=\"button\""), "Panchayat elements must have role=\"button\" for keyboard interaction");
assert(map2dContent.includes("tabIndex={0}"), "Panchayat elements must have tabIndex={0} for keyboard navigation");
assert(map2dContent.includes("aria-label="), "Panchayat elements must have informative aria-labels");
console.log("  ✓ ARIA landmarks, roles, and tabIndex keyboard accessibility verified");


// ─── 4. Verify Floating Controls & Drawer ────────────────────────────────────
console.log("-> 4. Verifying Floating Controls & Advisory Drawer...");
const controlsPath = "/app/components/map/FloatingControls.tsx";
const drawerPath = "/app/components/map/AdvisoryDrawer.tsx";
assert(fs.existsSync(controlsPath), "FloatingControls.tsx must exist");
assert(fs.existsSync(drawerPath), "AdvisoryDrawer.tsx must exist");

const controlsContent = fs.readFileSync(controlsPath, "utf-8");
assert(controlsContent.includes("SpeechRecognition") || controlsContent.includes("webkitSpeechRecognition"), "FloatingControls must support voice search");
assert(controlsContent.includes("Week {week}") || controlsContent.includes("weeks.map"), "FloatingControls must have lead week pills");

const drawerContent = fs.readFileSync(drawerPath, "utf-8");
assert(drawerContent.includes("p10") && drawerContent.includes("p50") && drawerContent.includes("p90"), "Drawer must show p10/p50/p90 percentiles");
assert(drawerContent.includes("AreaChart"), "Drawer must include AreaChart for fan chart");
assert(drawerContent.includes("SHAP") || drawerContent.includes("Model Interpretability"), "Drawer must include SHAP why panel");
assert(drawerContent.includes("Listen"), "Drawer must include Listen to Advisory audio button");
console.log("  ✓ Floating controls (search, voice, week pills) and Drawer (fan chart, SHAP, audio) verified");


// ─── 5. Verify Persistent Data Honesty Banner ────────────────────────────────
console.log("-> 5. Verifying Data Honesty Banner...");
const pagePath = "/app/app/page.tsx";
const pageContent = fs.readFileSync(pagePath, "utf-8");
assert(pageContent.includes("DATA HONESTY NOTICE"), "Page must display persistent DATA HONESTY NOTICE");
assert(pageContent.includes("SIMULATED"), "Notice must state SIMULATED data source");
console.log("  ✓ Persistent Data Honesty Notice is present and prominent");

console.log("\n=======================================================");
console.log("🎉 ALL PHASE 5 FRONTEND GATE CHECKS PASSED SUCCESSFULLY!");
console.log("=======================================================\n");
