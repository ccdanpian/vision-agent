"""
apps/wechat/handler.py
微信模块处理器 - 集成工作流执行功能
"""
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

from apps.base import DefaultHandler
from .workflows import (
    Workflow, WeChatScreen, WORKFLOWS,
    match_workflow, is_complex_task, get_workflow_descriptions,
    SCREEN_DETECT_REFS
)
from .workflow_executor import WorkflowExecutor, parse_task_params
from ai.task_classifier import get_task_classifier, TaskType


class Handler(DefaultHandler):
    """
    微信专用处理器

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
        # 设置任务分类器的日志
        classifier = get_task_classifier()
        classifier.set_logger(logger_func)

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
3. 如果任务包含多个步骤（如先发消息再发朋友圈），选择 message_and_moments
4. 只返回 JSON，不要其他内容"""

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
        params: Dict[str, Any],
        local_only: bool = False
    ) -> Dict[str, Any]:
        """
        执行指定工作流

        Args:
            workflow_name: 工作流名称
            params: 工作流参数
            local_only: 是否仅使用本地匹配（禁用AI回退）

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
        return self._workflow_executor.execute_workflow(workflow, params, local_only)

    def execute_task_with_workflow(self, task: str) -> Optional[Dict[str, Any]]:
        """
        尝试使用工作流执行任务

        流程：
        1. 正则分配（SS快速模式）
           - 成功且简单任务 → local执行
             - local失败 → LLM重新分配
               - LLM简单任务 → 再次local执行
                 - 再次失败 → 返回需要LLM从头规划
               - LLM复杂任务 → 返回需要LLM从头规划
           - 失败 → LLM分配
             - LLM简单任务 → local执行
               - 失败 → 返回需要LLM从头规划
             - LLM复杂任务 → 返回需要LLM从头规划

        Args:
            task: 用户任务描述

        Returns:
            执行结果，包含 need_llm_replan=True 表示需要 LLM 从头规划
        """
        classifier = get_task_classifier()
        simple_task_types = {"send_msg", "post_moment_only_text"}

        # ========== 第一步：正则分配（SS快速模式）==========
        regex_success = False
        parsed_data = None
        task_parsed_type = None

        if classifier._is_ss_mode(task):
            self._log(f"检测到 SS 快速模式，尝试正则解析")
            parsed_data = classifier._parse_ss_mode(task)
            if parsed_data and parsed_data.get("type"):
                task_parsed_type = parsed_data["type"]
                regex_success = True
                self._log(f"正则解析成功: type={task_parsed_type}")

        # ========== 第二步：根据正则结果决定后续流程 ==========
        if regex_success and task_parsed_type in simple_task_types:
            # 正则成功且是简单任务 → local 执行
            self._log(f"")
            self._log(f"╔════════════════════════════════════════╗")
            self._log(f"║   【正则分配成功】尝试 local 执行       ║")
            self._log(f"╚════════════════════════════════════════╝")
            self._log(f"")

            result = self._execute_local_workflow(task_parsed_type, parsed_data)
            if result and result.get("success"):
                return result

            # local 失败，LLM 重新分配
            self._log(f"")
            self._log(f"╔════════════════════════════════════════╗")
            self._log(f"║   【local失败】LLM 重新分配任务         ║")
            self._log(f"╚════════════════════════════════════════╝")
            self._log(f"")
            self._log(f"local 失败原因: {result.get('message', '未知') if result else '无结果'}")

            classifier._ensure_llm_agent()
            classifier._classify_with_llm(task)
            llm_parsed_data = classifier._last_parsed_data

            if llm_parsed_data and llm_parsed_data.get("type") == "invalid":
                return {"success": False, "message": "无效的输入指令", "error_type": "invalid_input"}

            if llm_parsed_data and llm_parsed_data.get("type") in simple_task_types:
                # LLM 分配为简单任务 → 再次 local 执行
                self._log(f"LLM 重新分配为简单任务: {llm_parsed_data.get('type')}")
                result2 = self._execute_local_workflow(llm_parsed_data["type"], llm_parsed_data)
                if result2 and result2.get("success"):
                    return result2

                # 再次失败 → 需要 LLM 从头规划
                self._log(f"LLM 分配的简单任务 local 执行也失败，需要 LLM 从头规划")
                return {"success": False, "need_llm_replan": True, "message": "简单任务执行失败，需要LLM从头规划"}
            else:
                # LLM 分配为复杂任务或其他 → 需要 LLM 从头规划
                self._log(f"LLM 分配为复杂/其他任务: {llm_parsed_data.get('type') if llm_parsed_data else 'None'}")
                return {"success": False, "need_llm_replan": True, "message": "复杂任务，需要LLM从头规划"}

        else:
            # 正则失败或不是简单任务 → LLM 分配
            self._log(f"")
            self._log(f"╔════════════════════════════════════════╗")
            self._log(f"║   【正则分配失败】LLM 分配任务          ║")
            self._log(f"╚════════════════════════════════════════╝")
            self._log(f"")

            classifier._ensure_llm_agent()
            classifier._classify_with_llm(task)
            llm_parsed_data = classifier._last_parsed_data

            if llm_parsed_data and llm_parsed_data.get("type") == "invalid":
                return {"success": False, "message": "无效的输入指令", "error_type": "invalid_input"}

            if llm_parsed_data and llm_parsed_data.get("type") in simple_task_types:
                # LLM 分配为简单任务 → local 执行
                self._log(f"LLM 分配为简单任务: {llm_parsed_data.get('type')}")
                result = self._execute_local_workflow(llm_parsed_data["type"], llm_parsed_data)
                if result and result.get("success"):
                    return result

                # 失败 → 需要 LLM 从头规划
                self._log(f"LLM 分配的简单任务 local 执行失败，需要 LLM 从头规划")
                return {"success": False, "need_llm_replan": True, "message": "简单任务执行失败，需要LLM从头规划"}
            else:
                # LLM 分配为复杂任务 → 需要 LLM 从头规划
                self._log(f"LLM 分配为复杂/其他任务: {llm_parsed_data.get('type') if llm_parsed_data else 'None'}")
                return {"success": False, "need_llm_replan": True, "message": "复杂任务，需要LLM从头规划"}

    def _execute_local_workflow(self, task_type: str, parsed_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        执行 local 工作流

        Args:
            task_type: 任务类型 (send_msg, post_moment_only_text)
            parsed_data: 解析的参数数据

        Returns:
            执行结果
        """
        workflow_name = self._map_type_to_workflow(task_type, local_only=False)
        local_workflow_name = self._map_type_to_workflow(task_type, local_only=True)

        if not workflow_name or not local_workflow_name:
            self._log(f"无法映射工作流: {task_type}")
            return None

        params = self._map_parsed_data_to_workflow_params(parsed_data, workflow_name)
        self._log(f"执行 local 工作流: {local_workflow_name}, 参数: {params}")

        # 检查必需参数
        workflow = WORKFLOWS[workflow_name]
        missing = [p for p in workflow.required_params if p not in params or not params[p]]
        if missing:
            self._log(f"缺少必需参数: {missing}")
            return {"success": False, "message": f"缺少必需参数: {missing}", "missing_params": missing}

        # 执行 local_only 版本
        return self.execute_workflow(local_workflow_name, params, local_only=True)

    def _map_type_to_workflow(self, task_type: str, local_only: bool = False) -> Optional[str]:
        """
        将任务类型映射到工作流名称

        Args:
            task_type: 任务类型（如 send_msg, post_moment_only_text）
            local_only: 是否使用 local_only 版本的工作流

        Returns:
            工作流名称，如果无法映射则返回 None
        """
        if local_only:
            # Local 版本映射
            type_to_workflow_map = {
                "send_msg": "send_message_local",
                "post_moment_only_text": "post_moments_only_text_local",
            }
        else:
            # 正常版本映射
            type_to_workflow_map = {
                "send_msg": "send_message",
                "post_moment_only_text": "post_moments",
                "search_contact": "search_contact",
                "add_friend": "add_friend",
            }

        return type_to_workflow_map.get(task_type)

    def _map_parsed_data_to_workflow_params(
        self,
        parsed_data: Dict[str, Any],
        workflow_name: str
    ) -> Dict[str, Any]:
        """
        将解析的数据映射到工作流参数

        支持 SS 快速模式和 LLM 智能模式解析的统一格式：
        {
          "type": "send_msg" / "post_moment_only_text" / "others",
          "recipient": "好友名称",
          "content": "消息内容"
        }

        Args:
            parsed_data: 解析的数据
            workflow_name: 工作流名称

        Returns:
            工作流所需的参数字典
        """
        params = {}
        task_type = parsed_data.get("type", "")
        recipient = parsed_data.get("recipient", "")
        content = parsed_data.get("content", "")

        # 根据工作流名称映射参数
        if workflow_name == "send_message":
            # 发消息工作流需要: contact, message
            params["contact"] = recipient
            params["message"] = content

        elif workflow_name == "post_moments":
            # 发朋友圈工作流需要: content
            params["content"] = content

        elif workflow_name == "search_contact":
            # 搜索联系人需要: keyword
            params["keyword"] = recipient or content

        elif workflow_name == "add_friend":
            # 添加好友需要: wechat_id
            params["wechat_id"] = recipient or content

        else:
            # 未知工作流，尝试通用映射
            self._log(f"警告: 未知工作流 {workflow_name}，使用通用参数映射")
            if recipient:
                params["contact"] = recipient
                params["recipient"] = recipient
            if content:
                params["message"] = content
                params["content"] = content

        return params

    def detect_current_screen(self) -> WeChatScreen:
        """检测当前微信界面"""
        if not self._workflow_executor:
            return WeChatScreen.UNKNOWN
        return self._workflow_executor.detect_screen()

    def navigate_to_home(self) -> bool:
        """导航到微信首页"""
        if not self._workflow_executor:
            return False
        return self._workflow_executor.navigate_to_home()

    def get_screen_ref(self, screen: WeChatScreen) -> Optional[str]:
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
"""

        workflow_info += """
