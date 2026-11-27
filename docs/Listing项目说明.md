# Listing 生成智能体完整交付包

交付日期：2026-08-07

## 已接入图创 AI 项目

本目录已作为 Flask Blueprint 接入项目，无需单独启动 Node 服务：

1. 启动项目现有的 Flask 服务。
2. 登录后从主控制台或 AI 模块页进入“Listing 生成智能体”。
3. 也可以直接打开 `/listing-agent/`。
4. 完整 ABA 排名看板地址为 `/listing-agent/aba-ranking/`，主控制台与 Listing 页面顶部均有入口。

后端会复用项目根目录 `.env` 中的 `SILICONFLOW_API_KEY`、`SILICONFLOW_BASE_URL`、`SILICONFLOW_MODEL` 和 `SILICONFLOW_TEXT_MODEL`。页面中保存的专用配置会写入已被 Git 忽略的 `code/.env.local`。

原始 Node 服务仍保留在 `code/server.js`，仅作为独立运行和交付参考。

本包包含 Listing 生成智能体的完整前后端代码、ABA 排名原始数据、结构化排名导出和三版示例 Listing。

## 目录

- `code/`：网页、交互逻辑、本地 Node 服务、图片识别及 AI Listing 生成接口。
- `data/`：ABA 四核心词排名原始看板，以及 JSON、CSV 两种结构化导出。
- `outputs/`：根据示例产品事实和包内 ABA 数据生成的三版 Listing，提供 JSON 和 Markdown。
- `tools/`：重新生成 ABA 导出及示例 Listing 的脚本。

## 启动

1. 进入 `code/`。
2. 将 `.env.example` 复制为 `.env.local`。
3. 在 `.env.local` 中填写自己的 `SILICONFLOW_API_KEY`。
4. 根据需要设置图片识别模型和 Listing 文本模型。
5. 运行 `node server.js`。
6. 打开 `http://127.0.0.1:5177/`。

环境变量：

- `SILICONFLOW_API_KEY`：硅基流动密钥，必填。
- `SILICONFLOW_MODEL`：图片识别模型。
- `SILICONFLOW_TEXT_MODEL`：Listing 文本模型；留空时复用图片模型。
- `SELLFOX_RANKING_FILE`：可选，覆盖包内默认 ABA 看板路径。
- `PORT`：本地端口，默认 `5177`。

## ABA 数据

数据周期：2026-06-28 至 2026-07-04。

结构化导出包含 4,571 条关键词及以下字段：

- 当前 ABA 排名与推算的上期排名。
- 排名环比和同比信号。
- 前三 ASIN 点击份额与转化份额。
- 前三 ASIN 和品牌信息。

## Listing 输出

`outputs/示例Listing_三版.md` 适合直接查看，`outputs/示例Listing_三版.json` 适合程序读取。示例文件使用本地规则生成，实际网页运行时会调用配置的硅基流动文本模型生成三版 Listing，并执行字符数、Search Terms 字节数、违禁词和未确认声明检查。

## 安全说明

交付包不包含 `.env.local`，也不包含任何真实 API 密钥。请勿把填写密钥后的环境文件提交到代码仓库或发送给他人。

## 重新生成导出

在交付包根目录执行：

```bash
node tools/build_exports.js
```

脚本会重新生成 `data/aba-ranking-export.json`、`data/aba-ranking-export.csv` 和 `outputs/` 下的三版示例 Listing。
