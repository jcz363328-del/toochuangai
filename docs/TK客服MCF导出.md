# TK 客服 MCF 导出

## 使用方式

在 TK 客服页面设置日期、店铺、导入人或发样订单号筛选条件，点击“MCF导出”。导出覆盖全部符合条件的记录，不受当前分页限制。原“导出”按钮保留原格式。

接口：`GET /api/tk_customer_service/export?format=mcf`，沿用客服权限校验和既有筛选参数。

## 模板与字段

按提供的截图输出以下 13 列，保留模板的英文表头及顺序（包括 `Distrct` 拼写）：

| 列名 | 来源或规则 |
| --- | --- |
| * External Order ID | 发样订单号 FaYangDingDanHao |
| * Consumer Name | 既有地址解析得到的收件人 |
| * Contact Phone | 既有地址解析及规范化得到的电话 |
| * E-mail | PinPaiDianPu：按 Dian 匹配店铺的 BangDingYouXiang |
| * Postcode | 既有地址解析得到的邮编 |
| * Region | 国家二字码，沿用原导出默认 US 的逻辑 |
| * State or Region | 既有地址解析得到的州/省 |
| Distrct or County | 沿用原导出的区/县，目前为空 |
| * City | 既有地址解析得到的城市 |
| * Address line 1 | 既有地址解析得到的地址1 |
| Address line 2 | 沿用原导出的地址2，目前为空 |
| * Goods ID | KuCun3.HuoPinID，优先按 SKU + Dian 匹配；没有同店铺结果时，仅使用该 SKU 唯一的货品 ID |
| * Goods quantity | 1，沿用原客服每条记录的导出数量 |

批量查询货品及店铺映射并去重，避免库存表多条记录导致订单行数增加。同店铺命中多个不同货品 ID，或 SKU 回退结果不唯一时，不任意选取。

## 异常与 Excel 格式

“全部数据”工作表保留所有匹配的客服记录。“导出错误列表”记录原地址校验错误，以及货品 ID、绑定邮箱缺失或不唯一的问题；相应映射字段留空。上传 MCF 前应先检查并修正错误列表。

订单号、电话、邮编和 Goods ID 以文本保存，避免长编号精度丢失和邮编前导零丢失；数量保持数值。模板使用深色表头、筛选和冻结首行。

## 验证与部署

验证命令：

```powershell
python -m unittest tests.test_tk_customer_service_mcf tests.test_tk_customer_service_pagination -q
```

12 项测试通过，覆盖同店铺货品匹配、邮箱映射、缺失映射保留订单并报告错误、导出筛选参数传递、模板列顺序及长编号/邮编文本保真。

2026-11-27 已更新运行容器 toochuangai-single-app-1 中的 app.py、客服路由和客服模板，并重启 Supervisor 的 web 进程；容器健康检查返回 all services healthy。部署镜像 toochuangai-single:latest 同步包含这三个文件，后续完整源码构建也包含此功能。

验证范围不包含向第三方 MCF 平台实际上传或创建履约订单。
