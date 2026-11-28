# G-1-P-C 个人供应商审批中心

接自 B-V 实机证据提交 `97e942d9339921089cabb6fe2b0ea01d6832f5fe`。C 首版源码为 `0b25c0a375ffa6660884287bc4e2b0c25c535a65`，验收源码为 `912ff28e0a10e3329bc49c6e9fdc97e290229a68`。[B-V 三项 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45757091621) · [草稿 PR #2](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/2)

可信 Personal Local Owner 在「版本与研究准入」选中获准项目，查看当前绑定、材料缺口、风险、预算及历史，在对应冻结范围内提交、批准或撤销。服务端校验身份、权限、范围、用途中每项必要材料、时效、Token 限额和当前凭证。允许接受有明确理由、影响、缓解措施、责任人及时效的非强制未知。审批记录不可变，撤销在凭证损坏时仍可追加。浏览器只接收脱敏结果。[接口与权限](../../architecture/g1-personal-approval-contract.md)

## 实机缺陷与复验

在较深的受保护 Windows 运行目录中，项目、冻结范围和版本组成的密文路径超过 260 字符。首版原生 HTTP 保存返回 503，`os.replace` 报 WinError 3。修复对读取、临时文件、原子替换和密文清理统一使用 Win32 扩展路径，沿用原文件名和版本锚。新增一个原生 DPAPI 长路径用例。普通用户合成探针通过保存、重启读取、轮换、删除及旧密文重放验证，审批 API 未触发外连。

SQLite 工作库为 v9。原有 v8 库及活跃 WAL 一致性备份通过增量迁移、数据与稳定 ID 比对、失败回滚、重开幂等及备份恢复。验证记录、独立复审和缺陷状态见[实机结果](windows11-results.md)、[迁移证据](database-migration.md)、[复审](independent-review.md)及[缺陷登记](bug-register.md)。

## 发布与准入状态

固定源码的 **WINDOWS_11_REAL_MACHINE = PASS**，**WINDOWS_11_DEPLOYMENT_GATE = PASS**。C 发布验收绑定本交付提交，草稿 PR #2 的 Ubuntu、Windows Server 2022 和 Chromium 三项检查均通过时 **G-1-P-C = ENGINEERING_PASS**、**G-1-P-D = READY**。READY 只表示工程接续条件。[交付检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/2/checks)

G1_PERSONAL_APPROVAL_CENTER 已实现，G1_PERSONAL_IMPLEMENTATION 为 PARTIAL。G-1-PERSONAL 为 NOT_EVALUATED，商用 G-1 为 BLOCKED。个人预准入、正式研究和原 PackyCode 真实阻断继续生效。M06 冻结，正式统计为 `unavailable` 和 `null`，ROADMAP-V2 为 39/79。G-1-P-R 和 M09 为 NOT_STARTED。真实研究 API、真实供应商探针分别为 0。

D 实际运行需真实当前账户、通道与模型、逐源授权、预算和负责人单独批准。[同批准备方案](d-preparation.md)
