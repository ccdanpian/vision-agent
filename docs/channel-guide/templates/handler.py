"""
apps/{channel}/handler.py
{Channel}频道处理器模板

使用说明：
1. 将 {Channel} 替换为频道名称（如 Douyin, Weibo）
2. 将 {channel} 替换为小写名称（如 douyin, weibo）
3. 导入实际的 workflows 模块
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any

from apps.base import DefaultHandler
from .workflows import (
    Workflow, {Channel}Screen, WORKFLOWS,
    match_workflow, is_complex_task, get_workflow_descriptions,
    SCREEN_DETECT_REFS
)
from .workflow_executor import WorkflowExecutor, parse_task_params


class Handler(DefaultHandler):
    """
    {Channel}专用处理器

    扩展功能：
    - 工作流执行（简单任务规则匹配，复杂任务 LLM 选择）
    - 界面状态检测
    - 智能导航
    """

    def __init__(self, module_dir: Path):
        super().__init__(module_dir)
        self._workflow_executor: Optional[WorkflowExecutor] = None
        self._task_runner = None

    def set_task_runner(self, task_runner):
        """设置 TaskRunner 引用（用于工作流执行）"""
        self._task_runner = task_runner
        self._workflow_executor = WorkflowExecutor(task_runner, self)
        if self._logger:
            self._workflow_executor.set_logger(self._logger)

    @property
    def workflow_executor(self) -> Optional[WorkflowExecutor]:
        """获取工作流执行器"""
        return self._workflow_executor

    def set_logger(self, logger_func):
        """设置日志函数"""
        super().set_logger(logger_func)
        if self._workflow_executor:
            self._workflow_executor.set_logger(logger_func)

    def get_available_workflows(self) -> Dict[str, str]:
        """获取可用的工作流列表"""
        return {name: wf.description for name, wf in WORKFLOWS.items()}

    def match_workflow(self, task: str) -> Optional[Dict[str, Any]]:
        """
        根据任务描述匹配工作流（简单任务用规则）

        Args:
            task: 用户任务描述

        Returns:
            匹配结果或 None
        """
        return match_workflow(task)

    def select_workflow_with_llm(self, task: str) -> Optional[Dict[str, Any]]:
        """
        使用 LLM 选择工作流和提取参数（复杂任务）

        Args:
            task: 用户任务描述

        Returns:
            {"workflow_name": str, "params": dict} 或 None
        """
        if not self._task_runner:
            self._log("TaskRunner 未设置，无法调用 LLM")
            return None

        # 构建 prompt
        workflow_desc = get_workflow_descriptions()

        prompt = f"""分析以下任务，选择合适的预定义工作流并提取参数。

【用户任务】
{task}

【可用工作流】
{workflow_desc}

【输出格式】
如果任务匹配某个工作流，返回 JSON：
{{"workflow": "工作流名称", "params": {{"参数名": "参数值", ...}}}}

如果没有匹配的工作流，返回：
{{"workflow": null, "reason": "原因说明"}}

