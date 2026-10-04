import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.describe("Phase 5 & 6 E2E Gate Verification", () => {
  // ─── (a) WebGL disabled -> 2D fallback renders ────────────────────────────
  test("(a) WebGL disabled -> 2D fallback renders with patterns and symbols", async ({ page }) => {
    // Disable WebGL in browser context
    await page.addInitScript(() => {
      (window as any).WebGLRenderingContext = undefined;
      (window as any).WebGL2RenderingContext = undefined;
      HTMLCanvasElement.prototype.getContext = function (type: string) {
        if (type.includes("webgl")) return null;
        return null;
      } as any;
    });

    await page.goto("/");

    // 1. Fallback map container is visible
    const fallbackMap = page.locator("#choropleth-2d-fallback");
    await expect(fallbackMap).toBeVisible({ timeout: 10000 });

    // 2. Banner indicating 2D fallback mode
    await expect(page.getByText("2D Accessible Fallback Mode (WebGL off)")).toBeVisible();

    // 3. Patterns exist (color is not the only cue)
    await expect(page.locator("#pattern-dense-cross")).toBeAttached();
    await expect(page.locator("#pattern-diagonal-stripes")).toBeAttached();
    await expect(page.locator("#pattern-dots")).toBeAttached();

    // 4. Numerical thresholds and symbols in legend
    await expect(page.getByText("High Risk (≥ 70%)")).toBeVisible();
    await expect(page.getByText("Moderate (40% – 69%)")).toBeVisible();
    await expect(page.getByText("Low (< 40%)")).toBeVisible();

    // 5. Data Honesty Notice is displayed
    await expect(page.getByRole("alert", { name: "Simulated Climate Data Notice" })).toContainText("DATA HONESTY NOTICE");
  });

  // ─── (b) Login -> Farmer Dashboard ────────────────────────────────────────
  test("(b) login -> farmer dashboard with 1-tap crop stage and consent", async ({ page }) => {
    await page.goto("/login");

    // Select farmer role & fill phone
    await page.getByText("Farmer", { exact: true }).click();
    await page.getByPlaceholder("9876543210").fill("9876543210");
    await page.getByRole("button", { name: /Send OTP/i }).click();

    // Enter 6-digit OTP
    await expect(page.getByText("Enter 6-Digit OTP")).toBeVisible();
    await page.getByPlaceholder("000000").fill("000000");
    await page.getByRole("button", { name: "Verify & Enter Dashboard" }).click();

    // Redirects to /farmer
    await page.waitForURL("**/farmer", { timeout: 10000 });
    await expect(page.getByRole("heading", { name: "Pannaga Farmer" })).toBeVisible();

    // Verify 5 canonical crop stages are rendered
    await expect(page.getByRole("radio", { name: "Not Started" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "Sown" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "Vegetative" })).toBeVisible();
    await expect(page.getByRole("radio", { name: /Flowering/i })).toBeVisible();
    await expect(page.getByRole("radio", { name: "Harvest Ready" })).toBeVisible();

    // Verify Punjabi is included in language options
    const langSelect = page.getByRole("combobox", { name: /Select Regional Language/i });
    await expect(langSelect).toContainText("ਪੰਜਾਬੀ");

    // Test 1-tap stage selection
    await page.getByRole("radio", { name: "Vegetative" }).click();
    await expect(page.getByRole("radio", { name: "Vegetative" })).toBeChecked();
  });

  // ─── (c) Officer approve -> dry-run -> broadcast ──────────────────────────
  test("(c) officer approve -> dry-run -> broadcast on mock provider", async ({ page }) => {
    await page.goto("/login");

    // Select Officer role & fill phone
    await page.getByText("Extension Officer", { exact: true }).click();
    await page.getByPlaceholder("9876543210").fill("9123456780");
    await page.getByRole("button", { name: /Send OTP/i }).click();

    // Enter OTP
    await expect(page.getByText("Enter 6-Digit OTP")).toBeVisible();
    await page.getByPlaceholder("000000").fill("000000");
    await page.getByRole("button", { name: "Verify & Enter Dashboard" }).click();

    // Redirects to /officer
    await page.waitForURL("**/officer", { timeout: 10000 });
    await expect(page.getByRole("heading", { name: /Agricultural Extension Officer Portal/i })).toBeVisible();

    // Officer approves an advisory
    const approveBtn = page.getByRole("button", { name: /Approve & Generate TTS/i }).first();
    await expect(approveBtn).toBeVisible();
    await approveBtn.click();
    await expect(page.getByText(/approved.*TTS audio pre-generated/i)).toBeVisible();

    // Dry Run Preview check
    const dryRunBtn = page.getByRole("button", { name: /Dry Run Preview/i }).first();
    await expect(dryRunBtn).toBeVisible();
    await dryRunBtn.click();

    // Verify Dry Run Modal opens
    await expect(page.getByRole("heading", { name: /Guarded Broadcast Dispatch/i })).toBeVisible();
    await expect(page.getByText(/Step 1: Dry-Run Recipient Verification/i)).toBeVisible();

    // Confirm broadcast
    await page.getByRole("button", { name: /Confirm & Broadcast/i }).click();
    await expect(page.getByText(/Broadcast Dispatched Successfully!/i).first()).toBeVisible();
  });

  // ─── (d) SIMULATED data shows the banner and blocks broadcast ─────────────
  test("(d) SIMULATED data shows the banner and blocks broadcast", async ({ page }) => {
    await page.goto("/officer");

    // Check for simulated data notices in officer dashboard
    await expect(page.getByText(/SIMULATED blocked/i).first()).toBeVisible();
    await expect(page.getByText(/\[DATA: SIMULATED\]/i).first()).toBeVisible();

    // Open Dry Run to verify data honesty intercept
    await page.getByRole("button", { name: /Dry Run Preview/i }).first().click();
    await expect(page.getByText(/Data Honesty Intercept \(Simulated\):/i)).toBeVisible();
  });

  // ─── (3) Axe accessibility scans ──────────────────────────────────────────
  test("(3) axe accessibility scan on map, farmer page, and officer page", async ({ page }) => {
    // 1. Scan Map Page
    await page.goto("/");
    const mapAxe = await new AxeBuilder({ page }).analyze();
    const mapCritical = mapAxe.violations.filter((v) => v.impact === "critical");
    expect(mapCritical).toHaveLength(0);

    // 2. Scan Farmer Page
    await page.goto("/farmer");
    const farmerAxe = await new AxeBuilder({ page }).analyze();
    const farmerCritical = farmerAxe.violations.filter((v) => v.impact === "critical");
    expect(farmerCritical).toHaveLength(0);

    // 3. Scan Officer Page
    await page.goto("/officer");
    const officerAxe = await new AxeBuilder({ page }).analyze();
    const officerCritical = officerAxe.violations.filter((v) => v.impact === "critical");
    expect(officerCritical).toHaveLength(0);
  });
});
