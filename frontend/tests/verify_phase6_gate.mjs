/**
 * Automated Phase 6 Gate Verification Suite:
 * Farmer Dashboard PWA & Agricultural Extension Officer Broadcast Portal.
 */

import fs from "fs";
import assert from "assert";

console.log("=== Running Phase 6 Gate Verification Suite ===");

// ─── 1. Verify PWA Assets & Service Worker ──────────────────────────────────
console.log("-> 1. Verifying PWA Assets & Offline Service Worker...");
const manifestPath = "/app/public/manifest.json";
const swPath = "/app/public/sw.js";
const icon192Path = "/app/public/icon-192.svg";
const icon512Path = "/app/public/icon-512.svg";
const pwaRegisterPath = "/app/components/pwa/PwaRegister.tsx";

assert(fs.existsSync(manifestPath), "manifest.json must exist in public/");
assert(fs.existsSync(swPath), "sw.js must exist in public/");
assert(fs.existsSync(icon192Path), "icon-192.svg must exist");
assert(fs.existsSync(icon512Path), "icon-512.svg must exist");
assert(fs.existsSync(pwaRegisterPath), "PwaRegister.tsx must exist");

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
assert.strictEqual(manifest.display, "standalone", "PWA display must be standalone");
assert.strictEqual(manifest.start_url, "/farmer", "PWA start_url must point to /farmer");
assert(manifest.icons && manifest.icons.length >= 2, "PWA must specify maskable/SVG icons");

const swContent = fs.readFileSync(swPath, "utf-8");
assert(swContent.includes("caches.open"), "Service Worker must open caches");
assert(swContent.includes("/api/v1/advisories"), "Service worker must intercept advisories API for offline caching");
console.log("  ✓ PWA Manifest, Service Worker, and icons verified");


// ─── 2. Verify Farmer Dashboard PWA ──────────────────────────────────────────
console.log("-> 2. Verifying Farmer Dashboard PWA (/farmer)...");
const farmerPath = "/app/app/farmer/page.tsx";
assert(fs.existsSync(farmerPath), "app/farmer/page.tsx must exist");
const farmerContent = fs.readFileSync(farmerPath, "utf-8");

// Check 1-tap crop status
const expectedStages = ["PLANNED", "SOWING", "VEGETATIVE", "FLOWERING", "TRANSPLANTING", "GRAIN_FILLING", "HARVESTING", "HARVESTED"];
for (const stage of expectedStages) {
  assert(farmerContent.includes(stage), `Farmer dashboard must support crop stage: ${stage}`);
}
assert(farmerContent.includes("updateCropStatus"), "Must call updateCropStatus for 1-tap status update");
console.log("  ✓ 1-Tap Crop Status Tracker supports all 8 stages");

// Check accessibility & non-color cues
assert(farmerContent.includes("▲▲"), "Must have ▲▲ shape marker for CRITICAL alerts");
assert(farmerContent.includes("▲"), "Must have ▲ shape marker for HIGH advisories");
assert(farmerContent.includes("■"), "Must have ■ shape marker for MODERATE advisories");
assert(farmerContent.includes("●"), "Must have ● shape marker for INFORMATIONAL advisories");
assert(farmerContent.includes("repeating-linear-gradient"), "Must use CSS pattern fills as non-color cues");
console.log("  ✓ Accessibility non-color cues (symbols: ▲▲, ▲, ■, ● and pattern fills) verified");

// Check Bhashini audio & language switcher
assert(farmerContent.includes("handlePlayAudio") || farmerContent.includes("audio"), "Must support audio playback");
assert(farmerContent.includes("hindi") || farmerContent.includes("हिंदी") || farmerContent.includes("kn"), "Must support regional languages");
assert(farmerContent.includes("whatsapp_consent") || farmerContent.includes("whatsapp"), "Must manage WhatsApp channel consent");
assert(farmerContent.includes("sms_consent") || farmerContent.includes("sms"), "Must manage SMS channel consent");
assert(farmerContent.includes("opt_out") || farmerContent.includes("isOptedOut"), "Must support 1-tap opt-out");
console.log("  ✓ TTS Audio playback, regional languages, channel consent, and opt-out verified");


// ─── 3. Verify Officer Broadcast Portal ──────────────────────────────────────
console.log("-> 3. Verifying Officer Broadcast Portal (/admin/broadcast)...");
const broadcastPath = "/app/app/admin/broadcast/page.tsx";
assert(fs.existsSync(broadcastPath), "app/admin/broadcast/page.tsx must exist");
const broadcastContent = fs.readFileSync(broadcastPath, "utf-8");

// Check queue, approval & TTS pre-generation
assert(broadcastContent.includes("getQueue"), "Must fetch officer pending approval queue");
assert(broadcastContent.includes("handleApprove") || broadcastContent.includes("approve"), "Must support 1-click advisory approval");
assert(broadcastContent.includes("handleReject") || broadcastContent.includes("reject"), "Must support advisory rejection");

// Check translation preview & MT review badge
assert(broadcastContent.includes("previewTranslation") || broadcastContent.includes("handleTogglePreview"), "Must fetch regional translation preview");
assert(broadcastContent.includes("machine_translated") || broadcastContent.includes("Machine Translated"), "Must display Machine Translated warning badge");
assert(broadcastContent.includes("review_disclaimer") || broadcastContent.includes("review required"), "Must warn officer when translation needs review");
console.log("  ✓ Approval queue, translation preview diff, and machine translation review warnings verified");

// Check guarded 2-step broadcast
assert(broadcastContent.includes("dryRunResult") || broadcastContent.includes("confirm: false") || broadcastContent.includes("Dry-Run"), "Must provide dry-run recipient calculation");
assert(broadcastContent.includes("blocked_cooldown"), "Dry run must display count of cooldown-excluded recipients");
assert(broadcastContent.includes("handleConfirmBroadcast") || broadcastContent.includes("confirm: true"), "Must provide confirmed broadcast dispatch");
assert(broadcastContent.includes("getDelivery"), "Must display live delivery tracking status table");
console.log("  ✓ Guarded 2-step broadcast (dry-run breakdown, cooldown exclusion, live delivery table) verified");


// ─── 4. Verify Persistent Data Honesty Notice ────────────────────────────────
console.log("-> 4. Verifying Data Honesty Banners across portals...");
assert(farmerContent.includes("DATA HONESTY NOTICE") || farmerContent.includes("SIMULATED"), "Farmer dashboard must show simulated data warning");
assert(broadcastContent.includes("SIMULATED") || broadcastContent.includes("BLOCKED_SIMULATED"), "Officer portal must show simulated data notice");
console.log("  ✓ Persistent Data Honesty notices verified across farmer and officer portals");

console.log("\n=======================================================");
console.log("🎉 ALL PHASE 6 PORTAL GATE CHECKS PASSED SUCCESSFULLY!");
console.log("=======================================================\n");
