# 经营分析

本地 ECharts 经营分析平台，支持 SQL Server 实时查询、60 秒自动刷新、参数化 SQL、公式追溯与 Excel 快照降级。

## 启动

```powershell
Copy-Item .env.example .env.local
# 在 .env.local 填写 SALES_DB_SERVER / DATABASE / USER / PASSWORD
npm install
npm run dev -- --port 4310
```

打开 <http://localhost:4310/>。网页端口为 `4310`，仅监听本机的数据库 API 端口为 `4311`。

数据库未配置或暂时不可用时，页面会明确显示“快照/缓存”，并继续使用 `app/data/workbook-data.json`。每个核心 KPI 的 `fx` 可查看公式、输入值、数据口径和计算时间。

请使用单独的只读 SQL Server 账号；不要复用 Excel VBA 中的旧明文凭据。
