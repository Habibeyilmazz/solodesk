import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "playwright/test";

// The smoke test runs against the real thing: the built UI served by FastAPI, on a throwaway
// database. Build first (`make e2e` does).
const port = 4152;

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure" },
  webServer: {
    command: `../.venv/bin/python -m uvicorn solodesk.main:create_app --factory --port ${port}`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    env: {
      SOLODESK_PASSWORD: "e2e-password",
      SOLODESK_DATA_DIR: mkdtempSync(join(tmpdir(), "solodesk-e2e-")),
    },
  },
});
