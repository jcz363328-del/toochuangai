# 赛狐 TikTok + 自定义订单 API 测试导入

`sellfox_import.py` 从赛狐官方“多平台订单列表”接口读取 TikTok，以及截图中
“自定义”所对应的 `okaylove`、`Geeneiya` 两个店铺，只写入
`dbo.TK_dingdan_ceshi`。接口把这两个自定义店铺返回为 Shopify 平台 3，程序在
请求 TikTok（平台 6）和 Shopify（平台 3）后还会按店铺 ID/名称白名单过滤，
不会导入其他 Shopify 店铺。

脚本没有写正式表的开关，`dbo.TK_DingDan` 只用于复制和校验表结构。

## 首次配置

```powershell
& '.\.venv\Scripts\python.exe' '.\sellfox_import.py' --configure
```

API 密钥和数据库密码会使用当前 Windows 用户的 DPAPI 加密，保存在
`%LOCALAPPDATA%\SellfoxTK\config.dpapi`，不会写进 Python 文件或日志。

## 手动运行

双击 `手动导入测试订单.bat`，或运行：

```powershell
& '.\.venv\Scripts\python.exe' '.\sellfox_import.py' --once `
  --date-type purchase --lookback-days 7
```

默认按 `purchase`（订购时间）导入今天及前 6 天，共 7 个自然日。小批量测试：

```powershell
& '.\.venv\Scripts\python.exe' '.\sellfox_import.py' --once `
  --date-type purchase --lookback-days 7 --max-orders 10
```

指定日期：

```powershell
& '.\.venv\Scripts\python.exe' '.\sellfox_import.py' --once `
  --date-type purchase --start-date 2026-07-26 --end-date 2026-07-27
```

只创建/检查同结构测试表：

```powershell
& '.\.venv\Scripts\python.exe' '.\sellfox_import.py' --ensure-table-only
```

日志位于 `%LOCALAPPDATA%\SellfoxTK\logs\sellfox_import.log`，不会记录密码、
Access Token、签名或完整请求地址。

## 每天 09:00 自动运行

Codex 中已创建并启用自动任务“赛狐订单 API 测试表导入”。它每天按本机时区
09:00 在本项目导入 TikTok + 指定自定义店铺最近 7 天订单，成功时不打扰，
失败时提醒。

## 当前 API 限制

- 多平台接口能返回部分买家邮箱，但目前不返回收件人、电话、邮编和详细地址；
  这些列保持空白。
- 接口的财务金额是订单级。单商品订单可以直接对应；多商品订单会按商品金额比例
  分摊并保证订单合计不变，相关行会在备注中标记。若以后赛狐开放逐商品财务接口，
  应替换这段分摊逻辑。
- 运单号不在当前接口响应中；物流商和发货时间可以写入，运单号保持空白。
- 为复刻原 VBA，英国金额仍按 `7.5 / 6.5` 转成美元，订单利润率不参与换算。
