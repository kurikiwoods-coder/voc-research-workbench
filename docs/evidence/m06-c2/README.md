# M06-C2 实时语料资格验收

开发基线为 `776acfed513d1b56af0adfbaf74864912817f25f`，SQLite v7。2026-11-25 在隔离的 Linux x86_64 工作区执行测试，使用合成项目、临时主库和仓库的四份脱敏历史归档。真实研究 API 调用 0 次。PDT v1.3.1、五项负责人政策、SQLite schema 和公开 GET 路由保持既有版本。专案 v2.2 的 27 页 PDF 原件在本次仓库资料中仍缺，沿用已登记的摘要和差异。

实现提交为 `965a4b8b3596c03437f9629f2f203e11af617726`。实现 CI 的 Ubuntu、Windows Server 2022 和 Chromium 三项均为 success，M06-C2 = **ENGINEERING_PASS**。本轮已识别的四项阻塞缺陷全部关闭，开放 P0/P1 为 0。

## 两个入口与写入截点

Python `CorpusStore.qualified_record(study_id, record_id)` 和 GET `/api/corpus/{study_id}/records/{record_id}/eligible` 沿用短读快照。它们与写入路径共同调用 `qualified_record_in_transaction(db, study_id, record_id, *, today)`。合法返回保留原话、摘要、来源、当前审核状态、角色、隐私、期限、撤销标记及工程资格。项目、冻结范围及其版本仍在 `trace` 中。正式研究和外发均为 false。跨项目和不存在记录返回相同 404；同项目失格记录返回 409。

后续写调用方先验证操作者与项目权限，在主库连接执行 `BEGIN IMMEDIATE`。进入 `with corpus.qualified_write_inputs(db, study_id, record_ids) as records`，传入全部直接证据和上下文的稳定 ID。查验主库身份、写锁和当前 UTC 当日资格后，才能在该块内进行依赖写入。退出时逐条复读资格并核对 UTC 日期。异常回滚本块保存点，调用方负责整个命令的回滚，以及成功退出后的立即提交。最终 COMMIT 失败由调用方回滚。跨日须重算整个命令。旧 WAL 读快照升级失败须退出原事务，在新事务重试。资格结果仅供当前操作使用，任何后续显示、回放或导出均须重新取证。跨项目授权仍由未来受信入口核对。

## 修复前后

| 合成验证 | 修复前 | 修复后 |
|---|---|---|
| 未经逐行审核的批次被撤销，另一导入中的相同文件行已有审核 | 副本 eligible 200 | 409，原话详情及导入行遮蔽。批次撤销独立于逐行审核是否存在 |
| 一份映射遗漏了来源 URL，在其中登记撤销；另一映射的相同文件行已核验 | 副本 eligible 200 | 409，按项目、文件摘要、工作表和行号匹配。显式新授权仅恢复指定行 |
| 已撤销记录的原保留期限已过，再提交新材料 | 人工复核 200 | 409，到期后不可复用保留中的原文 |
| 同一文件行的一份撤销登记未另填截止日，另一份有效期更长 | 到期后副本复核 200 | 409，副本检查沿用审核历史的有效期限 |

导入预览与确认是本次超出核心文件清单的相邻入口。为保持既有 M04 重试契约，对已撤销、无逐行审核事件、原配置完全相同的暂存批次，预览仅从已存汇总重取原令牌与撤销状态，样本及问题行为空。确认仅返回既有批次；改映射、改隐私或重开受限文件按现行规则拒绝。专测以禁止文件重读的断言验证该路径。

## WAL 时序与结果

