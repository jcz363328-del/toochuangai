# 经营分析源码迁移说明

本源码包包含前端仪表盘、ECharts 图表、SQL Server 查询服务、实时公式、Excel 快照降级、测试和构建配置。真实数据库账号与密码不在包内。

## 独立运行

环境要求：Node.js `>= 22.13.0`。

```powershell
Copy-Item .env.example .env.local
# 在 .env.local 中填写 SALES_DB_SERVER / DATABASE / USER / PASSWORD
npm ci
npm run dev -- --port 4310
```

打开 <http://localhost:4310/>。网页端口默认为 `4310`，本机数据库 API 端口默认为 `4311`。

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:4311/api/health
```

生产构建先运行 `npm run build`。网页和数据库 API 是两个进程，部署时需同时运行 `npm run start` 与 `npm run start:api`，并确保目标环境把 `/api` 转发到 `127.0.0.1:4311`。

## 合并到现有项目

1. 将 `app/` 中的页面、组件、hooks、lib 和快照数据合入目标前端。
2. 将 `server/` 与 `scripts/dev.mjs` 合入目标项目，或把 `/api/dashboard` 接口改接目标项目自己的服务端。
3. 合并 `package.json` 中的 `echarts`、`mssql`、React、Vinext/Vite 等依赖。
4. 保留 `vite.config.ts` 的 `/api` 代理，或按目标项目端口调整代理地址。
5. 从 `.env.example` 新建目标环境变量文件；不要复制或提交原项目的 `.env.local`。
6. 运行 `npm run lint` 和 `npm test`，确认公式、三期口径和构建均正常。

SQL Server 只读账号需要能够查询当前 SQL 中使用的对象，包括 `v_MaoLiLv`、`v_PinPaiDianPu`、`v_ZhiXiao`、`ChuKu`、`v_FBAHuoJian`、`v_CengJi`、`ZiDian`、`XinPinWeiFaHuo` 和 `v_ShangXin`。

## 主要入口

- `app/DashboardClient.tsx`：经营分析主界面与交互。
- `app/lib/dashboard.ts`：店铺、部门和整体业绩汇总公式。
- `server/index.mjs`：本地 API 服务入口。
- `server/queries/catalog.mjs`：参数化 SQL 查询。
- `server/formulas/`：可追溯公式注册与计算。
- `tests/`：指标、数据整形和公式测试。
- `.openai/`、`build/`、`worker/`：构建与本地 Worker 配置；其中 `build/` 是源码目录，不是可删除的生成目录。

## 安全说明

- 源码包仅包含空白的 `.env.example`，不包含 `.env.local`。
- 建议为目标环境配置只读 SQL Server 账号。
- `app/data/workbook-data.json` 是断连时使用的当前业务快照；若源码包需要发给公司外部人员，请先替换为经过审核的脱敏样例数据。
- `node_modules`、构建产物、缓存、日志和本地工具目录均未打包，可通过 `npm ci` 恢复依赖。
