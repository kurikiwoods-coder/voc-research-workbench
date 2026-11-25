# M08-A/B 隔离工程验收

基线 `81ce8818354f36ed33943d604e8890adde1f4c3f`，开发分支 `codex/p0-0-connectivity`，草稿 PR #1。基线 Ubuntu、Windows Server 2022 和 Chromium 均通过。[基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45638047977)

| 检查 | 结果 |
|---|---|
| Windows 10 Home China 22H2，19045.6466 | 在普通 Windows 用户上下文以 Python 3.12.14 运行最终全量 359/359，75.764 秒。原 328 项，新增 M08 专项 31 项。 |
| Chromium | Chrome 157.0.8103.80 以回环夹具通过全套 E2E，含 M03–M05 与 PackyCode 同库重启、M07 和 M08 界面。M08 复验 320 和 390 px、键盘展开、预览映射、3 条发现及 2 个独立 URL、1 个可访问页面。 |
| Node、冷启动及归档 | Node 24.22.3，2/2；三次独立空库启动通过，工作库 v8；脱敏历史归档 4/4。 |
| SQLite | 使用带中文及空格的隔离目录完成两次独立进程启动，重启后冻结范围、工作库 v8 和演示回执 ID 及内容对账一致。演示账本 v1 `integrity_check=ok`、`foreign_key_check` 无结果。 |
| 安全及兼容 | 独立复审 7 项关闭，其中 1 项 P1；M06 分母、M07 和 PackyCode 定向回归 57/57。 |
| Windows 11 实机 | 本次源码 NOT_TESTED。Windows Server 2022 的 CI 记录单独核对。 |
| 真实调用 | 0 次。演示使用内存夹具，采集入口 403，正式各阶段漏斗均为 `null`。 |

复现命令为 `python -m unittest discover -s tests -p 'test_*.py'`、`node --test tests/client_state.test.cjs`、`python scripts/cold_start.py`、`python tests/browser_e2e.py` 和 `bash scripts/check-no-secrets.sh`。Windows 本次通过 `VOC_CHROMIUM` 指定本机 Chrome。仅运行 M08 界面可用 `python tests/browser_e2e.py --acquisition-only`。凭证用例在受限执行上下文出现既有 DPAPI 限制，普通用户上下文全量通过。Starlette 的既有弃用提示继续按非阻塞技术债处理。

[来源契约](../../architecture/m08-source-adapter-contract.md) · [搜索及回源契约](../../architecture/m08-search-and-retrieval-contract.md) · [独立复审](independent-verification.md) · [缺陷台账](bug-register.md)

正式业务验收为 PENDING。需要补逐供应商账户与逐来源审批、实际正式采样与授权链、原标准要求的抽查和对账，以及 G-1 同批六项验收。历史 PackyCode 合成契约 PASS，第二片实扣和实际总扣仍未核实。
