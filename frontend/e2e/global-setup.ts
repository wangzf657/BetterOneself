import { resolve } from 'node:path'

// 保留目录约定但不再外部清库:清库改由后端 BO_RESET_DB=1 在启动时自清,
// 因为 playwright 的 webServer 先于 globalSetup 启动,外部删除会踩时序。
export default function globalSetup() {
  void resolve
}
