import { defineConfig } from '@playwright/test'

// E2E 跑 stub LLM 后端 + vite 前端;数据落 backend/data/e2e(独立于开发库)
// 端口可用 E2E_API_PORT / E2E_WEB_PORT 错开:开发服务常驻时(8000/5173 被占)不冲突
const API_PORT = process.env.E2E_API_PORT ?? '8000'
const WEB_PORT = process.env.E2E_WEB_PORT ?? '5173'

export default defineConfig({
  globalSetup: './e2e/global-setup.ts',
  testDir: './e2e',
  timeout: 120_000,
  workers: 1, // 共享同一个 stub 后端库,必须串行
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: `uv run --directory ../backend uvicorn app.main:app --port ${API_PORT} --log-level warning`,
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      timeout: 180_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        BO_STUB_LLM: '1',
        BO_DATA_DIR: 'data/e2e',
        BO_RESET_DB: '1', // 后端启动自清:E2E 干净起跑(webServer 先于 globalSetup,外部删目录会踩时序)
      } as Record<string, string>,
      stdout: 'ignore',
    },
    {
      command: `pnpm dev --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      timeout: 180_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        E2E_API_PORT: API_PORT, // vite 代理指向本次 E2E 后端
      } as Record<string, string>,
    },
  ],
})
