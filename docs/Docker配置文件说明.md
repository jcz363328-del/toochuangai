# Docker Compose 配置文件说明

项目根目录有三份 Compose 配置。它们定义 Docker 要启动的服务、对外端口，以及数据目录或数据卷的挂载方式。下面的命令均在项目根目录执行。

| 文件 | 用途 | 启动命令 |
| --- | --- | --- |
| `compose.yaml` | 默认部署配置。主站、小哈、无限画布等服务在同一个容器内运行，默认对外入口为 `8000`。 | `docker compose up -d` |
| `compose.single.yaml` | 显式指定单容器部署时使用，与默认配置采用同一种部署方案。 | `docker compose -f compose.single.yaml up -d` |
| `compose.multi.yaml` | 多容器部署配置。主站、小哈、VideoClaw 等按服务拆分运行，端口和数据卷按这份配置管理。 | `docker compose -f compose.multi.yaml up -d` |

`compose.yaml` 和 `compose.single.yaml` 是同一套部署方式的两个入口。日常启动选一份即可。完整配置与部署步骤见[单容器部署](单容器部署.md)和[多容器部署](多容器部署.md)。

如果在 Windows 上直接启动本地开发环境，请看[本地启动说明](本地启动说明.md)。
