import { defineConfig } from "@playwright/test";

// 回归独立配置：复用已在跑的 QA 回归前端 5176（代理到 8000 桩实例），不自带 webServer。
export default defineConfig({
  testDir: __dirname,
  timeout: 120_000,
  retries: 0,
  workers: 1,
  outputDir: __dirname + "/../V0.1/logs/reg/ui-results",
  use: {
    baseURL: "http://localhost:5176",
    viewport: { width: 1280, height: 800 },
    trace: "retain-on-failure",
  },
});
