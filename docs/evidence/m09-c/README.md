# M09-C 主题快照、证据追溯与离线复跑

实施基线 `cd4859dfa12cdc5676d13fd5033b2a04a8ada19d`，Personal 开发分支 `codex/g1-personal-phase-1`，草稿 PR #2。范围为 M09-C 隔离工程。**M09-C = PENDING_ACCEPTANCE**，**M09 = PARTIAL**，已验收核心 **41/79**。

## 本地发现服务

- `TopicRuns.create` 接收受信项目授权函数、固定范围版本、精确证据引用和获准离线模型。UUID 标识每次运行。快照记录起止时间、状态、模型 ID 和修订、模型资产和运行时版本、Embedding 运行 ID、输入及向量摘要、注册表版本、预处理、语言和请求及实际聚类参数。
- `get` 恢复已封存快照，`list_runs` 按项目与冻结范围版本列出元数据。主题行保存有权成员的关键词与代表文档引用。每个输入成员保存原始主题、HDBSCAN 簇编号及可得的成员概率、离群分数和主题质心余弦。按主题编号 `-1` 保存离群成员。后处理决定使用独立子表，当前决定为空。
- `evidence_for` 以运行、文档、证据和片段版本回读原话。保留来源、精确 Unicode 区间、原文及片段哈希。每次回查重新走当前项目授权和 M05/M06 或 M08 资格入口。撤销后下钻、比较和复跑失败关闭，读取快照时将受影响主题的派生关键词与代表引用遮蔽。快照库按文档 ID 引用代表原话。
- `replay` 按已封存的配置、模型和精确输入重新计算，核对向量及运行时后以新 UUID 封存并关联原运行。 `compare` 输出主题的成员交集和并集，以及配置、成员、离群、关键词、证据映射和诊断差异。相同请求的重试返回同一快照，发生中断时允许以原请求重试。
- 所有结果属于待审核候选，正式研究分母增量为 0。沿用 M09-A/B 已锁定的 BERTopic 0.17.4、UMAP 0.6.0、HDBSCAN 0.8.44 及本地向量运行时。M09-C 使用 Python 标准库 SQLite 和已有数值依赖。聚类算法沿用已验收基线。Windows CPU 锁的 jieba 轮包哈希按本页重建记录修订。[运行时与许可证](../m09-a/README.md) · [M09-B 验证](../m09-b/README.md)

## 存储和恢复

首次使用时创建与工作库相邻的主题库，例如 `connectivity-m09-topics.sqlite3`。主题库为 SQLite v1，版本标识区分 Personal 与 Business。工作库仍为 Personal v11 和 Business v9。运行、主题、成员、代表引用及后处理决定在同一写事务中封存。外键在每个连接启用，已封存行受触发器保护。恢复时使用 SQLite Backup API 保存或恢复主题库，将其与同一工作区的匹配工作库配对，执行 `PRAGMA integrity_check` 和 `PRAGMA foreign_key_check`，并经服务复查当前证据资格。需要同时保全两库时，暂停该工作区写入，再对两库分别做一致性备份。主题库与现有工作库使用各自的备份文件。

## 验证记录

| 环境 | 范围 | 实际结果 |
|---|---|---|
| Windows 10 build 19045，Python 3.12 | M09-C、M09-A/B 及 M05–M08 直接回归 | 101/101，41.918 秒，非回环 DNS 和 socket 尝试 0 |
| 同上 | 新增离线用例 | M09-C 集成 12/12，原始诊断与输入观测新增 3/3 |
| Windows 10 build 19045，普通用户目录隔离回归 | 全套 Python | 共 613 项，602 通过、0 失败或错误、11 跳过。152.364 秒，非回环 DNS 和 socket 尝试 0 |
| 同上 | Node 与空库冷启动 | 2/2 与 3/3 |
| 原生 Windows 11 26H2 x64（26300.9974），2026-11-28 | M09-C 固定模型、工作库重开、离线复算和逐条原话回查 | 22 通过、0 失败、3 项 G3 质量诊断按原开关跳过。95.373 秒，退出码 0，进程审计的非回环 DNS 和 socket 尝试 0 |
| GitHub PR #2 | Ubuntu、Windows Server 2022、Chromium | 代码提交 cc07435 三项通过。[Actions](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/46012213223) |

沙箱全量回归记录 8 个失败和 67 个错误条目，涉及原有凭证、DPAPI 与用户目录边界。清除供应商环境变量并在普通 Windows 用户目录复测后，全部适用用例通过。11 项跳过包括 10 项需要单独提供固定模型运行时的用例及 1 项非 Windows 平台用例。

