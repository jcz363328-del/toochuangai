# 测试目录

这里的文件用于回归验证，不是临时文件。暂不移动到子目录，因为多项测试通过 `Path(__file__).parents[1]` 定位项目根目录。

| 前缀或名称 | 范围 |
| --- | --- |
| `test_*permission*`、`test_department*`、`test_operation*` | 权限和部门 |
| `test_dashboard*` | 导航、总览与功能目录 |
| `test_business_analysis*` | 经营分析 |
| `test_innovation*` | 创新提案 |
| `test_tk*` | TK 数据、客服与授权 |
| `test_daily_replenishment*`、`test_smart_replenishment*` | 补货 |
| `test_xiaoha*`、`test_a_plus*` 等 | 小哈与图片处理 |
| `test_docker_runtime.py` | 容器与服务集成 |
| `*_browser.cjs`、`videoclaw_api_client_test.mjs` | 浏览器与 JavaScript |

其他子项目测试保留在各自目录，使用自身工具链运行。

## 运行

在项目根目录、安装了对应依赖的开发环境中执行：

```powershell
python -m pytest tests/test_docker_runtime.py -q
python -m unittest discover -s tests -p "test_xiaoha_ui_stability.py"
```

主站测试应关闭后台通知任务。数据库、付费接口及浏览器测试应先核对 mock 与环境要求，不直接在生产容器跑全套测试。

## 本次清理

- 临时源码包 `tmp/business-analysis-20260826/经营分析源码包-20260826/tests/formulas.test.mjs` 与正式版本的 SHA-256 完全一致，删除临时副本，保留 `business_analysis/tests/formulas.test.mjs`。
- 主项目 `tests/` 未发现完全相同的文件，不按名称相似删除测试。
- 主项目测试目录排除在新 Docker 构建上下文之外。
