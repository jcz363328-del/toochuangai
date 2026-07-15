from typing import Any                                                                                  # 导入通用类型，供公共函数接收任意输入


MOBILE_KEYWORDS = (                                                                                     # 定义默认的移动端识别关键词
    "iphone",                                                                                           # 识别 iPhone 设备
    "ipad",                                                                                             # 识别 iPad 设备
    "android",                                                                                          # 识别 Android 设备
    "mobile",                                                                                           # 识别通用 Mobile 标记
    "harmony",                                                                                          # 识别 HarmonyOS 设备
    "micromessenger",                                                                                   # 识别微信内置浏览器
)                                                                                                       # 结束移动端关键词定义


def safe_print(*args: Any, **kwargs: Any) -> None:                                                      # 作用：安全打印任意参数；输入打印参数；无返回值
    try:                                                                                                # 优先使用当前控制台正常输出
        print(*args, **kwargs)                                                                          # 按调用方提供的格式打印内容
    except UnicodeEncodeError:                                                                          # 捕获控制台不支持中文或特殊字符的情况
        try:                                                                                            # 尝试转换为 ASCII 安全文本后再次输出
            safe_args = [                                                                               # 创建转换后的安全参数列表
                str(arg)                                                                                # 先把当前参数转换为字符串
                .encode("ascii", errors="backslashreplace")                                             # 把特殊字符转换为可显示的转义形式
                .decode("ascii")                                                                        # 把转换结果还原为普通字符串
                for arg in args                                                                         # 依次处理所有位置参数
            ]                                                                                           # 完成安全参数列表构建
            print(*safe_args, **kwargs)                                                                 # 使用安全参数重新打印
        except Exception:                                                                               # 捕获降级打印过程中的异常
            pass                                                                                        # 打印失败时保持业务流程继续运行
    except Exception:                                                                                   # 捕获其他不可预期的打印异常
        pass                                                                                            # 打印失败时保持业务流程继续运行


def escape_sql_literal(                                                                                 # 作用：转义 SQL 字面量；输入任意值；返回安全字符串
    value: Any,                                                                                         # 接收需要写入 SQL 字符串的原始值
    escape_percent: bool = True,                                                                        # 控制是否同时转义 pytds 使用的百分号
) -> str:                                                                                               # 返回完成引号和百分号处理的字符串
    text = "" if value is None else str(value)                                                          # 把空值转为空字符串，其余值统一转为文本
    text = text.replace("'", "''")                                                                      # 把单引号替换为 SQL 字面量中的双单引号
    if escape_percent:                                                                                  # 根据参数决定是否处理百分号
        return text.replace("%", "%%")                                                                  # 转义百分号并返回 pytds 可用文本
    return text                                                                                         # 不处理百分号时直接返回引号转义结果


def is_mobile_user_agent(                                                                               # 作用：判断请求是否来自移动端；输入 UA 和关键词；返回布尔值
    user_agent: Any,                                                                                    # 接收浏览器 User-Agent 原始值
    keywords: tuple[str, ...] = MOBILE_KEYWORDS,                                                        # 允许调用方传入自定义识别关键词
) -> bool:                                                                                              # 命中任一关键词返回 True，否则返回 False
    text = str(user_agent or "").lower()                                                                # 把 User-Agent 转为便于比较的小写文本
    for keyword in keywords:                                                                            # 依次检查所有移动端关键词
        if str(keyword).lower() in text:                                                                # 判断当前关键词是否出现在 User-Agent 中
            return True                                                                                 # 命中关键词后立即确认是移动端
    return False                                                                                        # 全部关键词未命中时判定为非移动端


def preview_text(                                                                                       # 作用：生成限定长度的文本预览；输入文本和规则；返回预览字符串
    value: Any,                                                                                         # 接收需要生成预览的任意值
    limit: int = 800,                                                                                   # 设置预览正文允许保留的最大字符数
    suffix: str = "...(truncated)",                                                                     # 设置文本被截断后追加的提示内容
    strip: bool = False,                                                                                # 控制是否先去除文本首尾空白
) -> str:                                                                                               # 返回原文本或完成截断后的预览文本
    text = str(value or "")                                                                             # 把空值转为空字符串，其余值统一转为文本
    if strip:                                                                                           # 根据参数决定是否清理首尾空白
        text = text.strip()                                                                             # 去除文本首尾的空格和换行
    size = max(0, int(limit))                                                                           # 把长度限制规范为不小于零的整数
    if len(text) <= size:                                                                               # 判断文本是否已经满足长度限制
        return text                                                                                     # 未超长时返回完整文本
    return text[:size] + str(suffix)                                                                    # 超长时截取正文并追加截断提示


def ai_chat_complete(                                                                                   # 作用：依次尝试多个 AI 模型；输入客户端和参数；返回首个有效回复
    client: Any,                                                                                        # 接收兼容 OpenAI 调用方式的客户端
    messages: Any,                                                                                      # 接收发送给模型的消息列表
    max_tokens: int,                                                                                    # 设置模型最多生成的令牌数量
    temperature: float,                                                                                 # 设置模型回复的随机程度
    model_candidates: Any,                                                                              # 接收按优先级排列的候选模型
    stream: bool | None = None,                                                                         # 控制是否传递流式输出参数
) -> str:                                                                                               # 返回首个成功模型生成的非空文本
    last_error = None                                                                                   # 保存最近一次模型调用异常
    for model in model_candidates or ():                                                                # 按给定顺序逐个尝试候选模型
        try:                                                                                            # 开始执行当前模型调用
            params: dict[str, Any] = {                                                                  # 创建当前模型的请求参数
                "model": model,                                                                         # 指定当前候选模型
                "messages": messages,                                                                   # 传入对话消息
                "max_tokens": max_tokens,                                                               # 传入最大生成令牌数
                "temperature": temperature,                                                             # 传入回复随机程度
            }                                                                                           # 完成基础请求参数构建
            if stream is not None:                                                                      # 仅在调用方明确设置时传递流式参数
                params["stream"] = stream                                                               # 写入流式输出配置
            response = client.chat.completions.create(**params)                                         # 调用当前候选模型生成回复
            message = response.choices[0].message                                                       # 读取模型返回的第一条消息
            content = str(message.content or "").strip()                                                # 提取并清理模型回复正文
            if content:                                                                                 # 判断模型是否返回有效文本
                return content                                                                          # 立即返回第一个有效模型回复
        except Exception as exc:                                                                        # 捕获当前候选模型的调用异常
            last_error = exc                                                                            # 记录异常并继续尝试下一个模型
    if last_error is not None:                                                                          # 所有模型失败后检查是否记录了具体异常
        raise last_error                                                                                # 抛出最近异常供调用方定位原因
    raise RuntimeError("AI 调用失败")                                                                       # 没有候选模型时抛出统一错误
