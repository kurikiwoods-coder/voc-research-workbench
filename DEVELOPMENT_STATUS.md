# VOC Research Workbench 开发状态

核查日期 2026-11-24。接管分支 `codex/p0-0-connectivity`，远端基线 `bca93639043e176f4159b9bf9fb98b4b2e2b32d8`。[PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1) · [接管基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45341736949) · [15 个模块](MODULE_ROADMAP.md)

## 本轮 M05-R2 许可与数据资格复修

基于远端 `958ebcb948fa9677a7254dde4516c4a49761b798` 重开 M05 工程验收。BUG-01 与 BUG-02 均已完成基线复现及修复后本机实测。SQLite v5 保留现有历史、增加不可变许可事件，撤销后须由人工核对独立的新授权材料。当前资格服务统一控制原话、重复组与后续读取。

Linux 本机通过 123 项 Python、2 项 Node、3 次空库冷启动及 4 份历史归档核验。远端 Ubuntu、Windows Server 2022 和 Chromium 工程验收待在本轮提交上确认。正式阶段为 P0-0，G-1 **BLOCKED**。本轮真实研究 API 调用 0 次。[M05-R2 复测证据](docs/evidence/m05/permissions-review.md) · [下游数据契约](HANDOVER.md#m05--m06-数据契约)

## 上轮 M05-R 独立工程复审

M05-R 当轮记录为 **ENGINEERING_PASS**。复审基线为 `f279c7e0075b07e581d528709ffd5c9824e1a811`，最终实现为 `d0414f5e7b978460d7dec3784c0862d7f1f0bdd0`。原留存期限、许可撤销、跨文件来源限制、批次重试和遮蔽均有回归。Windows 11 实机通过 Python 114/114（基线 104，新增 10）、Node 2/2、冷启动 3/3、Chromium 8/8 和归档 4/4。对应 Ubuntu、Windows Server 2022、Chromium 作业全部通过。真实研究 API 调用 0 次。正式阶段仍为 P0-0，G-1 **BLOCKED**。[M05-R CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45359711019) · [合成回归证据](docs/evidence/m05/review.md) · [M06 数据契约](HANDOVER.md#m05--m06-数据契约)

## 上轮 M05 原始语料库、去重及溯源

本机工作台已接入原始语料审核。记录绑定冻结范围与导入文件行，保存原话快照摘要、角色、许可核验依据、保留期限和历史。跨批次按项目聚合重复原话，撤销、排除及到期会重算可用组成员。原话审核走回环 FastAPI 和 SQLite v4，正式统计和外发资格均关闭。[本机操作与接入](docs/imports.md#m05-原始语料审核) · [工程测试记录](docs/evidence/m05/README.md)

M05 实现提交为 `b02a2b647bff67f7e091b51fcdfc46cc719077e8`，直接基于 `bca93639043e176f4159b9bf9fb98b4b2e2b32d8`。Windows 11 本机通过 Python 104 项、Node 2 项、空库冷启动 3 次、Chromium 8 组及四份历史归档核验。验证使用合成输入、隔离数据库和既有脱敏归档，真实 Tavily、Brave、Jev 请求均为 0。

2026-11-24，GitHub 确认 `kurikiwoods-coder` 具备仓库写入权限。Windows 上的 Git HTTPS 推送在发包阶段遇到 `Bad file descriptor`。通过获准的临时仓库 SSH 密钥，将 `b02a2b6` 常规推送到 `codex/p0-0-connectivity`，并核对远端完整 SHA。临时密钥已撤销。该提交的 Ubuntu、Windows Server 2022 和 Chromium 作业全部通过，M05 完成本轮工程交付。M05 增量 Git bundle 已通过 `git bundle verify` 并保存在本机交付目录。[草稿 PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1) · [M05 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45352022477)

## 上轮 M04 CSV / Excel 数据导入

完成本机文件上传、工作表选择、字段映射、质量检查、确认入库、批次查询及撤销。导入写入 SQLite v3 暂存，绑定原项目和冻结范围。真实 Tavily、Brave、Jev 请求 0 次，G-1 保持 BLOCKED。[本机用法、模板与 M05 契约](docs/imports.md) · [工程测试记录](docs/evidence/m04/README.md)

M04 交付时，本地 Linux、Ubuntu 和 Windows Server 2022 各通过 95 项 Python（含新增 26 项）、2 项 Node 与 3 次空库冷启动，Chromium 六组通过。四份既有归档核验通过。[CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45341223418) · [截图和实际输出](docs/evidence/m04/README.md)

## 上轮 M03 研究项目与范围管理

交付本机项目列表、新建和编辑、搜索排序、当前项目切换、归档恢复、五种研究模式及范围快照冻结。SQLite v2 增量迁移保留 M01 和 M02 存储边界。[本机操作与接口](docs/studies.md) · [工程测试记录](docs/evidence/m03/README.md)

Linux 本机、Ubuntu CI 和 Windows Server 2022 各通过 69 项 Python（含 16 项 M03）、2 项 Node、3 次空库冷启动，失败均为 0。Windows Server 中文及空格路径的启动器通过。Chromium 四组浏览器测试通过，含 M03 的研究项目操作与服务重启。四份历史收据经 SQLite 与 JSON 核对。Windows 10/11 真机 NOT_TESTED。本轮 Tavily、Brave、Jev 调用量均为 0。[三平台 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45336483119) · [桌面截图](docs/evidence/m03/m03-project-list.png) · [移动端截图](docs/evidence/m03/m03-mobile-detail.png)

## 上轮 M01 基础工程与连通性

已交付同批来源恢复。在本机运行 `python -m src.outputs.recover_source_batch` 可从锁定的 Tavily 归档恢复原批次，原帖许可、时间和原句指纹重新核对后才写入。恢复保留原批次 ID 和搜索证据。继续验收从「运行记录 → 恢复此批次」执行。原帖发生变化、归档损坏或中途写库失败时停止恢复，重复执行无额外搜索请求。[操作说明](docs/connectivity.md#原运行库缺失时继续原批次)

| 验证范围 | 实际结果 |
|---|---|
| Ubuntu | 53 项 Python、2 项 Node、3 次空库冷启动，四份 SQLite 与 JSON 归档核验通过 |
| Windows Server 2022 | 53 项 Python、2 项 Node、3 次空库冷启动，归档及中文和空格路径启动通过 |
| Chromium | 浏览器 E2E 通过，涵盖桌面和 320 / 390 像素布局 |
| 归档恢复 | 新增 6 项回归通过，覆盖锁定摘要、同批幂等、原帖变化、篡改拒绝、事务回滚及夹具隔离 |
| Windows 10/11 真机 | NOT_TESTED |

已通过工程测试的实现提交为 [`47051f3`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/47051f3749589478aef41b0fa2b73a9ac542bf30)。恢复回归使用隔离夹具及已提交的归档核验。真实 Jev 和付费 Tavily 请求在本轮均为 0。[本轮 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45325025692) · [恢复回归](https://github.com/kurikiwoods-coder/voc-research-workbench/blob/47051f3749589478aef41b0fa2b73a9ac542bf30/tests/test_recover_source_batch.py)

## 正式验收

| 要求 | 状态 | 现有证据 |
|---|---|---|
| C0-1 | BLOCKED | 固定版本和 8 + 3 实发分片需要符合审核的 Jev 调用 |
| C0-2 | BLOCKED | 等待 Choice、Score、Noul 完整真实响应 |
| C0-3 | PASS | Tavily 认证搜索一次，HTTP 200、实报 1 credit，原帖 94603 许可回源成功 |
| C0-4 | BLOCKED | SQLite 归档通过核对，真实 Jev 用量及余额回填待验证 |
| C0-5 | PASS | 36 次限制案例在传输前拦截，六种故障演练 |
| C0-6 | PASS | 两个产品品类及 30 个意图的跨品类召回冒烟 |
| G-1 | BLOCKED | 等待供应商留存审查及 C0-1、C0-2、C0-4 |

[正式批次 `89b0c2d1-576d-420f-9046-9e55878159be`](docs/evidence/p0-0/tavily-live/README.md) · [需求矩阵](docs/requirements-matrix.md)

## 下一轮候选

当前正式阶段为 P0-0。正式语料验收需完成逐源清理审计、三批和至少 100 条真实语义片段，并抽查 30/30 可回源。后续模块等待开发指令。
