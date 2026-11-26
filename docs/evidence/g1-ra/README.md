# G-1-R-A 工程验收

入口为 `codex/p0-0-connectivity` 的 `a7b1de491c85fb879bed4b2ce25f9f3164add6a0`。本机、远端开发分支及草稿 PR #1 核对一致。入口的 Ubuntu、Windows Server 2022 和 Chromium 作业均成功。[入口 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45619489081) · [交付 PR 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

## Windows 10 实机

2026-11-25 在 Windows 10 Home China 22H2 x64 19045.6466 执行。Python 3.12.14，SQLite 3.53.1，Node 24.22.3，Playwright 1.65.2，Chrome 157.0.8103.80。

| 验证 | 实际结果 |
| --- | --- |
| Python 全量 | 313/313，72.941 秒。既有 298 项，新增 PackyCode 15 项。 |
| Node | 2/2。 |
| Chromium E2E | 13/13 组，原 12 组加 PackyCode 配置、钱包呈现和凭证生命周期 1 组。回环 HTTP 2/2。 |
| 冷启动、旧回执 | 空库冷启动 3/3，四份历史脱敏归档 4/4。 |
| SQLite | 工作库 v8，诊断专库 v1。两类隔离库均为 `integrity_check=ok`，外键已开启，检查违规 0。 |
| DPAPI | 普通用户会话通过合成凭证保存、读取、轮换、重启和删除。Codex 受限会话在内存探针返回 Windows 错误码 2。本机凭证保护机制按原实现执行。 |

[合成配置截图](packycode-candidate.png)的 SHA-256 为 `cac53f759b2b5d60fc678f8a2a24eff254c0b7c1c990e81d53bed85ac64a4af8`。保留既有 Starlette TestClient 弃用提示作为非阻塞债务。Windows 11 本轮同源码实机 **NOT_TESTED**。

## 结果和范围

工程覆盖固定端点与账户隔离、审查绑定、8+3 分片、固定模型校验、三类答案、Schema 缺口、幂等与恢复、未知计费及内部数据外发限制。[专项用例](../../../tests/test_packycode.py) · [独立复审](independent-review.md) · [通道与后续预检](../../packycode.md)

`G1_RA = ENGINEERING_PASS` 以交付 SHA 的三项 CI 通过为验收条件。已实现 PackyCode 候选连接器。供应商公开端点及计费元数据已核对。实际账户审核为 **PENDING**，PackyCode 真实契约为 **NOT_TESTED**。Windows 本机仅核对凭证和审核状态，两者均未配置或通过。

负责人批准一次受控合成预检，累计上限 100,000 输入 token。因账户审核未通过且本机未配置独立凭证，预检保持 **BLOCKED**，实际请求和输入用量均为 **0**。G-1-R-B = **NOT_STARTED**，G-1 = **BLOCKED**，真实研究 API 调用 = **0**。ROADMAP-V2 工程或复审进度 **35/79**。
