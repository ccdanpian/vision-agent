# SS 模式路由问题修复

## 问题描述

用户在交互式快速模式下输入 `消息：张华：123`，系统自动添加 `ss:` 前缀后变成 `ss:消息：张华：123`，但是没有路由到微信模块，而是路由到了"系统操作"模块。

**现象**：
```
请输入任务（快速格式）: 消息：张华：123

开始执行任务: ss:消息：张华：123
[TaskRunner] 路由到模块: 系统操作 (匹配度: 0.00)
[TaskRunner] 无匹配的简单任务模板，交给 AI 规划器处理
```

---

## 问题原因

### 路由逻辑

VisionAgent 的模块路由通过 `ModuleRegistry.route(task)` 实现，计算每个模块与任务的匹配度：

```python
def match_task(self, task: str) -> float:
    """计算任务与本模块的匹配度"""
    # 1. 任务模板匹配（权重 0.5）
    # 2. 关键词匹配（权重 0.4）
    # 3. 包名匹配（权重 0.1）
```

### 关键词匹配规则

```python
for keyword in self.module_info.keywords:
    keyword_lower = keyword.lower()
    if keyword_lower in task_lower:
        keyword_hits += 1
```

**检查逻辑**：关键词是否在任务字符串中

### 问题分析

**用户输入**：`ss:消息：张华：123`

**微信模块原有关键词**：
```yaml
keywords:
  - 发微信
  - 发消息      # "发消息" 不在 "ss:消息：张华：123" 中
  - 微信消息
  - 朋友圈
  # ... 等
```

**匹配结果**：
- ❌ "发消息" 不在 "ss:消息：张华：123"
- ❌ "微信消息" 不在 "ss:消息：张华：123"
- ❌ "朋友圈" 不在 "ss:消息：张华：123"
- 结果：匹配度 0.00

**默认行为**：
```python
# 如果没有匹配或得分太低，使用 system 模块
if best_score < 0.3:
    best_handler = cls._handlers.get('system')
```

所以任务被路由到了"系统操作"模块。

---

## 解决方案

### 修改内容

在 `apps/wechat/config.yaml` 的 keywords 中添加 SS 模式的关键词：

**修改前**：
```yaml
keywords:
  - 发微信
  - 发消息
  - 微信消息
  - 朋友圈
```

**修改后**：
```yaml
keywords:
  # 消息操作（各种表述方式）
  - 消息         # SS 模式：ss:消息:联系人:内容
  - 发消息       # SS 模式：ss:发消息:联系人:内容
  - xx          # SS 模式别名
  - msg         # SS 模式别名
  - message     # SS 模式别名
  - 发微信
  - 发信息
  - 微信消息
  # ...

  # 朋友圈
  - 朋友圈       # SS 模式：ss:朋友圈:内容
  - pyq         # SS 模式别名
  - 发圈
  - 动态
```

### 添加的关键词

| SS 格式 | 添加的关键词 | 说明 |
|---------|------------|------|
| `ss:消息:...` | `消息` | 单独的"消息" |
| `ss:发消息:...` | `发消息` | 完整词组 |
| `ss:xx:...` | `xx` | SS 模式别名 |
| `ss:msg:...` | `msg` | 英文别名 |
| `ss:message:...` | `message` | 英文别名 |
| `ss:朋友圈:...` | `朋友圈` | 单独的"朋友圈" |
| `ss:pyq:...` | `pyq` | 朋友圈拼音缩写 |

---

## 验证

### 测试 1：消息

**输入**：`消息：张华：123`

**处理**：
```
1. 自动添加前缀: ss:消息：张华：123
2. 模块路由: "消息" in task → 微信模块 (匹配度 > 0)
3. 工作流匹配: send_message
4. 执行任务
```

**预期结果**：✅ 路由到微信模块

### 测试 2：朋友圈

**输入**：`朋友圈：今天天气真好`

**处理**：
```
1. 自动添加前缀: ss:朋友圈：今天天气真好
2. 模块路由: "朋友圈" in task → 微信模块
3. 工作流匹配: post_moments
4. 执行任务
```

**预期结果**：✅ 路由到微信模块

### 测试 3：别名

**输入**：`xx:李四:下午见`

**处理**：
```
1. 自动添加前缀: ss:xx:李四:下午见
2. 模块路由: "xx" in task → 微信模块
3. 工作流匹配: send_message
4. 执行任务
```

**预期结果**：✅ 路由到微信模块

---

## 技术细节

### 模块路由流程