【重要：界面导航规则】
1. 执行任何操作前，先检查当前界面状态
2. 如果不在正确的界面，先导航到正确位置：
   - 按返回键回到首页
   - 使用 system/wechat_home_page 验证是否到达首页
3. 不要在错误的界面尝试执行操作

【重要：参考图用途区分】
参考图分为两类，用途不同：

1. 界面判断参考图（用于验证当前在哪个页面，不用于点击）：
   - system/wechat_home_page: 微信首页（聊天列表）
   - system/wechat_contacts_page: 通讯录页面
   - system/wechat_discover_page: 发现页面
   - system/wechat_me_page: 我的页面

2. 点击操作参考图（用于定位可点击元素）：
   - wechat_home_button: 底部"微信"Tab按钮（聊天主页）
   - wechat_news_button: 底部"消息"Tab按钮（同wechat_home_button）
   - wechat_tab_discover_button: 底部"发现"Tab按钮
   - wechat_tab_contacts_button: 底部"通讯录"Tab按钮
   - wechat_tab_me_button: 底部"我"Tab按钮
   - wechat_search_button: 搜索按钮
   - wechat_back: 返回按钮
   - wechat_chat_input: 聊天输入框
   - wechat_chat_send: 发送按钮
   - wechat_moments_entry: 朋友圈入口（发现页）
   - wechat_moments_camera: 朋友圈相机图标
   - contacts/wechat_contacts_zhanghua: 通讯录中"张华"联系人

注意：
- 点击操作时必须使用"点击操作参考图"，不要使用"界面判断参考图"！
- 部分参考图有 _v1 变体版本用于多设备适配，系统会自动尝试匹配
"""

        return base_prompt + workflow_info
