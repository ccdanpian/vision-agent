# 无效输入处理机制

## 概述

为了提升用户体验和系统稳定性，任务分类器增加了 `invalid` 类型，用于识别和处理无效输入。

---

## 什么是无效输入？

### 常见场景

| 场景 | 示例 | 说明 |
|------|------|------|
| **空白输入** | `""`, `"   "`, `"\n"` | 用户误点回车 |
| **无意义字符** | `"aaa"`, `"123"`, `"!!!"` | 随机敲击键盘 |
| **误触输入** | `"s"`, `"ss"`, `"、、、"` | 输入未完成就发送 |
| **不清楚的指令** | `"帮我"`, `"那个"`, `"嗯"` | 意图不明确 |

---

## 工作流程

### 1. LLM 识别

**System Prompt**：
```
你是一个解析器，只输出JSON。字段包含：type(send_msg/post_moment_only_text/others/invalid), recipient, content

type 说明：
- send_msg: 发送消息给联系人
- post_moment_only_text: 发布纯文字朋友圈
- others: 其他复杂任务（多步骤任务）
- invalid: 无效输入（空白、无意义、误触、错误输入等）

invalid 类型示例：
- 空白输入、只有空格/换行
- 无意义的字符（如：aaa、123、！！！）
- 明显的误触（如：s、ss、、、等）
- 不清楚的指令
```

**LLM 响应示例**：
```json
{
  "type": "invalid",
  "recipient": "",
  "content": ""
}
```

### 2. 分类器处理

**代码位置**：`ai/task_classifier.py:343-346`

```python
if task_type == "invalid":
    # 无效输入，标记为复杂任务（在 handler 中会被特殊处理）
    self._log("LLM判断：无效输入")
    return TaskType.COMPLEX
```

**说明**：
- `invalid` 类型被标记为 `TaskType.COMPLEX`
- 但 `parsed_data` 中保留了 `type: "invalid"`
- Handler 会在执行前拦截

### 3. Handler 拦截

**代码位置**：`apps/wechat/handler.py:194-204`

```python
# 1.1 检查是否为无效输入
if parsed_data and parsed_data.get("type") == "invalid":
    self._log(f"检测到无效输入: {task}")
    return {
        "success": False,
        "message": "无效的输入指令。请输入有效的任务描述，例如：\n"
                  "- 给张三发消息说你好\n"
                  "- 发朋友圈今天天气真好\n"
                  "- SS快速模式：ss:消息:张三:你好",
        "error_type": "invalid_input"
    }
```

**返回给用户**：
```json
{
  "success": false,
  "message": "无效的输入指令。请输入有效的任务描述，例如：...",
  "error_type": "invalid_input"
}
```

---

## 完整执行流程

### 无效输入流程

```
用户输入: "aaa" (随机字符)
    ↓
classify_and_parse()
    ↓
LLM 识别: {type: "invalid", recipient: "", content: ""}
    ↓
返回: (TaskType.COMPLEX, parsed_data)
    ↓
Handler 检查 parsed_data.type == "invalid"
    ↓
提前返回错误信息 ❌
    ↓
不执行任何工作流，不浪费资源
```

### 有效输入流程（对比）

```
用户输入: "给张三发消息说你好"
    ↓
classify_and_parse()
    ↓
LLM 识别: {type: "send_msg", recipient: "张三", content: "你好"}
    ↓
返回: (TaskType.SIMPLE, parsed_data)
    ↓
Handler 检查 parsed_data.type != "invalid"
    ↓
继续执行工作流 ✅
```

---

## 测试验证

### 运行测试

```bash
cd /home/lighthouse/app/vision-agent
python test_invalid_input.py
```

### 测试用例

**无效输入**（应该被识别为 invalid）：
```python
[
    "",           # 空字符串
    "   ",        # 空格
    "aaa",        # 无意义字符
    "123",        # 纯数字
    "!!!",        # 标点符号
    "s",          # 单字符
    "ss",         # 不完整的 SS 模式
    "帮我",       # 不清楚的指令
    "嗯",         # 语气词
]
```

**有效输入**（不应该被识别为 invalid）：
```python
[
    "给张三发消息说你好",
    "发朋友圈今天天气真好",
    "ss:消息:张三:你好",
]
```

