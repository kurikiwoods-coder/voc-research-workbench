# G-1-P-B 独立安全复审

实现与复审分离。复审角色在云端 Linux 读取 Phase 1 到 B 的代码差异，在独立临时目录以 TestClient、SQLite 和受控 opener 复验。未编辑实现，也未配置或调用任何真实供应商。

- 最终专项复跑 **27/27**，历史来源归档恢复专项 **6/6**。额外核对两个 CLOUD 版本下的归档导出、恢复命令和直接恢复函数，均在工作库或传输前拒绝。
- 独立复验认证前拒绝、请求声明不升级权限、导入与审核操作的权限分离、同冻结范围读写、未知对象处理、读取重审、商用同批证据及当前审批绑定。
- 两道门禁均未复用另一版本证据。个人正式采集、出队、编码、历史运行回放和发布入口未放行。PackyCode 原预检的执行和续跑授权封存。
- 核对 `src/raw_store/migrations/`、`denominators.py`、`relation_access.py` 和冻结文档没有改动。既有 Windows 实机只绑定原受测源码。

复审确认 7 个已修复问题，其中 P0 1、P1 5、P2 1。未关闭 P0/P1 为 **0**。补记一项 P3 浏览器身份验证提示。Windows 11 原生 ACL、运行与 DPAPI 为本轮实机待核。[缺陷台账](bug-register.md) · [回归记录](README.md)

Windows Server 2022 首轮的 PB-09 与 PB-10 修复后，独立复验 M06 迁移 11/11、M07 迁移 4/4、PackyCode 合成预检 15/15、B 策略 27/27、损坏库保护 1/1，合计 **58/58**。另实测存储路径保留、别名无法重开个人库以及头校验异常会关闭连接。修复后的 Windows Server 2022 CI 亦通过。[修复后 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45749971864)
