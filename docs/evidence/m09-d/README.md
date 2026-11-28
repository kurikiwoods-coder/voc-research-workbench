# M09-D 主题发现工作台、候选审核与独立盲测

负责人签收 M09-C 的提交为 `8a2ee1e3465964112e8f6a132932f35658557839`，M09-D 从该提交接续。交付分支为 `codex/g1-personal-phase-1`，PR #2 保持草稿。核心已验收 42/79，M09 保持 PARTIAL，正式 G3 与 P0-1 待验收。[M09-C 签收](../m09-c/README.md) · [草稿 PR #2](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/2)

## 交付范围

| 授权工作 | 实现 |
| --- | --- |
| 聚类可视化 | 按冻结范围显示主题成员数、离群和关键词关系，标明样本覆盖、语言和质量诊断。主题关系采用关键词集合 Jaccard 重叠，反映共词而非向量距离。 |
| 候选输出 | 从封存运行得到带稳定 ID 的候选和关键词描述，附成员及代表证据引用。候选支持保留供人审、驳回及历史修订回读。 |
| 已知与未知盲测 | 预先锁定 32 条混合样本、18 条负例样本、黄金标签、参数和评分规则。两个批次实跑固定模型并复算。 |
| 原话与证据 | 从主题、离群和成员下钻至精确片段、证据、来源版本及原话。当证据不再合格，隐藏其派生展示并拒绝下钻、比较与重算。 |
| 快照与重算 | 指定审核修订可重读已存结果。重算重新验证同一批合格证据，封存独立子运行，可比较主题匹配、成员、关键词、后处理、离群与候选覆盖。 |
| 质量与复现 | 保存模型清单、嵌入与聚类设置、随机种子、输入摘要、样本和评分结果。保留已知失败及复验记录。 |

