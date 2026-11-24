# VOC Research Workbench 开发状态

核查日期 2026-11-24。本轮开发基线 `d22d56cdce129b1530647cf57dccd4b8f56cafed`，目标分支 `codex/p0-0-connectivity`。[PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1) · [15 个模块](MODULE_ROADMAP.md)

## 本轮 M04 CSV / Excel 数据导入

完成本机文件上传、工作表选择、字段映射、质量检查、确认入库、批次查询及撤销。导入写入 SQLite v3 暂存，绑定原项目和冻结范围。真实 Tavily、Brave、Jev 请求 0 次，G-1 保持 BLOCKED。[本机用法、模板与 M05 契约](docs/imports.md) · [工程测试记录](docs/evidence/m04/README.md)

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

当前仍处于 P0-0。M05 开发须经单独授权，使用 M04 的 import_candidates 及原始文件、项目和范围引用，实现正式原文治理、溯源和去重接口。真实业务流程仍按 PDT 和 G-1 放行。
