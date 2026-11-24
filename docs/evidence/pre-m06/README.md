# Pre-M06 实测证据

| 执行 | 提交和结果 |
|---|---|
| 原远端验证 | `04049b375f8b0e281c5f09f51d2fb07b5f1c3463`。草稿 PR #1，Ubuntu、Windows Server 2022、Chromium 通过 |
| 初次独立反例 | `abe5c781ff60609e86ff2ff50b0e9612de29bb5d`。Ubuntu 共 136 项，13 次断言失败和 3 个错误。合成夹具，包括中英文许可、凭证和导入边界 |
| 历史状态补测 | `df2306584b4d13ea92b70b5dab57177032bcd47b`。Ubuntu 共 140 项，旧审批和旧撤销共 2 次回归失败。损坏库的保护断言通过 |
| 修复 CI | `d64fb4f29094be9a3fc9b91e2910830ea0c1c8c2`。Ubuntu 和 Windows Server 2022 各 140 项 Python、2 项 Node、3 次冷启动及 4 份历史归档通过。Chromium 8 组通过 |
| Windows 11 实机 | NOT_TESTED。本轮无实机执行环境，单独保留此前提交的实机证据 |

[基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45371258390) · [历史状态补测](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45373165462) · [修复 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45373503587) · [以往 Windows 11 实机记录](../m05/review.md)

- 日志为 Actions 的脱敏摘录，包含断言结果和实际测试摘要。浏览器截图在相应 CI 的 Chromium 产物中。 [修复前日志](baseline-regression.log) · [修复后日志](verified-ci.log)
- 审计使用每个用例的新临时库，新用例拒绝外部研究调用。历史归档只做离线验证。真实研究 API 请求 **0 次**。 [独立合成用例](../../../tests/test_pre_m06_audit.py)
- 独立回归命令为 `python -m unittest discover -s tests -p test_pre_m06_audit.py -v`。全量 CI 执行 `bash scripts/smoke-test.sh` 和 `python tests/browser_e2e.py`。Windows 11 验证须使用对应版本、同一提交和无研究凭证的临时目录，依照交接文档执行启动器和离线验证；留存系统版本、提交、冷启动、套件及路径结果。 [本机验证手册](../../../HANDOVER.md#复建开发环境)
