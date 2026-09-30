// Playwright for the existing Next.js page. The browser talks to port 3000 only.

// Config helper.
import { defineConfig } from "@playwright/test";

// One flow, two viewports, one worker so the 8 GB GPU runs a single model at a time.
export default defineConfig({
  // Tests sit beside the app, not in a second project.
  testDir: "./e2e",
  // The photo and the diffusion image share one GPU, so tests do not overlap.
  fullyParallel: false,
  // One browser at a time.
  workers: 1,
  // Stop after the first failure so a second viewport does not start a doomed GPU run.
  maxFailures: 1,
  // No retries. A failed photo or render should stay visible.
  retries: 0,
  // Photo, parse, diffusion, and the explanation can each take several minutes.
  timeout: 25 * 60 * 1000,
  // Ordinary assertions. The long steps pass their own timeouts.
  expect: { timeout: 15_000 },
  // List for the terminal, HTML for a failed step. The HTML folder is gitignored.
  reporter: [["list"], ["html", { open: "never" }]],
  // Shared browser settings.
  use: {
    // Same origin the page already uses. The test does not open port 8001.
    baseURL: "http://localhost:3000",
    // Keep a trace when a step fails.
    trace: "retain-on-failure",
    // Keep a screenshot when a step fails.
    screenshot: "only-on-failure",
  },
  // Reuse the dev server when it is already on port 3000. This does not start the API.
  webServer: {
    // Next.js dev server. API_URL in frontend/.env.local points the handlers at port 8001.
    command: "npm run dev",
    // Ready when the page answers.
    url: "http://localhost:3000",
    // Leave an already running `npm run dev` in place.
    reuseExistingServer: true,
    // Cold start budget. An existing server returns immediately.
    timeout: 120_000,
  },
  // Desktop first, then a narrow phone width. Both drive the same flow.
  projects: [
    {
      // Wide layout.
      name: "desktop",
      // Viewport only. The channel is Playwright's Chromium.
      use: { viewport: { width: 1280, height: 900 } },
    },
    {
      // Narrow layout. Tables scroll inside their own boxes.
      name: "narrow",
      // Width used by the earlier phase walkthroughs.
      use: { viewport: { width: 390, height: 844 } },
    },
  ],
});