### 预期输出

```
【无效输入测试】
1. 输入: ''
   [TaskClassifier] LLM判断：无效输入
   ✓ 正确识别为 invalid

2. 输入: 'aaa'
   [TaskClassifier] LLM判断：无效输入
   ✓ 正确识别为 invalid

无效输入识别率: 9/9 (100%)

【有效输入测试】
1. 输入: 给张三发消息说你好
   ✓ 正确识别为有效输入 (type=send_msg)

有效输入识别率: 3/3 (100%)
```

---

## 优势

### 1. 提升用户体验

**优化前**：
```
用户输入: "aaa"
    ↓
系统尝试匹配工作流
    ↓
匹配失败
    ↓
调用 LLM Planner 分析
    ↓
Planner 无法理解
    ↓
返回: "无法理解任务"
```
**耗时**: ~2-3秒
**成本**: 调用了 Planner LLM

**优化后**：
```
用户输入: "aaa"
    ↓
LLM 分类器识别为 invalid
    ↓
Handler 提前拦截
    ↓
返回: "无效的输入指令。请输入..."
```
**耗时**: ~500ms（只调用分类器）
**成本**: 只调用分类器 LLM

### 2. 节省资源

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| **LLM 调用次数** | 2次（分类 + 规划） | 1次（分类） |
| **执行时间** | 2-3秒 | ~500ms |
| **API 成本** | 💰💰 | 💰 |

### 3. 更友好的提示

**优化前**：
```
"无法理解任务"
```

**优化后**：
```
无效的输入指令。请输入有效的任务描述，例如：
- 给张三发消息说你好
- 发朋友圈今天天气真好
- SS快速模式：ss:消息:张三:你好
```

---

## 边界情况

### Q: SS 模式格式错误会被识别为 invalid 吗？

**A**: 不会。SS 模式有自己的容错机制。

```
输入: "ss:未知类型:参数"
    ↓
检测到 SS 模式
    ↓
SS 解析失败（未知类型）
    ↓
降级到 LLM 模式
    ↓
LLM 可能识别为 invalid 或尝试理解
```

### Q: 简短但有意义的输入会被误判吗？

**A**: 不会。LLM 能理解简短指令。

```
输入: "发"
    ↓
LLM 分析：太简短，意图不明确
    ↓
识别为 invalid ✓

输入: "发消息"
    ↓
LLM 分析：意图明确，但缺少参数
    ↓
识别为 others（复杂任务）
    ↓
进入 LLM Planner 分析
```

### Q: 如果 LLM 误判怎么办？

**A**: 用户可以重新输入，或使用 SS 快速模式绕过。

```
# 如果被误判为 invalid
给张三发消息说你好  # 重新输入

# 或使用 SS 快速模式（100%不会误判）
ss:消息:张三:你好
```

---

## 配置选项

### 是否启用 invalid 检测？

**默认启用**，无需配置。

如果需要禁用（不推荐），可以修改 `handler.py`：

```python
# 注释掉 invalid 检查
# if parsed_data and parsed_data.get("type") == "invalid":
#     return {...}
```

### 自定义错误消息

修改 `apps/wechat/handler.py:199-202`：

```python
"message": "您的自定义错误消息",
```

---

## 监控建议

### 记录 invalid 输入统计

```python
# 在 handler.py 中添加
if parsed_data and parsed_data.get("type") == "invalid":
    # 记录到日志或数据库
    log_invalid_input(task, user_id)
    return {...}
```

### 分析 invalid 模式

定期分析被标记为 invalid 的输入，可以：
1. 发现用户常见误操作
2. 优化提示信息
3. 改进 LLM prompt

---

## 总结

| 项目 | 说明 |
|------|------|
| **触发条件** | LLM 识别为 `type: "invalid"` |
| **处理位置** | `handler.py:194-204` |
| **返回结果** | `{success: False, error_type: "invalid_input"}` |
| **优势** | 节省资源，提升体验，友好提示 |
| **测试** | `python test_invalid_input.py` |

**核心价值**：
- ✅ 提前拦截无效输入
- ✅ 节省 LLM API 成本
- ✅ 提供友好的错误提示
- ✅ 引导用户正确使用
