# 开发步骤与最佳实践

## 开发步骤详解

### 步骤1：创建目录结构

```bash
# 创建频道目录
mkdir -p apps/{channel_name}/{images,prompts}
mkdir -p apps/{channel_name}/images/{contacts,system}

# 创建必要文件
touch apps/{channel_name}/__init__.py
touch apps/{channel_name}/config.yaml
touch apps/{channel_name}/handler.py
touch apps/{channel_name}/workflows.py
touch apps/{channel_name}/workflow_executor.py
touch apps/{channel_name}/images/aliases.yaml
touch apps/{channel_name}/prompts/planner.txt
```

### 步骤2：配置 config.yaml

```yaml
# apps/{channel}/config.yaml
name: {channel}
display_name: {频道显示名称}
package: com.example.app
keywords:
  - 关键词1
  - 关键词2
  - 关键词3
description: 频道描述
```

### 步骤3：定义界面状态枚举和工作流

参考 `apps/wechat/workflows.py`，定义：

1. **界面状态枚举** (`{Channel}Screen`)
2. **界面检测参考图映射** (`SCREEN_DETECT_REFS`)
3. **导航步骤** (`NAV_TO_HOME`)
4. **工作流定义** (`WORKFLOW_*`)
5. **简单任务模式匹配规则** (`SIMPLE_TASK_PATTERNS`)

### 步骤4：实现 Handler

参考 `apps/wechat/handler.py`，实现：

- `set_task_runner()` - 设置 TaskRunner 引用
- `execute_task_with_workflow()` - 工作流执行入口
- `select_workflow_with_llm()` - LLM 工作流选择
- `get_planner_prompt()` - 规划器提示词增强

### 步骤5：实现工作流执行器

参考 `apps/wechat/workflow_executor.py`，实现：

- `_ensure_app_running()` - 确保应用运行
- `_ensure_at_home_screen()` - 确保在首页
- `detect_screen()` - 界面检测
- `navigate_to_home()` - 导航回首页
- `execute_workflow()` - 执行工作流
- `_execute_step()` - 执行单个步骤

### 步骤6：准备参考图

1. 截取应用界面关键元素
2. 按命名规范存放（`{channel}_{element}.png`）
3. 为多设备准备变体版本（`{channel}_{element}_v1.png`）
4. 配置 `aliases.yaml` 中文别名

### 步骤7：编写规划器提示词

参考 `apps/wechat/prompts/planner.txt`，编写应用专用的 AI 规划器提示词。

### 步骤8：测试验证

```bash
python test_planner.py --channel {channel_name} --task "测试任务"
```

---

## 最佳实践

### 1. 工作流设计

- **原子化步骤**：每个 NavStep 只做一件事
- **明确参数**：清晰定义必需/可选参数
- **支持子工作流**：复杂流程拆分为可复用的子流程
- **配置期望界面**：每步操作后检查是否到达预期界面

### 2. 参考图质量

- 截取清晰的界面元素
- 避免包含动态内容（时间、未读数）
- 保持适当边距
- 为不同设备准备变体

### 3. 提示词优化

- 提供清晰的操作说明
- 列出完整的参考图清单，区分用途
- 给出典型示例
- 说明常见错误和处理方式

### 4. 错误恢复

- 配置 fallback 方案
- 实现智能导航回退
- 支持 AI 辅助恢复

### 5. 渐进式开发

1. 先用最简 Handler 验证基本功能
2. 收集常见任务场景
3. 逐步添加预设工作流
4. 持续优化参考图库和提示词

---

## 常见问题

### Q: 简单任务和复杂任务的边界在哪里？

- **简单任务**：单一动作，无顺序连接词（"然后"、"再"等），可直接规则匹配
- **复杂任务**：包含连接词或多个动作词，需要 LLM 分析和选择工作流

