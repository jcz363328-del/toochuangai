# Listing Agent Studio

这是一个本地网页版 Listing 生成智能体原型。现在第一步已经可以通过本地服务接入硅基流动视觉模型，用上传的产品图片提取 `图片确认事实`、`需要确认` 和 `禁止推断`。

## 打开方式

只看原型页面时，可以直接用浏览器打开：

`web-listing-agent/index.html`

使用真实图片识别时，请用本地服务打开，避免把密钥放进浏览器代码：

```bash
cd web-listing-agent
SILICONFLOW_API_KEY="你的硅基流动密钥" node server.js
```

然后打开：

`http://127.0.0.1:5177`

页面里的“硅基流动配置”可以直接保存 API Key 和视觉模型；保存后重新点击“提取”即可。

默认视觉模型是 `Qwen/Qwen3-VL-8B-Instruct`。如果你要换成硅基流动里的其他模型，可以启动时增加：

```bash
SILICONFLOW_MODEL="你的模型名" SILICONFLOW_API_KEY="你的硅基流动密钥" node server.js
```

注意：图片识别模型必须支持图像输入。如果所选 Kimi 模型不支持 vision，多模态提取会失败，需要换成硅基流动支持图片理解的模型。

也可以把密钥放在本机的 `.env.local` 文件里，服务启动时会自动读取：

```bash
cp .env.example .env.local
```

然后把 `.env.local` 里的 `SILICONFLOW_API_KEY` 改成你的真实密钥，再运行：

```bash
node server.js
```

`.env.local` 已被忽略，不会作为项目文件提交。

## 已包含能力

- 产品事实输入：站点、品牌、产品类型、风格、长度、卷度、带型、根数、包含物、图片可见事实。
- 图片识别确认流：上传图片后先调用硅基流动提取事实，前端展示 `图片确认事实`、`需要确认`、`禁止推断`，用户确认后才进入下一步生成。
- MCP 数据摘要输入：T1/T2/T3 关键词、SellerSprite/ABA/竞品摘要、评论洞察。
- 个人 Skill 配置：Skill 名称、标题策略、语气、五点结构、禁用词、自定义规则。
- 本地保存 Skill：保存到浏览器 localStorage。
- 导出 Skill：导出为 Markdown。
- 一键生成：标题、Product Highlights、五点、描述、Image/A+ Plan、Search Terms、Alexa/Rufus Q&A、Review Guidance、A/B Test Plan。
- 自检：标题字符数、五点字符数、描述长度、Search Terms bytes、未确认声明、ASIN 风险和禁用词风险。

## 说明

当前 Listing 生成逻辑仍在浏览器内完成。图片识别已经接入本地服务接口，服务会读取环境变量中的硅基流动密钥并调用：

`https://api.siliconflow.cn/v1/chat/completions`

如果你已有自己的后端，也可以继续覆盖前端接口地址：

```js
window.LISTING_IMAGE_EXTRACTOR_ENDPOINT = "https://your-domain.com/api/extract-image";
```

接口返回建议格式：

```json
{
  "facts": [
    { "key": "lengths", "label": "Lengths", "value": "10-14mm", "source": "package text", "confidence": "high" }
  ],
  "needsConfirmation": ["Piece count needs confirmation."],
  "doNotInfer": ["Do not infer waterproof, hypoallergenic, wear-time or material claims from image only."]
}
```

后续如果要接入真实 AI 和 SellerSprite MCP，可以把 `app.js` 里的图片识别、数据策略和文案生成函数替换为后端 API 调用，同时保留当前页面作为操作台。
