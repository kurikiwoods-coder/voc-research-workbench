# G-1-P-B 双版本服务端策略

统一研究引擎由服务端确定产品版本和部署方式。空配置使用 `BUSINESS / LOCAL`，沿用原工作台、SQLite v8、凭证库、验收和账户审查。显式值使用 `PERSONAL`、`BUSINESS`、`LOCAL` 或 `CLOUD`，非法取值拒绝启动。两种 CLOUD 组合目前只提供状态，不开业务库、凭证库或调度器。[Phase 1 双版本政策](edition-policy.md) · [门禁契约](g1-personal-gate-contract.md)

## 个人本机启动

先在可信本机普通用户终端创建专用个人目录和项目。Windows 使用当前用户的 `LOCALAPPDATA` 子目录。Linux 使用当前用户拥有且仅自己可访问的目录，启动工具可创建目录。新目录须为空，续开须具有个人工作区标识。保留个人和商用各自的备份路径。个人 SQLite 的 `application_id` 标明版本域，使用当前版本时，复制出的个人库也不能作为商用库打开。现有 v8 业务迁移和数据关系保持原样，旧版程序未实现此隔离机制。

```powershell
$personalRoot = Join-Path $env:LOCALAPPDATA "VOC Personal"
python -m src.dashboard.personal_workspace $personalRoot --name "图书馆预约研究" --topic "哪些预约步骤容易让用户放弃"
```

本机工具复用 M03 项目与冻结快照。需要续接一次中断的相同提交时保留并重复使用同一个 `--request-key`。从生成结果记录 `study_id`、`scope_id` 和 `scope_version`。在服务进程的私有配置设置下列值，重启生效。

| 设置 | 取值 |
|---|---|
| `VOC_EDITION`，`VOC_DEPLOYMENT` | `PERSONAL`，`LOCAL` |
| `VOC_DATA_DIR` | 上述个人目录的绝对路径 |
| `VOC_PERSONAL_OPERATOR_REF`，`VOC_PERSONAL_OWNER_REF` | 低敏、可审计的本机操作者和负责人标识 |
| `VOC_PERSONAL_OWNER_SHA256` | 在本机以高熵随机密码从安全输入计算的 SHA-256 十六进制。使用密码管理器生成并保管 64 个随机小写十六进制字符，或 32 字节随机值的 43 字符无填充 base64url 表达 |
| `VOC_PERSONAL_PROJECT_GRANTS` | 服务端 JSON 列表。每个项目绑定一个明确冻结范围、一份授权引用、UTC 时效及操作权限。空列表允许 Owner 验证身份并看到空项目列表 |

可在本机以 `python -c "import getpass,hashlib; print(hashlib.sha256(getpass.getpass().encode('ascii')).hexdigest())"` 计算证明摘要。原密码留在密码管理器，放入本机浏览器原生身份验证框，用户名为 `owner`。服务器仅保存摘要，恒定时间比较。工作台页面不接收或保存密码。换密码或调整授权时更新可信进程配置并重启。启动时沿用现有仅监听回环地址的工作台，保持 Windows 用户目录原有私有 ACL，使用后关闭浏览器会话。样例配置中的标识和时间仅示范格式。

```json
[
  {
    "study_id": "00000000-0000-4000-8000-000000000001",
    "scope_id": "00000000-0000-4000-8000-000000000002",
    "scope_version": "v1",
    "purpose": "personal_research",
    "permissions": ["read_scope", "import_local", "read_corpus", "review_corpus", "export_import_issues", "read_formal_status"],
    "evidence_ref": "local:owner-grant-001",
    "starts_at": "2026-11-26T01:00:00Z",
    "expires_at": "2026-11-27T01:00:00Z"
  }
]
```

`read_scope` 允许在本机读取已获准的冻结范围及授权投影。`import_local` 允许文件暂存、预览、确认、回读状态和撤销。`read_corpus` 按 M05 实时资格读取可见记录。`review_corpus` 要求同时具有该范围的读取权，并保留原许可和历史审核约束。`export_import_issues` 只导出已有的脱敏导入错误报告。`read_formal_status` 读取正式不可用状态。个人工作区入口复用同一研究库代码。每次请求核对当前项目、冻结范围、作用及期限，数据读写在实际 SQLite 快照内复核。个人版的批次视图、草稿清理和重复组投影均限制在授权范围。

## 接口与当前边界

| 入口 | B 阶段行为 |
|---|---|
| `GET /api/edition` | 版本、部署、策略版本、两道门禁、操作状态及原因。页面使用这份投影，响应无密钥和原话 |
| `GET /api/edition/projects`、`GET /api/edition/projects/{study_id}` | 认证后查看作用范围、身份标识、操作权限和受控授权引用 |
| 项目冻结范围、导入、语料接口 | 已有接口复用精确范围及独立权限，未知或无权对象以统一状态回应 |
| `GET /api/studies/{study_id}/denominators?mode=formal` | 个人正式分析返回 `unavailable`、`counts: null` 及阻塞原因。原统计口径版本 `M06-B-F.1` |
| 旧连通性、诊断、采集预约和出队、续跑、编排、注册表发行、研究发布 | 个人版旧路径拒绝执行。工程合成回归继续走现有隔离机制，个人审批和正式同批验收入口分别由 C 与 D 交付 |
| 商用历史与提供商 | 原商用工作台和判定继续适用。新状态摘要在同批证据和当前账户审查一致时才投影商用通过 |
| PackyCode 独立预检 | 原授权已耗尽，命令只保留原账本查阅；`--execute`、`--resume-second` 均关闭。归档和实际成本证据保留 |

代码由 `src/edition_policy.py` 决策，`src/dashboard/edition_access.py` 在路由解析后、业务请求体解析前执行策略。本机回环和同源限制仍适用。Windows 依当前用户本机运行目录的继承权限及原有 DPAPI 服务；个人版 B 不打开供应商凭证库。[部署契约](edition-deployment-matrix.md) · [工程证据](../evidence/g1-p-b/README.md)
