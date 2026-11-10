本文件是多容器方案的历史说明，不是当前启动指南。当前根目录 `.env` 使用正式数据路径和 8000 端口，不能据此并行启动旧方案；旧方案仅用于组件镜像构建，回滚运行需先停正式服务并单独审核端口和挂载。所有旧方案命令显式添加 `-f compose.multi.yaml`。

# Windows Docker Desktop 运行说明

## 运行范围与安全默认值

- 主站 Flask 使用单进程、多线程 Waitress，避免飞书令牌内存缓存跨进程不一致。
- 经营分析 Node API 独立容器运行，与主站共享网络命名空间，仅监听内部 `127.0.0.1:4311`，不直接对外暴露数据库接口。
- 镜像构建经营分析、Listing Studio V2、广告诊断、VideoClaw 和无限画布前端，不依赖 Windows 上的 node_modules 或已构建文件。
- 默认访问 `http://localhost:18080`，不停止、不替换当前 Windows 上的 8000 服务。
- 默认关闭主站定时提醒，避免测试和原服务重复发送消息；经营分析仍会刷新自己的读取缓存。
- 数据库仍使用环境文件中的 SQL Server。测试站的正常业务操作仍可能修改这个数据库；需要完全隔离时请配置测试数据库。
- `.env` 仅运行时注入，已被 Git 和 Docker 构建排除。不要发送、提交此文件，也不要将包含密钥的 `docker inspect` / `docker compose config` 完整输出发给别人。

## 首次配置

环境文件现已统一为根目录 `.env`，原独立预览配置存放在 `docker-data/env-backups/` 中。以下保留历史方案操作示例，不代表当前环境隔离；不要覆盖现有 `.env`。
其他电脑首次部署时运行：

```powershell
Copy-Item .env.example .env
notepad .env
python docker/prepare_runtime.py
```

新克隆项目应先初始化 Git 子模块：`git submodule update --init --recursive`。运行准备脚本只在目标文件不存在时复制配置，不覆盖已有 Docker 配置；现有电脑已完成准备。

填写 DB_*、FLASK_SECRET_KEY、INNOVATION_SECRET_KEY 和飞书/AI 平台密钥。空白会导致对应功能不可用；两项会话密钥不能为空，可用 `python -c "import secrets; print(secrets.token_hex(32))"` 生成。
`env_file` 使用 raw 格式，值直接填写，不要额外包裹引号，密码内的 `$` 不需要转义。

SQL Server 在当前 Windows 电脑时，`DB_SERVER=host.docker.internal`，不能写 localhost；在其他服务器时填数据库真实地址。确认数据库已开启 TCP/IP、对应端口及防火墙放行。不要为此把数据库端口开放到公网。

## 构建与启动

要求 Docker Desktop 已启动，使用 Linux containers，Docker Compose 支持 `env_file.format: raw`（Compose 2.30+）。

```powershell
docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --build
docker compose --env-file .env ps
Invoke-WebRequest http://localhost:18080/_container/health
```

首次构建需要下载 Python、Node 和系统依赖，会比后续启动慢。健康接口只检查主站进程，不代表数据库、飞书授权或全部第三方平台已验证通过。

查看日志、停止、更新：

```powershell
docker compose --env-file .env logs --tail 100 web sales-api
docker compose --env-file .env down
docker compose --env-file .env up -d --build --force-recreate
```

更新时一起重建两个服务，因为经营分析共享 web 的网络命名空间。不要只重建 web 后留下旧的 sales-api。
`down` 保留数据；不要使用 `down -v`，它会删除命名数据卷。

## 飞书登录与其他电脑访问

默认仅本机访问。飞书开放平台必须允许测试站的回调地址，例如 `http://localhost:18080/feishu/callback`（以平台允许的地址规则为准）。现有线上地址的白名单不会自动包含测试端口。
需要手机、同事或外部飞书访问时，使用可达的测试域名/HTTPS 地址，并对应配置：

```dotenv
DOCKER_BIND_ADDRESS=0.0.0.0
FEISHU_PRODUCTION_DOMAIN=https://你的测试域名
```

同时配置反向代理、飞书回调白名单和必要的 Windows 防火墙规则，再执行启动命令重建容器。不需要开放数据库或 4311 端口。
不要将回调配置成 `host.docker.internal`、容器名或容器内部 IP。

## 文件与数据持久化

- `DOCKER_STORAGE_PATH` 默认 `./docker-data/storage`，挂载到容器 `/data`。Windows 的 `D:\tuchuangai` 代码路径通过公共路径转换函数映射到该目录。
- 此默认目录是独立的空目录，历史模特视频、创新图片、培训素材不会自动复制。需要历史文件时，先将所需素材复制到该目录并保留原子目录结构。
- 也可以设置 `DOCKER_STORAGE_PATH=D:/tuchuangai`，但这会让测试站直接读写生产素材；请先备份，谨慎使用。
- 知识库、Listing 数据、经营分析 data、导出文件和日志使用 Compose 命名卷，可在 Docker Desktop 的 Volumes 中查看。
- 命名卷首次创建时从镜像初始化，后续构建不会覆盖已有卷内容；升级静态快照时需单独同步对应文件并备份，不要通过删除整个卷来更新。
- 数据库由现有 SQL Server 单独备份；Docker 数据卷不包含 SQL Server 数据。
- 容器内的 AI 运行配置和日报卡片映射写入 `/data`，随存储挂载保留；不会读取镜像外 Windows 上的同名运行文件。