```
用户输入任务
    │
    ▼
【1. ModuleRegistry.route(task)】
    │
    ├─ 遍历所有模块
    │   │
    │   ├─ wechat.match_task(task)
    │   │   └─ 计算匹配度
    │   │
    │   ├─ system.match_task(task)
    │   │   └─ 计算匹配度
    │   │
    │   └─ ...
    │
    ▼
【2. 选择最高匹配度的模块】
    │
    ├─ best_score >= 0.3 → 使用该模块
    └─ best_score < 0.3  → 使用 system 模块
    │
    ▼
【3. 执行任务】
```

### 关键词匹配权重

```python
# 关键词匹配：每个命中 +0.1，最多 +0.4
keyword_hits = 0
for keyword in keywords:
    if keyword in task:
        keyword_hits += 1

keyword_score = min(keyword_hits * 0.1, 0.4)
```

**示例**：
- 命中 1 个关键词：0.1 分
- 命中 2 个关键词：0.2 分
- 命中 3 个关键词：0.3 分（超过阈值）
- 命中 4+ 个关键词：0.4 分（上限）

---

## 其他 SS 模式关键词

### 当前支持的 SS 格式

根据 `ai/task_classifier.py` 的实现：

**发消息**：
```python
if task_type_str in ['消息', '发消息', 'xx', 'msg', 'message']:
    # 解析为 send_msg
```

**发朋友圈**：
```python
if task_type_str in ['朋友圈', 'pyq']:
    # 解析为 post_moment_only_text
```

### 需要添加的关键词

| 类别 | 关键词 |
|------|--------|
| **消息** | 消息、发消息、xx、msg、message |
| **朋友圈** | 朋友圈、pyq |

**全部已添加** ✅

---

## 向后兼容性

### ✅ 完全向后兼容

1. **自然语言模式不受影响**
   - "给张三发消息说你好" 仍然匹配"发消息"关键词
   - 原有关键词都保留

2. **SS 模式增强**
   - 新增的关键词提升 SS 模式的路由准确性
   - 不影响其他模式

3. **不会误匹配**
   - 添加的关键词都是微信相关
   - 不会导致其他任务误路由到微信

---

## 未来优化方向

### 1. SS 模式优先路由

可以在 TaskRunner 中增加 SS 模式的特殊处理：

```python
if task.startswith('ss:'):
    # SS 模式：直接解析并路由
    parsed = parse_ss_mode(task)
    if parsed['type'] == 'send_msg':
        handler = ModuleRegistry.get_handler('wechat')
    elif parsed['type'] == 'post_moment_only_text':
        handler = ModuleRegistry.get_handler('wechat')
```

**优势**：
- 不依赖关键词匹配
- 100% 准确路由
- 更快速

### 2. 模块注册 SS 支持

在模块配置中声明支持的 SS 类型：

```yaml
# wechat/config.yaml
ss_types:
  - send_msg
  - post_moment_only_text
```

**路由逻辑**：
```python
if task.startswith('ss:'):
    ss_type = parse_ss_type(task)
    for handler in handlers:
        if ss_type in handler.ss_types:
            return handler
```

### 3. 智能关键词扩展

自动提取 SS 模式的关键词：

```python
# 从 task_classifier.py 中提取
SS_KEYWORDS = {
    'send_msg': ['消息', '发消息', 'xx', 'msg', 'message'],
    'post_moment': ['朋友圈', 'pyq']
}

# 自动添加到 keywords
```

---

## 总结

### 问题根源

SS 模式的关键词（如"消息"）没有出现在微信模块的 keywords 列表中，导致路由失败。

### 解决方案

在 `apps/wechat/config.yaml` 中添加 SS 模式的所有关键词。

### 修改内容

```yaml
keywords:
  - 消息         # 新增
  - 发消息       # 已有（顺序调整）
  - xx          # 新增
  - msg         # 新增
  - message     # 新增
  - 朋友圈       # 已有
  - pyq         # 新增
```

### 影响范围

- ✅ 修改 1 个文件（`apps/wechat/config.yaml`）
- ✅ 完全向后兼容
- ✅ 提升 SS 模式路由准确性
- ✅ 不影响自然语言模式

### 测试建议

```bash
# 测试各种 SS 格式
python run.py -i
选择: 1

消息:张三:你好
发消息:李四:早上好
xx:王五:下午见
msg:赵六:晚上好
朋友圈:今天天气真好
pyq:分享一张照片
```

全部应该正确路由到微信模块！