聚类沿用已有 BERTopic 0.17.4、UMAP 0.6.0、HDBSCAN 0.8.44 与固定 MiniLM CPU 环境。以 HTML、CSS 和原生 JavaScript 实现可操作条形分布与共词关系，沿用现有工作台导航和静态资源。未新增第三方依赖。主题关系直接读取封存关键词，使含义与撤销后的遮蔽规则一致。[BERTopic 可视化参考](https://maartengr.github.io/BERTopic/getting_started/visualization/visualization.html) · [既有运行时许可与资产](../m09-a/README.md)

## 本机入口、边界及备份

- 以现有本机启动路径打开 `/#discovery`。Personal 使用可信 Owner 的精确项目与冻结范围授权。Business 的可信服务端装配通过 `create_app(..., relation_grants=...)` 提供整项目读取及证据权限，候选审核还要求验证权限。默认 Business 启动保持仅定义权限。云端保持状态页。
- 在隔离工作目录提供受信 `m09-discovery-synthetic.json`。顶层数组每项包含 `study_id`、`scope_id`、`scope_version`、`registry_version`、`references`。其中 `mention` 引用包含 `record_id`、`raw_sha256`、`segment_revision`、`mention_id`、`evidence_id`、`original_language`。已有 M08 合成回执可用 `sampling` 引用，包含 `task_id`、`receipt_index`、`original_language`。引用对应既有的合格合成记录，清单仅存标识和摘要。
- `VOC_M09_MODEL_DIR` 指向已核实的 MiniLM 本机绝对目录。运行须能读取既有模型清单和锁定 CPU 依赖。缺少本地模型时可阅读已保存的合格快照，有效计算入口要求模型可用。受信清单、启动配置和工作库留在隔离工作区。
- 主题库从 v1 增量升至 v2。候选输出标识为 `m09-d-candidates-v1`。审核记录按修订追加，绑定操作者和幂等键，重算以新运行 ID 封存。Personal 工作库 v11、Business 工作库 v9。停写后通过 SQLite Backup API 对主题库和配对工作库分别一致性备份，恢复后运行 `integrity_check`、`foreign_key_check` 及证据重验。
- 使用同源回环 HTTP 与工作台动作头，敏感响应 `no-store`。合成主题和审核保留在发现层。正式研究分母增量、正式注册表写入、正式发布与真实研究 API 调用均为 0。

## 盲测与复验

32 条混合批的定时启动为纯度 5/10、召回 5/8，自动关闭无独立匹配簇。未知掉电恢复原始结果为纯度 6/15、召回 6/8，0.60 过滤后为 6/11、6/8，分配覆盖从 25/32 降至 21/32。18 条负例中，5 条模糊或孤立样本仍组成误发现簇。合成审阅驳回该候选，审核前后修订可分别回读。盲测复验 2 项通过、0 失败、0 跳过，48.400 秒，审计非回环网络尝试 0。M09-B 的 8/11、8/12、8/13 保留。0.60 过滤为探索记录，G3 继续待原定合格真实小样本和人工验收。[预设方案](blind-plan.md) · [报告与命令](blind-report.md) · [原始结果](blind-results-v1.json)

## 本机工程验证

| 范围 | 实际结果 |
| --- | --- |
| 候选、历史快照及数据库兼容 | 21 通过、0 失败、0 跳过，16.561 秒，非回环网络尝试 0 |
| 候选与本机 HTTP 权限 | 14 通过、0 失败、0 跳过，12.331 秒，非回环网络尝试 0 |
| 固定模型与盲测 | 原生 Windows 11 26H2 x64（26300.9974），CPython 3.12.9，2 通过，0 失败，0 跳过 |
| 浏览器 | Windows 11 本机 Chrome 158.0.8127.38 回环测试。确定性界面夹具与固定 MiniLM、BERTopic 实际推理分别执行，覆盖主题键盘操作、原话下钻、撤销、审核修订重读、重算与比较及移动端。另以 Personal 合成 Owner 验证项目及冻结范围选择。页面外部请求与 Python 非回环尝试均为 0。 |
| Node、空库冷启动、历史归档 | 2/2、3/3、4/4 |
| GitHub CI | Ubuntu、Windows Server 2022 与 Chromium 结果见交付提交对应的 PR 检查。Chromium 常规运行包含 M09-D 的确定性界面夹具。 |

浏览器使用合成材料。固定模型复验使用已有本机脱机锁定环境和已验签模型。将 `$appPython`、`$m09Python`、`$m09ModelDir`、`$appSitePackages` 和 `$browserOutput` 指向相应的隔离位置。原生浏览器可按已安装的 Chromium 路径设置 `VOC_CHROMIUM`。

```powershell
& $appPython tests/browser_e2e.py --discovery-only --output $browserOutput
$env:VOC_M09_MODEL_DIR = $m09ModelDir
$env:VOC_M09_MODEL_MANIFEST = (Resolve-Path docs/evidence/m09-a/model-assets.json).Path
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:PYTHONPATH = $appSitePackages
& $m09Python tests/browser_e2e.py --discovery-native --output $browserOutput
```

隔离沙箱默认用户目录导致回归夹具无法创建目录或校验模型路径。使用进程级测试目录变量重跑，保留初始结果与错误堆栈。旧有 `StarletteDeprecationWarning` 继续记录。

## 工程可行性检查

| 检查项 | 状态 | 依据 |
| --- | --- | --- |
| 本轮需求和下游契约 | PASS | 六项隔离工程能力已实现。原证据、注册表和候选分层，候选可交接人工复核。 |
| 数据模型与上下游兼容 | PASS | 主题库 v1→v2 保留历史快照。M05/M06 当前资格与版本和 M07 封版读取继续适用。 |
| 已核验模型与研究质量 | AT RISK | 固定模型实跑与复现证据可复验，独立盲测仍有混簇、漏分和误发现。 |
| 生产研究与最终验收 | BLOCKED | G3 与 P0-1 待验收，正式研究依适用准入门禁。 |

后续 M10 实施待负责人独立授权。双轨对照和正式 G3 质量验收沿用原路线图与口径。[ROADMAP-V2](../../planning/ROADMAP-V2.md)
