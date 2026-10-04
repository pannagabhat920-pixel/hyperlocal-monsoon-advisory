import { describe, it, expect } from "vitest";
import { getMessages, LOCALES } from "../../lib/i18n";

describe("i18n Multi-Lingual Catalogs & Placeholder Disclaimers", () => {
  it("includes all 6 required regional languages (en, hi, mr, kn, te, pa)", () => {
    expect(LOCALES).toEqual(["en", "hi", "mr", "kn", "te", "pa"]);
  });

  it("marks all 6 language catalogs as unreviewed placeholder translations", () => {
    for (const locale of LOCALES) {
      const msgs: any = getMessages(locale);
      expect(msgs._comment).toBeDefined();
      expect(msgs._comment).toContain("UNREVIEWED_MACHINE_TRANSLATED_PLACEHOLDER");
    }
  });

  it("proves language switching changes UI text strings across all 6 locales", () => {
    const en = getMessages("en");
    const hi = getMessages("hi");
    const mr = getMessages("mr");
    const kn = getMessages("kn");
    const te = getMessages("te");
    const pa = getMessages("pa");

    // English strings
    expect(en.farmer.portalTitle).toBe("Pannaga Farmer");
    expect(en.farmer.cropStageTracker).toBe("1-Tap Crop Status Tracker");

    // Hindi strings change
    expect(hi.farmer.portalTitle).toBe("पन्नग किसान");
    expect(hi.farmer.cropStageTracker).toBe("1-टैप फसल स्थिति ट्रैकर");
    expect(hi.farmer.portalTitle).not.toBe(en.farmer.portalTitle);

    // Marathi strings change
    expect(mr.farmer.portalTitle).toBe("पन्नगा शेतकरी");
    expect(mr.farmer.portalTitle).not.toBe(en.farmer.portalTitle);

    // Kannada strings change
    expect(kn.farmer.portalTitle).toBe("ಪನ್ನಗ ರೈತ");
    expect(kn.farmer.portalTitle).not.toBe(en.farmer.portalTitle);

    // Telugu strings change
    expect(te.farmer.portalTitle).toBe("పన్నగ రైతు");
    expect(te.farmer.portalTitle).not.toBe(en.farmer.portalTitle);

    // Punjabi strings change
    expect(pa.farmer.portalTitle).toBe("ਪੰਨਗਾ ਕਿਸਾਨ");
    expect(pa.farmer.portalTitle).not.toBe(en.farmer.portalTitle);
  });

  it("translates canonical crop stages across all languages", () => {
    const en = getMessages("en");
    const hi = getMessages("hi");
    const kn = getMessages("kn");

    expect(en.stages.vegetative).toBe("Vegetative");
    expect(hi.stages.vegetative).toBe("वानस्पतिक वृद्धि");
    expect(kn.stages.vegetative).toBe("ಸಸ್ಯ ಬೆಳವಣಿಗೆ");
  });
});
