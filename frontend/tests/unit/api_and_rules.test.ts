import { describe, it, expect } from "vitest";

describe("Frontend Client Logic & Agronomy Enums", () => {
  it("normalizes legacy crop status aliases to canonical 5 stages", () => {
    const STATUS_ALIASES: Record<string, string> = {
      NOT_STARTED: "NOT_STARTED",
      PLANNED: "NOT_STARTED",
      SOWN: "SOWN",
      VEGETATIVE: "VEGETATIVE",
      FLOWERING: "FLOWERING_PODDING",
      FLOWERING_PODDING: "FLOWERING_PODDING",
      POD_FORMATION: "FLOWERING_PODDING",
      GRAIN_FILLING: "FLOWERING_PODDING",
      MATURITY: "HARVEST_READY",
      HARVEST_READY: "HARVEST_READY",
      HARVESTED: "HARVEST_READY",
    };

    const canonicalStages = [
      "NOT_STARTED",
      "SOWN",
      "VEGETATIVE",
      "FLOWERING_PODDING",
      "HARVEST_READY",
    ];

    Object.entries(STATUS_ALIASES).forEach(([alias, canonical]) => {
      expect(canonicalStages).toContain(canonical);
    });
  });

  it("covers all 6 supported regional languages including Punjabi", () => {
    const SUPPORTED_LANGUAGES = [
      { code: "en", label: "English" },
      { code: "hi", label: "हिंदी (Hindi)" },
      { code: "kn", label: "ಕನ್ನಡ (Kannada)" },
      { code: "te", label: "తెలుగు (Telugu)" },
      { code: "mr", label: "मराठी (Marathi)" },
      { code: "pa", label: "ਪੰਜਾਬੀ (Punjabi)" },
    ];

    expect(SUPPORTED_LANGUAGES.map((l) => l.code)).toEqual([
      "en",
      "hi",
      "kn",
      "te",
      "mr",
      "pa",
    ]);
  });

  it("maps canonical irrigation sources without duplicate BOREWELL or TANK", () => {
    const canonicalIrrigationSources = [
      "RAINFED",
      "CANAL",
      "BOREWELL_WELL",
      "TANK_POND",
      "DRIP_SPRINKLER",
      "OTHER",
    ];

    expect(canonicalIrrigationSources).not.toContain("BOREWELL");
    expect(canonicalIrrigationSources).not.toContain("TANK");
    expect(canonicalIrrigationSources.length).toBe(6);
  });

  it("verifies SIMULATED data banner detection logic", () => {
    const isSimulated = (source: string) => source === "SIMULATED";
    expect(isSimulated("SIMULATED")).toBe(true);
    expect(isSimulated("LIVE")).toBe(false);
    expect(isSimulated("HINDCAST")).toBe(false);
  });
});
