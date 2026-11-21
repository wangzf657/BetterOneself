# BUG-001 设置分节"部分保存"会清空未提交字段（含密钥）

| 字段 | 内容 |
|---|---|
| 缺陷 ID | BUG-001 |
| 标题 | 设置页分节保存时，仅提交的字段被保存，同节其余已保存字段（含 API Key）被静默清空 |
| 模块 | P05 设置（后端 PUT /api/settings） |
| 严重级别 | **P1 严重**（用户配置数据丢失：密钥被清后需重新输入；影响真实 BYO-Key 用户） |
| 复现概率 | 必现（100%，API 与 UI 双重复现） |

## 前置条件
讲解与测验服务已保存 base_url、model、api_key 三项。

## 复现步骤（UI）
1. 打开 `/settings`，确认讲解与测验服务节已有"服务地址=https://api.example.com/v2、模型、密钥掩码"。
2. 仅在 API Key 输入框填入新密钥，点"保存本节"。
3. 观察保存后的表单与 GET /api/settings 返回。

## 预期结果
按 P05 规格"密钥项留缺省保持不变、置空即清除、填新值即替换；配置失败不清空用户刚填写的其他项"：只保存密钥，服务地址与模型保持不变。

## 实际结果
服务地址与模型被清空（表单回到占位符；GET /api/settings 返回 `{"base_url":null,"model":null,"api_key":"sk-****xxxx"}`）。反向同样成立：只改服务地址 → 模型与密钥被清空。

## API 级最小复现（证据）
```text
1) PUT /api/settings {"llm":{"base_url":"https://api.example.com/v1","model":"gpt-test","api_key":"sk-QAtest1234567890"}} → 200
   GET → {"base_url":"...v1","model":"gpt-test","api_key":"sk-****7890"}
2) PUT /api/settings {"llm":{"base_url":"https://api.example.com/v2"}} → 200
   GET → {"base_url":"...v2","model":null,"api_key":null}   ← model/key 被清
```
证据文件：qa/V0.1/logs/api/、qa/V0.1/screenshots/bug-001-settings-partial-save-wipes-others.png

## 观察到的实现事实（供开发定位，非根因断言）
- 服务端 `put_settings` 文档字符串声明"字段缺省保持不变"，且实现按 `short not in body` 判断缺省；
- 但 API 层用 `body.model_dump(exclude_none=False)` 序列化，pydantic 会把请求中未出现的字段补成显式 `null`，"缺省"在 HTTP 层不可表达；
- 前端 `ServiceForm.buildBody()` 只提交变更字段（diff），依赖的恰是"缺省保持不变"语义。
- 挡板路径：用户把三项一起填交即可恢复（故定 P1 而非 P0）。

## 影响分析
- 真实使用场景：换模型名 / 换地址 / 清密钥任意单项操作都会静默丢其余配置，密钥丢失直接导致 AI 功能不可用且原因不易察觉（讲解报"未配置"）。
- 与验收冲突：B5-02"密钥输入后可更新、可清除"隐含不破坏其他配置；页面清单 P05"配置失败不清空用户刚填写的其他项"精神相同。

## 修复记录（2026-11-21）

- 根因：API 层 `body.model_dump(exclude_none=False)` 把请求中未出现的字段补成显式 `null`，"缺省"在 HTTP 层不可表达；服务层三语义实现本身正确。
- 修复：`backend/app/api/settings.py` 改为 `model_dump(exclude_none=False, exclude_unset=True)`——未提交字段保持 absent（不变），显式 null 仍保留（清除）。
- 回归：`tests/test_api.py::test_settings_partial_update_keeps_other_fields`（改地址/换密钥/置 null/交掩码四段）通过；pytest 59 passed，E2E 7 passed。

## 回归验证（2026-11-21 修复后）

**结论：修复确认，关闭。** 详见 [06-regression-report.md](../06-regression-report.md)（API/单测/链路证据在 `logs/reg/`，UI 证据在 `screenshots/reg/`）。
