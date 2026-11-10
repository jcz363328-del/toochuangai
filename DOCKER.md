# 单容器、单端口部署

## 当前运行方式

- 本项目运行在一个容器 `toochuangai-single-app-1`，只对外发布 **8000**。
- `/` 主站；`/lashforge/` 小哈；`/infinite-canvas/` 画布；`/ai/video-claw/` 视频工具；经营分析、广告诊断从主站进入。
- Nginx 转发页面、上传、WebSocket 和流式接口。VideoClaw 的前后端接口仍经过主站权限检查，不直接公开内部端口。
- Supervisor 管理主站、小哈、静态/API 服务、VideoClaw 前后端、经营分析、广告诊断、定时任务和 Nginx；各子进程异常会重启。
- 主站、小哈、VideoClaw 分别使用 `/opt/web`、`/opt/xiaoha`、`/opt/video` Python 环境，避免 SDK 版本冲突。
- 内部进程仍使用不同监听端口；“一个端口”指对外只发布 8000，不是让多个程序争用同一个内部端口。

## 启动、查看与更新

在项目根目录的 PowerShell 中运行：

```powershell
docker compose --env-file .env.single up -d --no-build --wait
docker compose --env-file .env.single ps
docker compose --env-file .env.single exec -T app supervisorctl status
docker compose --env-file .env.single exec -T app python /app/docker/healthcheck.py
docker compose --env-file .env.single logs --tail 100 app
```

需要重建镜像时先构建组件镜像，再打包成一个运行镜像；构建过程不会启动七个运行容器：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File docker/build_single.ps1
docker compose --env-file .env.single up -d --no-build --force-recreate --wait
```

`docker compose --env-file .env.single stop app` 停止整个系统。不要使用 `down -v` 或 Docker Desktop 的删除数据卷选项。
镜像和主机绑定目录分离。已有数据不应通过删除卷来“刷新”。Docker Desktop 启动后，容器按 `unless-stopped` 策略恢复；不要同时重新启用旧 Windows 服务。

## 配置与现有数据

- `.env.single` 是当前运行配置，已被 Git 和镜像构建排除；`.env` 原配置未修改。不要提交、发送密钥或公开完整的 inspect/config 输出。
- 当前正式配置挂载原 `D:/tuchuangai` 素材目录，以及项目中现有知识库、Listing、经营分析、导出、VideoClaw 任务/结果、广告数据目录，没有用空测试卷替换正式数据。
- VideoClaw 配置：`docker-data/production-videoclaw/config.yaml`；广告配置：`docker-data/production-ads/ads_monitor_config.json`。初始从原配置复制，不将密钥打进镜像。
- 原 SQL Server 保持不变。`DB_*` 为主站连接参数，`TK_SQL_*` 为原广告脚本使用的同一数据库别名；数据库在本机时容器地址使用 `host.docker.internal`，不能用容器自己的 localhost。
- `DOCKER_PUBLIC_URL`、`FEISHU_PRODUCTION_DOMAIN` 保留原访问地址；小哈、素材和画布地址使用同一入口，不再向浏览器生成 8501/8502 地址。
- 本机访问 `http://localhost:8000`。其他电脑使用原服务器地址；如果调整公开域名，需同步公开地址、飞书回调白名单、HTTPS/反向代理配置。
- 正式数据是读写绑定，不是备份。数据库和素材目录仍需单独备份。
- 历史日报卡片索引已从原项目复制到持久化存储并验证哈希；原文件保留。后续消息更新写入存储目录，手工回滚前应在两套服务都停止时备份、核对这类新增运行状态。

## 定时任务

确认旧任务已停止后，正式配置启用 `TC_BACKGROUND_JOBS=1` 和 `TC_SCHEDULED_JOBS=1`。
广告快照按原 Windows 配置每小时第 55 分钟刷新；广告日监控每天北京时间 09:00 执行，参数沿用原任务。启动容器不会立即重复执行当天任务；同类采集尚未结束时不叠加启动。
原 `TuChuangAI-Main`、`SellfoxAdDiagnosticSnapshotHourly`、`SellfoxAdsMonitorDaily` 在切换时停用，状态记录位于 `docker-data/cutover-task-state.json`。旧小哈守护进程也必须停止，不能只杀掉它的子进程。

## 新电脑部署

先取得子模块源码：`git submodule update --init --recursive`。VideoClaw 子模块包含本次 API/媒体地址适配，发布时需要同步保存子模块修改。
复制 `.env.single.example` 为 `.env.single`，填写数据库、随机会话密钥、飞书和模型平台密钥，再运行构建脚本和启动命令。
新电脑默认配置使用独立数据目录/数据卷，不会自动取得这台电脑的历史资料；应先恢复数据库和文件备份，再配置 `DOCKER_*_PATH` 挂载。
测试时保持两项定时任务开关为 0，防止与正式系统重复采集或发消息。

## 切换与回滚

切换步骤是：先在 18081 隔离验收，正式目录只读核验；停止旧 Docker 测试环境、Windows 服务和旧采集任务后，才将正式目录以读写方式接入 8000。
`docker/cutover.ps1` 对原端口和进程路径做身份检查，并在新服务健康失败时先停止新容器，再恢复 Windows 服务。它只用于从原 Windows 服务迁入，不要对已经运行的单容器重复执行。
原多容器配置保留在 `compose.multi.yaml`，历史说明在 `DOCKER_MULTI.md`。原临时配置备份为 `.env.single.before-cutover`，所有配置备份也包含密钥，必须保密。

手工回滚必须先确认新容器完全停止，不能让 Windows 与容器同时写正式目录：

```powershell
docker compose --env-file .env.single stop app
```

然后按 `docker-data/cutover-task-state.json` 恢复原计划任务启用状态，并通过 `start_tuchuangai.ps1` 恢复主站、通过 `图片/xiaoha_watchdog.ps1` 恢复小哈。只启用一套采集和提醒任务。

## 验收范围

聚合健康检查覆盖全部 HTTP 服务和 Supervisor 子进程；验收包含小哈 WebSocket、同端口画布、VideoClaw 流式代理、依赖隔离、部门权限及原数据目录存在性。
本机已完成切换：单容器在 8000 健康运行，原三项 Windows 计划任务停用，原小哈守护进程已停止；正式域名 Origin 的 WebSocket 握手也已通过。部署测试 9 项通过。
补货 14 项、部署相关测试和导航集成测试通过。真实用户飞书回调及收费模型生成没有通过伪造账号或付费调用来代替验收。
现有画布旧测试有 2 项功能枚举断言未包含已有的商品精修功能，未为迎合旧断言删除功能；原有 npm 审计问题也未自动执行破坏性升级。

参考：[Docker 多进程管理](https://docs.docker.com/engine/containers/multi-service_container/)、[Nginx WebSocket 转发](https://nginx.org/en/docs/http/websocket.html)。
