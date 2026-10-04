import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.describe("Phase 5 Gate: Map & Accessibility Verification", () => {
  test("shows 2D accessible choropleth fallback when WebGL is disabled", async ({
    page,
  }) => {
    // Disable WebGL in the browser context before loading
    await page.addInitScript(() => {
      // Stub WebGLRenderingContext to simulate environment without WebGL support
      (window as any).WebGLRenderingContext = undefined;
      (window as any).WebGL2RenderingContext = undefined;
      HTMLCanvasElement.prototype.getContext = function (type: string) {
        if (type === "webgl" || type === "experimental-webgl" || type === "webgl2") {
          return null;
        }
        return null;
      } as any;
    });

    await page.goto("/");

    // 1. Verify 2D Fallback is displayed
    const fallbackMap = page.locator("#choropleth-2d-fallback");
    await expect(fallbackMap).toBeVisible({ timeout: 10000 });

    // 2. Verify fallback notice banner is present
    await expect(
      page.getByText("2D Accessible Fallback Mode (WebGL off)")
    ).toBeVisible();

    // 3. Verify color is never the only cue: check pattern definitions in DOM
    const patternCross = page.locator("#pattern-dense-cross");
    const patternStripes = page.locator("#pattern-diagonal-stripes");
    const patternDots = page.locator("#pattern-dots");

    await expect(patternCross).toBeAttached();
    await expect(patternStripes).toBeAttached();
    await expect(patternDots).toBeAttached();

    // 4. Verify Accessible Legend with symbols and numeric thresholds
    await expect(page.getByText("High Risk (≥ 70%)")).toBeVisible();
    await expect(page.getByText("Moderate (40% – 69%)")).toBeVisible();
    await expect(page.getByText("Low (< 40%)")).toBeVisible();

    // 5. Verify Data Honesty Notice is displayed
    await expect(page.getByRole("alert", { name: "Simulated Climate Data Notice" })).toContainText("DATA HONESTY NOTICE");

    // 6. Run Axe accessibility scan
    const accessibilityScanResults = await new AxeBuilder({ page })
      .include("#choropleth-2d-fallback")
      .analyze();

    // Zero critical accessibility violations
    const criticalViolations = accessibilityScanResults.violations.filter(
      (v) => v.impact === "critical"
    );
    expect(criticalViolations).toHaveLength(0);
  });
});
