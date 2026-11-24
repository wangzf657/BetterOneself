import { defineConfig } from "@playwright/test";

// uv 可执行路径：默认取 PATH，本机可用 UV_PATH 覆盖
const uv = process.env.UV_PATH ?? "uv";
const backend = (port: number) => `${uv} run uvicorn app.main:app --host 127.0.0.1 --port ${port}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8765",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      // 主实例：桩 LLM（规划成功、出题可重复换组）
      command: backend(8765),
      cwd: "../backend",
      url: "http://127.0.0.1:8765/api/studies",
      reuseExistingServer: true,
      timeout: 120_000,
      env: { BO_LLM_STUB: "1", BO_DATA_DIR: "data_e2e1" },
    },
    {
      // 辅实例：桩 LLM 但 AI 规划必失败（B2-03「仅规划失败保树」E2E）
      command: backend(8766),
      cwd: "../backend",
      url: "http://127.0.0.1:8766/api/studies",
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        BO_LLM_STUB: "1",
        BO_STUB_OUTLINE_FAIL: "1",
        BO_DATA_DIR: "data_e2e2",
      },
    },
    {
      // 第三实例：桩 LLM 但两路预检都不通（B6-02「分路提示、不自动重试」E2E）
      command: backend(8767),
      cwd: "../backend",
      url: "http://127.0.0.1:8767/api/studies",
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        BO_LLM_STUB: "1",
        BO_STUB_PRECHECK_FAIL: "embedding,llm",
        BO_DATA_DIR: "data_e2e3",
      },
    },
  ],
});
