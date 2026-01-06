# 工作流适配说明

## 当前状态

任务分类器已更新为新的提示词格式：
```python
system_prompt = "你是一个解析器，只输出JSON。字段包含：type(send_msg/post_moment_only_text/others), recipient, content"
```

输出格式：
```json
{
    "type": "send_msg",  // 或 post_moment_only_text, others
    "recipient": "张三",
    "content": "你好"
}
```

## 需要适配的地方

### 1. apps/wechat/handler.py - execute_task_with_workflow() 方法

**当前逻辑**：
```python
if is_complex_task(task):
    # 复杂任务 -> LLM选择工作流
    llm_result = self.select_workflow_with_llm(task)
else:
    # 简单任务 -> 规则匹配 + 正则解析参数
    match_result = self.match_workflow(task)
    params = parse_task_params(task, param_hints)  # 使用正则解析
```

**问题**：
- 当使用LLM分类器时，它已经解析出了`type`、`recipient`、`content`
- 但简单任务仍然使用正则表达式重新解析一次
- **重复解析，浪费资源**

**建议改进**：
```python
# 在判断简单/复杂时，同时获取LLM解析的数据
classifier = get_task_classifier()
task_type, parsed_data = classifier.classify_and_parse(task)

if task_type == TaskType.COMPLEX:
    # 复杂任务 -> LLM选择工作流
    llm_result = self.select_workflow_with_llm(task)
else:
    # 简单任务
    if parsed_data:
        # 如果LLM已经解析了数据，直接使用
        workflow_name = map_type_to_workflow(parsed_data["type"])
        params = map_parsed_data_to_params(parsed_data)
    else:
        # 使用正则匹配（兼容正则模式）
        match_result = self.match_workflow(task)
        params = parse_task_params(task, param_hints)
```

### 2. 需要添加的映射函数

#### 2.1 type -> workflow 映射

```python
def map_type_to_workflow(task_type: str) -> Optional[str]:
    """
    将LLM解析的type映射到工作流名称

    Args:
        task_type: send_msg / post_moment_only_text / others

    Returns:
        工作流名称
    """
    type_workflow_map = {
        "send_msg": "send_message",
        "post_moment_only_text": "post_moments",
    }
    return type_workflow_map.get(task_type)
```

#### 2.2 parsed_data -> params 映射

```python
def map_parsed_data_to_params(parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    将LLM解析的数据映射到工作流参数

    Args:
        parsed_data: {"type": "send_msg", "recipient": "张三", "content": "你好"}

    Returns:
        工作流参数字典
    """
    task_type = parsed_data.get("type")
    recipient = parsed_data.get("recipient", "")
    content = parsed_data.get("content", "")

    if task_type == "send_msg":
        return {
            "contact": recipient,
            "message": content
        }
    elif task_type == "post_moment_only_text":
        return {
            "content": content,
            "post_action": "long_press"  # 纯文字朋友圈
        }

    return {}
```

### 3. 建议的完整改造

**apps/wechat/handler.py 新增方法**：

```python
def map_type_to_workflow(self, task_type: str) -> Optional[str]:
    """将LLM解析的type映射到工作流名称"""
    type_workflow_map = {
        "send_msg": "send_message",
        "post_moment_only_text": "post_moments",
    }
    return type_workflow_map.get(task_type)

def map_parsed_data_to_params(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    """将LLM解析的数据映射到工作流参数"""
    task_type = parsed_data.get("type")
    recipient = parsed_data.get("recipient", "")
    content = parsed_data.get("content", "")

    if task_type == "send_msg":
        return {
            "contact": recipient,
            "message": content
        }
    elif task_type == "post_moment_only_text":
        return {
            "content": content,
            "post_action": "long_press"
        }

    return {}
```

**修改 execute_task_with_workflow() 方法**：

```python
def execute_task_with_workflow(self, task: str) -> Optional[Dict[str, Any]]:
    """
    尝试使用工作流执行任务

    流程：
    1. 使用分类器判断简单/复杂，同时获取LLM解析的数据
    2. 简单任务 -> 优先使用LLM解析的数据，回退到规则匹配
    3. 复杂任务 -> LLM选择工作流
    """
    workflow_name = None
    params = {}

    # 1. 使用分类器判断并获取解析数据
    from ai.task_classifier import get_task_classifier, TaskType
    classifier = get_task_classifier()
    task_type, parsed_data = classifier.classify_and_parse(task)

    if task_type == TaskType.COMPLEX:
        # 复杂任务 -> LLM选择工作流
        self._log(f"检测到复杂任务，使用 LLM 选择工作流")
        llm_result = self.select_workflow_with_llm(task)
        if llm_result:
            workflow_name = llm_result["workflow_name"]
            params = llm_result["params"]
            self._log(f"LLM 选择工作流: {workflow_name}, 参数: {params}")
    else:
        # 简单任务
        if parsed_data:
            # 优先使用LLM解析的数据
            workflow_name = self.map_type_to_workflow(parsed_data.get("type"))
            if workflow_name:
                params = self.map_parsed_data_to_params(parsed_data)
                self._log(f"使用LLM解析数据: workflow={workflow_name}, params={params}")

        # 如果LLM没有解析出数据，或者无法映射到工作流，使用规则匹配
        if not workflow_name:
            match_result = self.match_workflow(task)
            if match_result:
                workflow = match_result["workflow"]
                workflow_name = workflow.name
                param_hints = match_result["param_hints"]
                params = parse_task_params(task, param_hints)
                self._log(f"规则匹配工作流: {workflow_name}, 参数: {params}")

    # 后续检查和执行逻辑保持不变...
    if not workflow_name:
        self._log(f"未匹配到工作流: {task}")
        return None

    # 检查必需参数
    workflow = WORKFLOWS[workflow_name]
    missing = [p for p in workflow.required_params if p not in params]
    if missing:
        self._log(f"缺少必需参数: {missing}")
        return {
            "success": False,
            "message": f"无法从任务中解析出必需参数: {missing}",
            "workflow": workflow_name,
            "parsed_params": params,
            "missing_params": missing
        }

    # 执行工作流
    return self.execute_workflow(workflow_name, params)
```

## 优势

1. **避免重复解析**：LLM已经解析了参数，不需要再用正则解析一次
2. **提高准确性**：LLM的解析能力通常比正则更准确
3. **向后兼容**：正则模式仍然可用，不影响现有功能
4. **优雅降级**：如果LLM解析失败，自动回退到规则匹配

## 测试建议

```python
# 测试用例1：LLM模式 - 发消息
task = "给张三发消息说你好"
# 期望：使用LLM解析的数据，直接执行 send_message 工作流

# 测试用例2：LLM模式 - 发朋友圈
task = "发朋友圈今天天气真好"
# 期望：使用LLM解析的数据，执行 post_moments 工作流

# 测试用例3：正则模式 - 发消息
task = "给张三发消息说你好"
# 期望：使用规则匹配 + 正则解析参数

# 测试用例4：复杂任务
task = "给张三发消息说你好，然后截图发朋友圈"
# 期望：LLM判断为复杂任务，使用 select_workflow_with_llm
```

## 总结

主要需要修改的文件：
1. ✅ `ai/task_classifier.py` - 已添加 `classify_and_parse()` 方法
2. ⏳ `apps/wechat/handler.py` - 需要添加映射函数和修改 `execute_task_with_workflow()`
3. 📝 文档更新 - 说明新的工作流适配逻辑