## 统一服务清单

全部由相同的 `docker compose --env-file .env up -d --build` 管理，统一自动重启、健康检查和持久化，不再依靠 Windows 启动脚本。

| Compose 服务 | 内容 | 访问方式 |
| --- | --- | --- |
| web | 主站、权限与同源代理 | localhost:18080 |
| sales-api | 经营分析数据接口 | 内部 4311，不对外发布 |
| xiaoha | 小哈 Streamlit 图片工厂 | localhost:18501/lashforge |
| xiaoha-static | 无限画布、上传素材与图片接口 | localhost:18502/infinite-canvas/ |
| videoclaw-frontend | VideoClaw Next.js 前端 | 主站 /ai/video-claw，AI 部门及功能权限校验 |
| videoclaw-backend | VideoClaw FastAPI、FFmpeg、Chromium | 内部 18000，经主站 /ai/video-claw/backend 代理 |
| ads-api | 广告诊断与受控操作接口 | 内部 4174，经主站权限代理 |

无限画布由小哈的静态/API 服务提供，不再额外启动另一个前端开发服务器。VideoClaw 流式接口使用同源流式代理，不将用户浏览器请求发往用户自己的 localhost，也不绕过主站权限直接暴露后端。

- 小哈与主站共用 `.env` 中的模型平台配置和 `LASHFORGE_LOGIN_ACCOUNTS_JSON`，不会把原 `图片/config.py` 密钥打入镜像。
- VideoClaw 配置在 `docker-data/videoclaw/config.yaml`，初次从现有配置复制；会话、任务、生成视频及临时文件分别持久化。复制配置不等于迁移历史任务文件，历史文件需另行备份导入。
- 广告配置在 `docker-data/ads/ads_monitor_config.json`，平台凭据使用 `SELLFOX_CLIENT_ID` 和 `SELLFOX_CLIENT_SECRET`；不依赖 Windows DPAPI 密文。在现有电脑已复制可读取的凭据到独立 `.env`，其他电脑需自行填写。
- 广告数据和输出使用独立卷，不会直接挂载、修改当前 Windows 服务的历史 SQLite 文件。镜像包含 ODBC Driver 17；首次安装按微软驱动条款接受 EULA，详见[微软安装说明](https://learn.microsoft.com/en-us/sql/connect/odbc/linux/installing-the-microsoft-odbc-driver-for-sql-server)。
- 经营分析缓存刷新保留；原 Windows 广告计划任务和其他自动采集任务不会自动复制为 Linux 定时任务，避免在测试阶段重复采集或操作广告。
- 初次部署的历史图片、生成任务和广告快照默认不迁移；页面可用不代表历史资料已自动同步，也不代表已验证全部收费模型生成流程。

其他电脑访问时，除主站地址之外，还需设置 `DOCKER_XIAOHA_PUBLIC_URL` 和 `DOCKER_UPLOAD_PUBLIC_URL` 为浏览器及模型平台可达的地址；默认 localhost 只用于本机测试。`DOCKER_XIAOHA_PORT`、`DOCKER_ASSETS_PORT` 分别配置 18501 和 18502 的对外端口。
需要平台拉取上传素材时，上传地址必须公网可达，并按需求配置 HTTPS 和反向代理；不要把 `host.docker.internal` 给浏览器或云平台使用。

## 正式切换

先验收登录、权限、数据库读写、文件上传及各独立服务，再决定是否切换原端口/域名。
当前测试默认 `TC_BACKGROUND_JOBS=0`。只有确认旧服务相同定时任务已停用时，才改为 `1` 并重建容器，避免重复提醒。
当前配置没有自动关闭原服务，也没有更改 Windows 防火墙、SQL Server 或飞书开放平台配置。
首次 npm 构建发现现有经营分析依赖存在审计漏洞，未自动执行可能破坏兼容性的 `npm audit fix --force`；对公网发布前应另行审计和升级依赖。

## 本机验收记录

2026-11-10：7 项服务构建成功并达到 healthy；主站健康接口返回 ok；SQL Server `SELECT 1` 通过；前端产物存在；镜像内不存在 `.env`、`.env`；原 Windows 8000 监听进程未改变。
VideoClaw 浏览器加载和 API 地址前缀验证通过，JavaScript 异常数为 0；进程内测试身份联调主站前端、后端代理均返回 200，非 AI 身份返回 403。小哈首次页面渲染异常数为 0；广告容器检测到 ODBC Driver 17。
补货测试已补充真实的 AI 部门测试身份，14 项通过，其中包含“其他部门即便有功能权限也不能进入 AI 部门入口”的反向测试；没有放宽生产权限。新增 Docker 与 VideoClaw 流式代理测试 6 项通过，小哈稳定性相关测试 8 项通过。
无限画布现有测试另有 2 项功能枚举断言不包含已存在的 product_retouch / product_retouch_local，未在本次部署中更改功能范围或删除功能来迎合旧断言。
尚未验收真实用户的飞书回调登录、全部业务读写及收费模型实际生成；健康和页面加载不代表这些流程全部可用。
VideoClaw 子模块前端含本次 API/媒体地址适配代码；发布时需要同步保存子模块修改并更新主仓库引用，不能只推送主仓库 Docker 配置。本次未自动提交代码，也未覆盖原有子模块改动。

网络行为参考：[Docker Desktop 官方网络说明](https://docs.docker.com/desktop/features/networking/)。
