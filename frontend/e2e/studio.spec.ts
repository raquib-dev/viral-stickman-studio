import { expect, Page, test } from "@playwright/test";

// Full dry run through the browser, gates on pause: niche -> discover -> patterns -> topic GATE ->
// hooks -> hook GATE -> script -> Phase A GATE (edited) -> Phase B -> render (mock) -> stitch -> package.
const SHOTS = process.env.VSS_SCREENSHOTS; // folder for review screenshots (optional)

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

async function waitForStatus(page: Page, pattern: RegExp, timeout = 180_000) {
  await expect(page.getByTestId("pipeline-status")).toHaveText(pattern, { timeout });
}

test("dry run from niche to packaged video through the UI", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));

  // Settings: dry run on, every gate paused
  await page.goto("/settings");
  await expect(page.getByTestId("dry-run")).toBeChecked();
  for (const g of ["topic", "hook", "phase_a", "render_cost"]) await page.getByTestId(`gate-mode-${g}`).selectOption("pause");
  await page.getByTestId("save-settings").click();
  await expect(page.getByText("✓ Saved.")).toBeVisible();
  await shot(page, "01-settings");

  // Niche setup (sample niche pre-filled: personal finance psychology, 60s, 9:16, Style 1 dark)
  await page.goto("/");
  await page.getByTestId("f-name").fill(`UI dry run ${Date.now() % 100000}`);
  await expect(page.getByTestId("f-niche")).toHaveValue("personal finance psychology");
  await page.getByTestId("niche-submit").click();
  await expect(page).toHaveURL(/\/p\/ui-dry-run-\d+\/niche/);
  await shot(page, "02-niche");

  // Run the whole pipeline; it pauses at the topic gate
  await page.getByTestId("run-pipeline").click();
  await waitForStatus(page, /needs you/);
  await expect(page.getByTestId("gate-banner")).toBeVisible();
  await page.getByTestId("nav-discover").click();
  await expect(page.getByTestId("outlier-table")).toBeVisible();
  await expect(page.getByText("SYNTHETIC - not real data").first()).toBeVisible();
  await shot(page, "03-discover");
  await page.getByTestId("nav-patterns").click();
  await expect(page.getByTestId("heatmap")).toBeVisible();
  await expect(page.getByTestId("profile-summary")).toContainText("re-hook at");
  await shot(page, "04-patterns");

  // Topic gate
  await page.getByTestId("nav-topics").click();
  await expect(page.getByTestId("gate-topic")).toContainText("pending");
  await page.getByTestId("topic-present-bias").click();
  await shot(page, "05-topics");
  await page.getByTestId("approve-topic").click();

  // Hook gate
  await waitForStatus(page, /needs you/);
  await page.getByTestId("nav-studio").click();
  await expect(page.getByTestId("gate-hook")).toContainText("pending");
  await page.getByTestId("hook-h1").click();
  await shot(page, "06-hooks");
  await page.getByTestId("approve-hook").click();

  // Phase A gate: edit the proposal, then approve the edited text
  await expect(page.getByTestId("gate-phase_a")).toContainText("pending", { timeout: 120_000 });
  await expect(page.getByTestId("phase-a-table")).toBeVisible();
  await page.getByRole("button", { name: "✎ Edit Phase A text" }).click();
  const editor = page.getByTestId("phase-a-editor");
  await editor.fill((await editor.inputValue()) + "\n_Edited in the browser test._\n");
  await page.getByRole("button", { name: "Save edits" }).click();
  await shot(page, "07-studio-phase-a");
  await page.getByTestId("approve-phase_a").click();

  // Phase B -> mock render (free, no cost gate) -> stitch -> package
  await waitForStatus(page, /completed/, 200_000);
  await page.getByTestId("nav-studio").click();
  await expect(page.getByTestId("prompt-1")).toBeVisible();
  await page.getByTestId("nav-render").click();
  await expect(page.getByTestId("clip-grid").locator("video")).toHaveCount(6);
  await expect(page.getByTestId("final-video")).toBeVisible();
  await expect(page.getByText("✓ all text inside the safe zone")).toBeVisible();
  await shot(page, "08-render");
  await page.getByTestId("nav-package").click();
  await expect(page.getByTestId("title-table").locator("tbody tr").first()).toBeVisible();
  await shot(page, "09-package");

  // Live log drawer has lines from the run
  await page.getByTestId("log-toggle").click();
  await expect(page.getByTestId("log-lines")).toContainText("[package]");

  // Dark mode renders the same screens
  await page.getByTestId("theme-toggle").click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  for (const p of ["patterns", "studio", "render"]) {
    await page.getByTestId(`nav-${p}`).click();
    await page.waitForTimeout(400);
    await shot(page, `10-dark-${p}`);
  }
  await page.getByTestId("theme-toggle").click();

  expect(errors, errors.join("\n")).toEqual([]);
});