| 场景 | 已执行时序 | 实际断言 |
|---|---|---|
| A 撤销先提交 | A 在同一连接取得旧资格并结束读事务；B 在真实 M05 审核 COMMIT 前发信号；A 尝试取锁得到 SQLITE_BUSY；放行 B 提交后 A 重取写锁 | 资格拒绝，测试引用数 0。另一试验保留旧 WAL 读快照，升级返回 SQLITE_BUSY_SNAPSHOT |
| B 写先提交 | A 持写锁并得到资格；B 独立连接以零等待抢锁得到 SQLITE_BUSY；A 写入仅含 record_id 的测试引用。第三个读连接在提交前看到 0 条；B 随后完成撤销 | 引用保留 1 条，当前 GET 409，详情无原话 |
| C 副本及历史 | 同项目来源 URL、跨批次、同文件同行及来源列缺失；重新打开、预览、导入历史、错误 CSV、暂存视图和确认重试 | 受限记录不能作为处理输入。可回读受控 ID，精确重试返回既有批次 |
| D、E 独立来源与单条新授权 | 同文不同来源保留独立资格；提交一条合法和一条已撤销的输入；试用旧许可，再显式登记指定记录的新材料 | 混合依赖整组拒绝；仍获准来源可单独使用。新授权后其余受限副本继续 409，审核历史保留 |
| F UTC | 到期日 23:59:59.999 有效，次日 00:00:00 起失效；测试写进行中跨日；已提交后才跨日；另测跨日时许可仍有效 | 进行中的写回滚，即使仍有效也须重算；到期后新读 409，已提交的引用保留 |
| G 项目隔离与异常 | 跨项目与不存在 ID，借用其他库、无活动事务、无依赖，调用方已有写入、故障注入及同事务内资格变化 | 接口相同 404；无效写路径停止。本块失败后调用方仍持有自己的事务，可回滚。无明文或资格缓存写入 |

## 实测与复验

云端 Python 3.12.14、SQLite 3.53.1、Node 24.22.3。C1 基线 Python 173/173；实现版 190/190，包含新增 C2 17 项、既有 M05-R2、Pre-M06 A–H 和 C1 33 项约束及迁移测试。新增 17 项另行连续运行三轮，每轮校验临时主库 integrity_check=ok，foreign_key_check 无记录。Node 2/2、Chromium 8/8、冷启动 3/3、归档 4/4、暂存文件敏感信息扫描通过。

本机的系统 Chromium 启动器缺少目标二进制，Playwright 下载端点返回拒绝。通过 npm 安装隔离的 Chromium 141.0.7390.0 headless，以仓库支持的 VOC_CHROMIUM 参数完成基线与实现版的原版浏览器测试。GitHub 的 Chromium 作业按 CI 依赖安装浏览器。C2 版 Windows 11 实机 NOT_TESTED，平台部署门禁 BLOCKED，交桌面端复验。C1 的 Windows 11 实机及其部署门禁历史 PASS。

~~~sh
bash scripts/smoke-test.sh
python -m unittest discover -s tests -p test_m06_eligibility.py -v
python tests/browser_e2e.py
for archive in docs/evidence/p0-0 docs/evidence/p0-0/regression docs/evidence/p0-0/api-setup/live-receipt docs/evidence/p0-0/tavily-live; do
  python -m src.outputs.audit_receipt --verify "$archive" || exit 1
done
~~~

[Linux 实际输出摘录](linux-results.txt) · [新增测试](../../../tests/test_m06_eligibility.py) · [实现 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45532356340) · [PR 当前检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

## 架构反例的验收边界

| 反例 | 本轮实际覆盖 | 留待所属阶段 |
|---|---|---|
| A07、A08、B08 | 独立来源可用、已撤销来源和上下文不可用，混合输入整组拒绝，单条重新授权 | C3 的实际 M/E 支持关系，C5/M12 的重新归桶、重编和发布 |
| A09 | 项目限定记录读取与写入，隐藏和不存在对象相同 404 | C4 的关系投影及跨项目专项授权，C5 分母 |
| A21 | 撤销先后两种 WAL 顺序、跨 UTC 日回滚、取历史时重新遮蔽 | 发布后的正式统计重算与已分发报告处置 |
| B04 | 按原文和摘要取得合法记录，所有列入请求的上下文分别复核 | C3 决定片段区间、身份、跨句依赖完整性及回放 |
| B09 | 既有 M04/M05 查询、暂存、导出及重试遵守当前限制 | 正式历史报告、多角色审计和按历史注册表版本重算 |
| B13、B14 | 同库写入串行、调用方回滚和 M04 已存在的批次回执重试 | C4 版次竞争、正式幂等发行；C5/M12 回执替换、统计与发布 |

G-1 BLOCKED。正式供应商验收、真实数据逐源许可及统计发布保留各自的原准入条件。C3 NOT_STARTED。
