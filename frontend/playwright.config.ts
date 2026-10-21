import { defineConfig } from "@playwright/test";

// The UI e2e drives the built app served by FastAPI. Start the backend yourself (README → "Test the UI")
// or let `webServer` start it: it uses VSS_PYTHON (default "python") and throwaway data folders.
const PORT = Number(process.env.VSS_E2E_PORT ?? 8770);
const PY = process.env.VSS_PYTHON ?? "python";

export default defineConfig({
  testDir: "./e2e",
  timeout: 240_000,
  expect: { timeout: 20_000 },
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, viewport: { width: 1280, height: 900 }, screenshot: "only-on-failure", trace: "retain-on-failure" },
  webServer: {
    command: `${PY} -m uvicorn backend.app.main:app --port ${PORT}`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