**判断逻辑**：
```python
COMPLEX_TASK_INDICATORS = ["然后", "再", "接着", "之后", "完成后", "并且", "同时", "顺便", "截图", "保存"]

def is_complex_task(task):
    # 包含复合任务指示词
    if any(indicator in task for indicator in COMPLEX_TASK_INDICATORS):
        return True
    # 包含多个动作词
    action_words = ["发消息", "发朋友圈", "搜索", "加好友", "打开", "点击", "截图"]
    action_count = sum(1 for w in action_words if w in task)
    return action_count >= 2
```

### Q: 为什么要区分界面判断参考图和点击操作参考图？

- **界面判断参考图**（`system/` 目录）：用于验证当前在哪个页面，通常是页面的整体特征
- **点击操作参考图**（根目录）：用于定位可点击的具体元素，需要精确定位中心点

**混用风险**：
- 用页面验证图去点击 → 位置不准
- 用按钮图去验证页面 → 不可靠

### Q: 工作流执行中途失败如何恢复？

1. `_try_recover()` 方法会尝试恢复
2. 返回已知状态（如首页）
3. 重新执行工作流或回退到 AI 规划

**恢复策略**：
```python
def _try_recover(self, failed_step, params):
    # 1. 检测当前界面
    current = self.detect_screen()

    # 2. 如果在未知界面，尝试回首页
    if current == Screen.UNKNOWN:
        return self.navigate_to_home()

    # 3. 根据失败步骤决定恢复策略
    if failed_step.action == "tap":
        # 重新检测目标
        return self._retry_locate(failed_step.target)

    return False
```

### Q: 参考图匹配不准确怎么办？

1. **检查参考图质量和边距**
2. **添加多个变体版本**（`_v1`, `_v2`）
3. **调整 HybridLocator 的置信度阈值**
4. **配置 fallback 回退方案**

### Q: 如何处理应用版本更新导致的界面变化？

1. **使用变体图**：为新版本添加 `_v2`, `_v3` 变体
2. **备用参考图**：配置 `SCREEN_DETECT_REFS_FALLBACK`
3. **AI 回退**：界面检测失败时使用 AI 辅助识别

### Q: 工作流参数如何从任务描述中提取？

使用正则表达式模式匹配：

```python
def parse_task_params(task, param_hints):
    params = {}

    # 解析联系人
    if "contact" in param_hints:
        match = re.search(r'给\s*([^\s:：，。\d]+?)(?:[：:]|发|说|$)', task)
        if match:
            params["contact"] = match.group(1)

    # 解析消息内容
    if "message" in param_hints:
        match = re.search(r'[:：]\s*(.+)', task)
        if match:
            params["message"] = match.group(1).strip()

    return params
```

### Q: 如何添加新的工作流？

1. 在 `workflows.py` 中定义新的 `Workflow` 对象
2. 添加到 `WORKFLOWS` 字典
3. 在 `SIMPLE_TASK_PATTERNS` 中添加匹配规则（如果是简单任务）
4. 更新 `get_planner_prompt()` 中的工作流描述

### Q: 如何调试工作流执行？

1. **启用详细日志**：
   ```python
   handler.set_logger(print)  # 输出到控制台
   ```

2. **单步执行**：
   ```python
   executor._execute_step(step, params)
   ```

3. **界面检测**：
   ```python
   screen = executor.detect_screen()
   print(f"当前界面: {screen.value}")
   ```

---

## 检查清单

新频道开发完成后，确认以下项目：

- [ ] `config.yaml` 配置正确
- [ ] 界面状态枚举覆盖主要页面
- [ ] 界面检测参考图映射完整
- [ ] 至少有一个基本工作流
- [ ] 简单任务模式匹配规则有效
- [ ] Handler 的 `execute_task_with_workflow()` 正常工作
- [ ] `get_planner_prompt()` 返回有效提示词
- [ ] 参考图命名规范
- [ ] `aliases.yaml` 配置中文别名
- [ ] 测试用例覆盖主要场景
