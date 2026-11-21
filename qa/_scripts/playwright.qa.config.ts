import { defineConfig } from "@playwright/test";

// QA 独立配置：复用已在跑的 QA 前端 5174（代理到 8000 桩实例），不自带 webServer。
export default defineConfig({
  testDir: __dirname,
  timeout: 120_000,
  retries: 0,
  workers: 1,
  outputDir: __dirname + "/../../V0.1/logs/qa-ui-results",
  use: {
    baseURL: "http://localhost:5174",
    viewport: { width: 1280, height: 800 },
    trace: "retain-on-failure",
  },
});
