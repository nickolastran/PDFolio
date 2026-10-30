import { defineConfig } from "@playwright/test";

// Runs against the production-style server (built frontend served by FastAPI).
export default defineConfig({
  testDir: "e2e",
  use: { baseURL: "http://localhost:8000" },
  webServer: {
    command: "npm run build && cd ../backend && .venv/bin/uvicorn app.main:app --port 8000 --no-access-log",
    url: "http://localhost:8000/api/tools",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
