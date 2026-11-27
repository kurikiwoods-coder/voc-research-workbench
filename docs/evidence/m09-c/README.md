# M09-C 主题快照、证据追溯与离线复跑

实施基线 `cd4859dfa12cdc5676d13fd5033b2a04a8ada19d`，Personal 开发分支 `codex/g1-personal-phase-1`，草稿 PR #2。范围为 M09-C 隔离工程。**M09-C = PENDING_ACCEPTANCE**，**M09 = PARTIAL**，已验收核心 **41/79**。

## 本地发现服务

- `TopicRuns.create` 接收受信项目授权函数、固定范围版本、精确证据引用和获准离线模型。UUID 标识每次运行。快照记录起止时间、状态、模型 ID 和修订、模型资产和运行时版本、Embedding 运行 ID、输入及向量摘要、注册表版本、预处理、语言和请求及实际聚类参数。
- `get` 恢复已封存快照，`list_runs` 按项目与冻结范围版本列出元数据。主题行保存有权成员的关键词与代表文档引用。每个输入成员保存原始主题、HDBSCAN 簇编号及可得的成员概率、离群分数和主题质心余弦。按主题编号 `-1` 保存离群成员。后处理决定使用独立子表，当前决定为空。
- `evidence_for` 以运行、文档、证据和片段版本回读原话。保留来源、精确 Unicode 区间、原文及片段哈希。每次回查重新走当前项目授权和 M05/M06 或 M08 资格入口。撤销后下钻、比较和复跑失败关闭，读取快照时将受影响主题的派生关键词与代表引用遮蔽。快照库按文档 ID 引用代表原话。
- `replay` 按已封存的配置、模型和精确输入重新计算，核对向量及运行时后以新 UUID 封存并关联原运行。 `compare` 输出主题的成员交集和并集，以及配置、成员、离群、关键词、证据映射和诊断差异。相同请求的重试返回同一快照，发生中断时允许以原请求重试。
- 所有结果属于待审核候选，正式研究分母增量为 0。沿用 M09-A/B 已锁定的 BERTopic 0.17.4、UMAP 0.6.0、HDBSCAN 0.8.44 及本地向量运行时。M09-C 使用 Python 标准库 SQLite 和已有数值依赖。原算法及依赖锁沿用已验收基线。[运行时与许可证](../m09-a/README.md) · [M09-B 验证](../m09-b/README.md)

## 存储和恢复

首次使用时创建与工作库相邻的主题库，例如 `connectivity-m09-topics.sqlite3`。主题库为 SQLite v1，版本标识区分 Personal 与 Business。工作库仍为 Personal v11 和 Business v9。运行、主题、成员、代表引用及后处理决定在同一写事务中封存。外键在每个连接启用，已封存行受触发器保护。恢复时使用 SQLite Backup API 保存或恢复主题库，将其与同一工作区的匹配工作库配对，执行 `PRAGMA integrity_check` 和 `PRAGMA foreign_key_check`，并经服务复查当前证据资格。需要同时保全两库时，暂停该工作区写入，再对两库分别做一致性备份。主题库与现有工作库使用各自的备份文件。

## 验证记录

| 环境 | 范围 | 实际结果 |
|---|---|---|
| Windows 10 build 19045，Python 3.12 | M09-C、M09-A/B 及 M05–M08 直接回归 | 101/101，41.918 秒，非回环 DNS 和 socket 尝试 0 |
| 同上 | 新增离线用例 | M09-C 集成 12/12，原始诊断与输入观测新增 3/3 |
| Windows 10 build 19045，普通用户目录隔离回归 | 全套 Python | 613/613，通过，跳过 11 项可选真实模型或非 Windows 路径，非回环 DNS 和 socket 尝试 0；DPAPI 实际用户路径可用 |
| 同上 | Node 与空库冷启动 | 2/2 与 3/3 |
| 原生 Windows 11 | M09-C 固定模型、数据库重启、离线重算和逐条原话回查 | NOT_TESTED，待在目标机器复验 |
| GitHub PR #2 | Ubuntu、Windows Server 2022、Chromium | 查阅 M09-C 提交对应的 PR 检查 |

定向用例覆盖空输入、全离群、成员与证据完整性、撤销、项目和范围隔离、变更比较、原库不变、失败恢复、SQLite 一致性备份和触发器。实测过程使用合成证据，真实研究 API 调用为 0。[集成测试](../../../tests/test_m09_persistence.py) · [固定模型验收用例](../../../tests/test_m09_actual_topics.py)

## Windows 11 接续命令

在原生 Windows 11 的仓库根目录运行。使用已锁定的 CPU 研究虚拟环境 Python、获准的模型目录和已安装应用依赖的包目录。通过脚本启用离线模式及进程内网络审计，保存实际操作系统版本、Git SHA、用例明细、网络尝试数和退出码。[已批准的模型与锁定安装](../m09-a/README.md)

```powershell
[Environment]::OSVersion.VersionString
git rev-parse HEAD
& $m09Python scripts/verify-m09-offline.py $m09ModelDir docs/evidence/m09-a/model-assets.json test_m09_persistence.py test_m09_topics.py test_m09_actual_topics.py --app-site-packages $appSitePackages
```

## 研究质量状态

M09-B 保持 **ENGINEERING_PASS**。原三项合成纯度诊断 **8/11、8/12、8/13** 继续为 **QUALITY_DIAGNOSTIC_WARNING**，主题审核仍为 **PENDING**，**G3_PENDING**。历史诊断与原夹具保留，0.60 质心过滤仍为探索方案。后续获准的 M09-D 使用独立第三留出集，按既定方式比较精确率、召回率、覆盖率、噪声拒绝、复跑稳定性与跨语言及跨品类表现，并在成员变更后重算主题表示。
