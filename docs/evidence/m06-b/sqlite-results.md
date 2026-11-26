# M06-B SQLite 约束与 M05 实时资格实验

运行日期为 2026-11-24。代码基线 `48b5352feb72df852417d6c9edb96775896153a7`，Windows 10 会话的项目虚拟环境，Python 3.12.14 / SQLite 3.53.1。下列程序用标准 SQLite 连接和现有合成测试夹具，分别生成一次性约束原型库及当前迁移初始化的 v6 项目库。FastAPI TestClient 在进程内调用 API，夹具拒绝研究网络请求。退出清理临时文件。

```powershell
.\.venv\Scripts\python.exe -B docs/evidence/m06-b/sqlite-probe.py
```

退出码 0。现有 TestClient 依赖发出 `StarletteDeprecationWarning`，该警告已在 Pre-M06-D 登记。

```text
Python 3.12.14, SQLite 3.53.1
PASS single root, explicit NULL check, exact-version/confirmed task FK, one primary
PASS deferred missing primary rejects COMMIT; explicit rollback removes version and command
PASS competing writer busy then stale; same-key same-hash replay; changed hash conflict
PASS actual v6 M05 WAL: stale read and SQLITE_BUSY_SNAPSHOT; fresh write lock and fresh qualification
PASS UTC day advance under write lock expires last independent support
PASS M05 GET 200/200/200 -> 409/409/200 -> 409/409/409 -> 200/409/409
PASS old grant rejected; wrong project 404; revoked excerpt masked; research/outbound false
```

| 实验 | 最小输入与交错 | 断言 |
|---|---|---|
| PROTOTYPE_TESTED 约束 | 二根；确认无主；引用仅存在于其他版本的任务；引用同版未确认任务（两项均以次边测试同一复合外键）；同意图双主 | SQLite 分别拒绝；允许无主候选，`foreign_key_check` 无违规。 |
| PROTOTYPE_TESTED 回滚 | 插入已确认意图及指向尚不存在的必需主边、新版本与命令，随后尝试提交 | 延迟外键使 COMMIT 失败；显式回滚撤销三类写入，后续发行路径可以继续。 |
| PROTOTYPE_TESTED 并发和幂等 | 两连接竞争写锁，B 基于旧版；模拟 A 客户端未收到响应后重试 | A 提交一版；B 锁等待返回 busy，重取锁看到旧版冲突。同命令键同摘要回原版，异摘要冲突，合计一条命令。 |
| PROTOTYPE_TESTED 现有 M05 路径 | 同项目原始来源、带 fragment 的副本、独立 URL。三者核准后，A 打开 WAL 快照；B 经真实 M05 路由撤销原始授权 | A 仍读三条均合格，写升级 `SQLITE_BUSY_SNAPSHOT`；新事务见前两条失格、第三条仍合格，且另一写者 `SQLITE_BUSY`。副本明文被屏蔽。 |
| PROTOTYPE_TESTED 日期边界 | `BEGIN IMMEDIATE` 内以留存截止日及下一 UTC 日查询同一快照 | 独立来源从可用变为失格，锁不能冻结时钟。使用受控日期输入模拟，未调整系统时间。 |
| PROTOTYPE_TESTED 撤销及重新授权 | 撤销第三条；尝试复用失效许可，再为第一条提出独立新许可；另外用第二项目查询第一项目记录 | 真实路由依次返回 `409/409/409` 和 `200/409/409`；旧许可 422，越项目 404，新授权仍保持 research/outbound false。 |

## 证据边界

- 数据库约束原型隔离验证 SQLite 机制。封版触发器、最终业务 Schema、覆盖所有关系的迁移、真实崩溃恢复及 M11 指令均为 IMPLEMENTATION_NOT_TESTED。
- 实验调用现有 `CorpusStore.source_row` 和共享 `qualification` 验证同一连接可得到当前结果。当前公开 `qualified_record` 的改造及未来关系写入仅 DESIGN_CHECKED，后续须以真实入口回归。
- 部分与全部撤销的状态在语料级别实测。M06 发生 M、M12 回执、缓存、报告、外发和重新许可后的统计均待各模块实现后验证。归档资格与当前时钟必须复验，SQLite 写锁对已发数据没有回收能力。