定向用例覆盖空输入、全离群、成员与证据完整性、撤销、项目和范围隔离、变更比较、原库不变、失败恢复、SQLite 一致性备份和触发器。实测过程使用合成证据，真实研究 API 调用为 0。[集成测试](../../../tests/test_m09_persistence.py) · [固定模型验收用例](../../../tests/test_m09_actual_topics.py)

## jieba 0.42.1 受控重建

原锁定轮包无法从可访问的本机资产恢复。经负责人批准，使用 PyPI 官方源码包重建 `jieba-0.42.1-py3-none-any.whl`。本机重新计算的源码 SHA-256 与 PyPI 发布记录一致。`PKG-INFO` 和 `setup.py` 确认版本为 0.42.1、MIT、无声明依赖。官方源码归档没有独立 LICENSE 文件。[PyPI 发布文件](https://pypi.org/project/jieba/0.42.1/#files) · [源码清单](../m09-a/jieba-source.json)

| 资产 | SHA-256 |
|---|---|
| 官方源码 `jieba-0.42.1.tar.gz` | `055ca12f62674fafed09427f176506079bc135638a14e23e25be909131928db2` |
| 已替换的原轮包锁 | `9ed35307b6a7abdfc49f568af7731c64578d25164e0a46a73e7cbe259014831b` |
| 两次独立干净构建及验收 wheelhouse | `c06757714d6eb7d1c9c6037d774ffd68350da42b8f83dc8c33f17b0f8ead04ad` |

原生 Windows 11 x64 使用 CPython 3.12.9，分别创建两套干净的构建虚拟环境，均使用 CPython 随附的 pip 24.3.1。从已校验的本地目录离线安装 setuptools 80.9.0 和 wheel 0.45.1。两项构建依赖的 SHA-256 分别为 `062d34222ad13e0cc312a4c02d73f059e86a4acbfbdea8f8f76b28c99f306922` 和 `708e7481cc80179af0e556bbf0cc00b8444c7321e2700b8d8580231d13017248`。构建固定 `PYTHONHASHSEED=0`，并使用官方归档中 `setup.py` 的修改时间作为 `SOURCE_DATE_EPOCH`。

```powershell
$env:PYTHONHASHSEED = '0'
$env:SOURCE_DATE_EPOCH = '1579530154'
& $buildPython -m pip install --no-index --no-deps --find-links $verifiedBuildWheelhouse --require-hashes -r $buildToolLock
& $buildPython -m pip wheel --use-pep517 --no-index --no-deps --no-build-isolation --no-cache-dir --wheel-dir $buildOutput $verifiedSdist
```

两次产物均为 19,314,526 字节，SHA-256 相同。54 个包文件与官方源码逐字节一致，58 条 `RECORD` 全部核验通过。轮包为 `py3-none-any`，版本为 0.42.1，MIT 元数据一致，新增依赖和可执行载荷均为 0。额外的 Python 3.12.9 隔离环境通过哈希锁安装、`pip check`、导入及中文分词。Windows CPU 锁和轮包来源清单各替换一处 jieba 轮包 SHA-256。[CPU 哈希锁](../m09-a/requirements-windows-py312-cpu.txt) · [轮包来源](../m09-a/wheelhouse-provenance.json)

本机复验根目录为 `C:/Users/kurik/Documents/Codex/2026-11-28/m09-c-windows11`。`build` 保留原源码和三份早期候选，早期失败的原锁校验保留在根目录 `acceptance-asset-check.log`。`controlled-jieba-0.42.1` 保有两次新构建产物、`build-tools.txt`、`build.log`、`wheel-verification.log` 和新 `acceptance-asset-check.log`。

## Windows 11 本机核查与复跑命令

2026-11-28，本机确认为 **Windows 11 家庭中文版 26H2 x64（26300.9974）**。测试以 `codex/g1-personal-phase-1` 的 `0c1ec3fb2e71193c2763e3da84107e1222ff293e` 为基线。该基线与此前核对的远端开发分支和草稿 PR #2 一致，对应 Ubuntu、Windows Server 2022、Chromium 均通过。M09-C 实现提交为 `cc07435db06ff6d2e00c93075ae68428b72ce3d8`。此次依赖与证据修订的交付为本地提交，CI 沿用可验证的历史基线记录。[草稿 PR #2](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/2) · [基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/46013848716)

- 在 CPython 3.12.9 x64 的 `cpu-env` 中，从本机 wheelhouse 哈希校验并离线安装全部 44 项锁定依赖，安装和 `pip check` 的退出码均为 0。MiniLM 固定修订 `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` 的 11 个资产均通过哈希校验。应用包目录沿用 `C:/Users/kurik/Documents/Codex/VOC Workbench 研究/.venv/Lib/site-packages`，该应用环境单独通过 `pip check`。[模型清单](../m09-a/model-assets.json)
- Python 专项共 25 项，22 通过、0 失败、3 项 G3 诊断跳过，耗时 95.373 秒。CPU 实际加载 MiniLM、BERTopic、UMAP 和 HDBSCAN，验证重新打开工作库和主题库、完整快照重载、逐条原话回查、离线复跑和结果比较。独立持久化用例通过精确证据版本、撤销后的回查及复跑拒绝、派生内容遮蔽和故障恢复。
- 运行使用隔离数据库及合成证据。进程退出码 0，Python 审计的非回环 DNS 和 socket 尝试 0，真实研究 API 调用 0。旧有 `StarletteDeprecationWarning` 在运行中出现，专项结果为通过。原始安装与测试日志位于复验根目录 `controlled-jieba-0.42.1/acceptance-install.log` 和 `controlled-jieba-0.42.1/windows11-native-acceptance.log`。
- 实际模型验收采用原有本地工作树测试改动，增加重开工作库、重建服务、核对快照及逐条原话的断言。运行时测试文件的 SHA-256 为 `7cd9a6d7859d325bb17c35c916c4d77a2cdc346026939cdccfd73494e4f7532f`，CRLF 原始 Git blob 为 `da0fdc3244644f455fd543704c717aa3839745e8`，Git 换行标准化后的 blob 为 `0fbdd59c4d3804ed8573e0c3acad33d3b6779073`。本次提交保存可复现的证据补丁，原测试文件和根目录完整差异 `acceptance-test-working-tree.diff` 仍在本机。[验收测试补丁](windows11-native-test.diff) · [持久化用例](../../../tests/test_m09_persistence.py)

在没有本地测试改动的复验工作区，可先用 `git apply --check --unidiff-zero docs/evidence/m09-c/windows11-native-test.diff` 核对补丁，再去掉 `--check` 应用。设置 `$m09Python`、`$m09Wheelhouse` 和 `$m09ModelDir` 指向独立目录中的 `cpu-env/Scripts/python.exe`、`wheelhouse` 和 `model`，并设置 `$appSitePackages` 为已核查的应用包目录。从仓库根目录执行下列命令。[获准模型与锁定安装](../m09-a/README.md)

```powershell
[Environment]::OSVersion.VersionString
git rev-parse HEAD
git --no-pager diff -- tests/test_m09_actual_topics.py
& $m09Python -m pip install --no-index --find-links $m09Wheelhouse --require-hashes -r docs/evidence/m09-a/requirements-windows-py312-cpu.txt
if ($LASTEXITCODE -ne 0) { throw "M09 offline installation failed" }
& $m09Python -m pip check
if ($LASTEXITCODE -ne 0) { throw "M09 CPU environment failed pip check" }
& $m09Python scripts/verify-m09-offline.py $m09ModelDir docs/evidence/m09-a/model-assets.json test_m09_persistence.py test_m09_topics.py test_m09_actual_topics.py --app-site-packages $appSitePackages
$LASTEXITCODE
```

## 全项目可行性检查

| 检查项 | 状态 | 依据 |
|---|---|---|
| M09-C 需求与架构兼容 | PASS | 五项功能已实现。本地主题库独立封存，Personal v11、Business v9，M06 核心契约和 M07 消费契约沿用现行版本 |
| 系统集成、安全与恢复 | PASS | M05–M08 上游和 M09 定向测试验证授权、精确证据、备份恢复、项目隔离及幂等。全套 Windows 10 回归及代码提交的三项 CI 通过 |
| 目标部署的固定模型运行 | PASS | Windows 11 原生 CPU 完成固定权重推理、快照重开、证据回查及离线复跑，22 项通过，0 项失败 |
| M09-C 工程验收 | PENDING_ACCEPTANCE | Windows 11 专项通过，依赖与证据本地交付，待负责人验收 |
| M09 研究质量与下一阶段接续 | AT RISK | 原三项纯度诊断保留，正式 G3 及候选视图归属原定接续。M09-D 须负责人单独授权 |

本次检查覆盖 M09-C 对完整研究链路的影响。全项目发布验收依原路线图及业务门禁安排。[路线图](../../planning/ROADMAP-V2.md)

## 研究质量状态

M09-B 保持 **ENGINEERING_PASS**。原三项合成纯度诊断 **8/11、8/12、8/13** 继续为 **QUALITY_DIAGNOSTIC_WARNING**，主题审核仍为 **PENDING**，**G3_PENDING**。历史诊断与原夹具保留，0.60 质心过滤仍为探索方案。后续获准的 M09-D 使用独立第三留出集，按既定方式比较精确率、召回率、覆盖率、噪声拒绝、复跑稳定性与跨语言及跨品类表现，并在成员变更后重算主题表示。