注意：
1. 仔细分析任务意图，选择最匹配的工作流
2. 从任务描述中提取所有必需参数
3. 只返回 JSON，不要其他内容"""

        try:
            # 调用 LLM
            vision_agent = self._task_runner.planner.vision
            response = vision_agent._call_openai_compatible(
                "你是任务分析助手，负责匹配工作流和提取参数。只返回JSON。",
                prompt,
                image_base64=None,
                json_mode=True
            )

            self._log(f"LLM 工作流选择响应: {response[:200]}...")

            # 解析响应
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                workflow_name = result.get("workflow")

                if workflow_name and workflow_name in WORKFLOWS:
                    return {
                        "workflow_name": workflow_name,
                        "params": result.get("params", {}),
                        "match_type": "llm"
                    }
                else:
                    self._log(f"LLM 未选择工作流: {result.get('reason', '未知原因')}")

        except Exception as e:
            self._log(f"LLM 工作流选择失败: {e}")

        return None

    def execute_workflow(
        self,
        workflow_name: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行指定工作流

        Args:
            workflow_name: 工作流名称
            params: 工作流参数

        Returns:
            执行结果
        """
        if not self._workflow_executor:
            return {
                "success": False,
                "message": "工作流执行器未初始化，请先调用 set_task_runner()"
            }

        if workflow_name not in WORKFLOWS:
            return {
                "success": False,
                "message": f"未知工作流: {workflow_name}，可用: {list(WORKFLOWS.keys())}"
            }

        workflow = WORKFLOWS[workflow_name]
        return self._workflow_executor.execute_workflow(workflow, params)

    def execute_task_with_workflow(self, task: str) -> Optional[Dict[str, Any]]:
        """
        尝试使用工作流执行任务

        流程：
        1. 简单任务 -> 规则匹配
        2. 复杂任务 -> LLM 选择

        Args:
            task: 用户任务描述

        Returns:
            执行结果，如果没有匹配的工作流则返回 None
        """
        workflow_name = None
        params = {}

        # 1. 检查是否为复杂任务
        if is_complex_task(task):
            self._log(f"检测到复杂任务，使用 LLM 选择工作流")
            llm_result = self.select_workflow_with_llm(task)
            if llm_result:
                workflow_name = llm_result["workflow_name"]
                params = llm_result["params"]
                self._log(f"LLM 选择工作流: {workflow_name}, 参数: {params}")
        else:
            # 2. 简单任务使用规则匹配
            match_result = self.match_workflow(task)
            if match_result:
                workflow = match_result["workflow"]
                workflow_name = workflow.name
                param_hints = match_result["param_hints"]
                params = parse_task_params(task, param_hints)
                self._log(f"规则匹配工作流: {workflow_name}, 参数: {params}")

        # 3. 如果没有匹配到工作流
        if not workflow_name:
            self._log(f"未匹配到工作流: {task}")
            return None

        # 4. 检查必需参数
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

        # 5. 执行工作流
        return self.execute_workflow(workflow_name, params)

    def detect_current_screen(self) -> {Channel}Screen:
        """检测当前界面"""
        if not self._workflow_executor:
            return {Channel}Screen.UNKNOWN
        return self._workflow_executor.detect_screen()

    def navigate_to_home(self) -> bool:
        """导航到首页"""
        if not self._workflow_executor:
            return False
        return self._workflow_executor.navigate_to_home()

    def get_screen_ref(self, screen: {Channel}Screen) -> Optional[str]:
        """获取界面对应的参考图名称"""
        return SCREEN_DETECT_REFS.get(screen)

    def get_planner_prompt(self) -> str:
        """
        获取规划器提示词

        扩展父类方法，添加工作流相关信息
        """
        base_prompt = super().get_planner_prompt()

        # 添加工作流信息（包含具体步骤）
        workflow_info = "\n\n【预定义工作流 - 必须优先参考！】\n"
        workflow_info += "以下任务有预定义的执行路径，**必须优先使用这些步骤**，不要自主设计：\n\n"

        for name, wf in WORKFLOWS.items():
            workflow_info += f"**{name}**: {wf.description}\n"
            workflow_info += f"  必需参数: {wf.required_params}\n"
            workflow_info += f"  标准步骤:\n"
            for i, step in enumerate(wf.steps, 1):
                target = step.target if step.target else "(无)"
                workflow_info += f"    {i}. {step.action}: {step.description} -> {target}\n"
            workflow_info += "\n"

        workflow_info += """**使用规则**:
1. 如果任务匹配上述工作流，**直接使用其标准步骤**
2. 根据当前屏幕调整起点 - 如果已在中间步骤，跳过前面的步骤
3. 只有无匹配时才自主规划

【重要：界面导航规则】
1. 执行任何操作前，先检查当前界面状态
2. 如果不在正确的界面，先导航到正确位置
3. 不要在错误的界面尝试执行操作

【重要：参考图用途区分】
参考图分为两类，用途不同：

1. 界面判断参考图（用于验证当前在哪个页面，不用于点击）：
   - system/{channel}_home_page: 首页
   - system/{channel}_*_page: 其他页面

2. 点击操作参考图（用于定位可点击元素）：
   - {channel}_*_button: 各种按钮
   - {channel}_*_input: 输入框

注意：
- 点击操作时必须使用"点击操作参考图"，不要使用"界面判断参考图"！
- 部分参考图有 _v1 变体版本用于多设备适配，系统会自动尝试匹配
"""

        return base_prompt + workflow_info
