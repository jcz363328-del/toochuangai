# toochuangai

当前采用 Docker 单容器、8000 单入口部署。启动、数据挂载与回滚说明请参阅 [DOCKER.md](DOCKER.md)。

## 项目导航

| 位置 | 用途 |
| --- | --- |
| `app.py` | 主站入口、路由与模块注册 |
| 根目录业务 `.py` | 现有业务模块，按功能英文前缀查找 |
| `templates/`、`static/` | 主站页面与静态资源 |
| `innovation/` | 创新提案业务 |
| `business_analysis/` | 经营分析前端与数据接口 |
| `listing_agent/`、`listing_agent_v2/` | Listing 生成模块 |
| `图片/`、`无限画布/` | 小哈与无限画布项目 |
| `VideoClaw/`、`ads_monitor_web/` | 视频与广告独立项目 |
| `docker/`、`compose.yaml` | 容器启动、网关、健康检查与部署工具 |
| `tests/` | 主项目回归测试，不是临时文件 |
| `demo/` | UI 演示，不参与生产运行 |
| `tmp/`、`logs/`、`outputs/`、`docker-data/` | 本地临时文件、日志、输出及部署状态；不要当作源码目录 |

目录约定和整理边界见 [项目结构规范](docs/project_structure.md)，测试分组见 [测试说明](tests/README.md)。
