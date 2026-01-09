"""apps/chrome/handler.py
Chrome 浏览器模块处理器 - 集成工作流执行功能
"""
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

from apps.base import DefaultHandler
from .workflows import (
    Workflow, ChromeScreen, WORKFLOWS,
    match_workflow, is_complex_task, get_workflow_descriptions,
    SCREEN_DETECT_REFS
)
from .workflow_executor import WorkflowExecutor, parse_task_params
from ai.task_classifier import get_task_classifier, TaskType


class Handler(DefaultHandler):
    """
    Chrome 专用处理器

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

        prompt = f"""分析以下 Chrome 浏览器任务，选择合适的预定义工作流并提取参数。

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
2. 从任务描述中提取所有必需参数（如 url, query 等）
3. 如果是打开网址，确保 url 格式正确（自动补全 https://）
4. 只返回 JSON，不要其他内容"""

        try:
            vision_agent = self._task_runner.planner.vision
            response = vision_agent._call_openai_compatible(
                "你是任务分析助手，负责匹配 Chrome 浏览器工作流和提取参数。只返回JSON。",
                prompt,
                image_base64=None,
                json_mode=True
            )

            self._log(f"LLM 工作流选择响应: {response[:200]}...")

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
        # Chrome 的简单任务类型
        simple_task_types = {"open_url", "search_web", "open_baidu"}

        # ========== 第一步：正则分配（SS快速模式）==========
        regex_success = False
        parsed_data = None
        task_parsed_type = None

        if self._is_chrome_ss_mode(task):
            self._log(f"检测到 Chrome SS 快速模式，尝试正则解析")
            parsed_data = self._parse_chrome_ss_mode(task)
            if parsed_data and parsed_data.get("type"):
                task_parsed_type = parsed_data["type"]
                regex_success = True
                self._log(f"正则解析成功: type={task_parsed_type}")

        # ========== 第二步：根据正则结果决定后续流程 ==========
        if regex_success and task_parsed_type in simple_task_types:
            self._log(f"")
            self._log(f"╔════════════════════════════════════════╗")
            self._log(f"║   【正则分配成功】尝试 local 执行       ║")
            self._log(f"╚═══════════════��════════════════════════╝")
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
                self._log(f"LLM 重新分类为 invalid，但任务已通过正则验证，继续 LLM 从头规划")
                return {"success": False, "need_llm_replan": True, "message": "local失败，需要LLM从头规划"}

            if llm_parsed_data and llm_parsed_data.get("type") in simple_task_types:
                self._log(f"LLM 重新分配为简单任务: {llm_parsed_data.get('type')}")
                result2 = self._execute_local_workflow(llm_parsed_data["type"], llm_parsed_data)
                if result2 and result2.get("success"):
                    return result2

                self._log(f"LLM 分配的简单任务 local 执行也失败，需要 LLM 从头规划")
                return {"success": False, "need_llm_replan": True, "message": "简单任务执行失败，需要LLM从头规划"}
            else:
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
                self._log(f"LLM 分配为简单任务: {llm_parsed_data.get('type')}")
                result = self._execute_local_workflow(llm_parsed_data["type"], llm_parsed_data)
                if result and result.get("success"):
                    return result

                self._log(f"LLM 分配的简单任务 local 执行失败，需要 LLM 从头规划")
                return {"success": False, "need_llm_replan": True, "message": "简单任务执行失败，需要LLM从头规划"}
            else:
                self._log(f"LLM 分配为复杂/其他任务: {llm_parsed_data.get('type') if llm_parsed_data else 'None'}")
                return {"success": False, "need_llm_replan": True, "message": "复杂任务，需要LLM从头规划"}

    def _is_chrome_ss_mode(self, task: str) -> bool:
        """
        检查是否为 Chrome SS 快速模式

        快速模式格式：
        1. 打开 <url>
        2. 搜索 <query>
        3. 百度 <query>

        Args:
            task: 用户任务描述

        Returns:
            是否为 SS 模式
        """
        task_stripped = task.strip()
        if not task_stripped:
            return False

        # 检查简单模式
        patterns = [
            r'^打开\s+(https?://\S+|www\.\S+|[a-zA-Z0-9][-a-zA-Z0-9]*\.\w+\S*)$',  # 打开网址
            r'^(搜索|查一下|百度一下|谷歌一下)\s+.+$',  # 搜索
            r'^打开百度$',  # 打开百度
            r'^新建标签$',  # 新建标签
            r'^刷新$',  # 刷新
        ]

        for pattern in patterns:
            if re.match(pattern, task_stripped, re.IGNORECASE):
                return True

        return False

    def _parse_chrome_ss_mode(self, task: str) -> Optional[Dict[str, Any]]:
        """
        解析 Chrome SS 快速模式的指令

        Args:
            task: 用户任务描述

        Returns:
            解析后的数据 {type, url/query, ...}
        """
        task_stripped = task.strip()

        # 打开网址
        url_match = re.match(r'^打开\s+(https?://\S+|www\.\S+|[a-zA-Z0-9][-a-zA-Z0-9]*\.\w+\S*)$', task_stripped, re.IGNORECASE)
        if url_match:
            url = url_match.group(1)
            if not url.startswith('http'):
                url = 'https://' + url
            return {
                "channel": "chrome",
                "type": "open_url",
                "url": url,
                "recipient": "",
                "content": url
            }

        # 搜索
        search_match = re.match(r'^(搜索|查一下|百度一下|谷歌一下)\s+(.+)$', task_stripped)
        if search_match:
            query = search_match.group(2).strip()
            return {
                "channel": "chrome",
                "type": "search_web",
                "query": query,
                "recipient": "",
                "content": query
            }

        # 打开百度
        if task_stripped == "打开百度":
            return {
                "channel": "chrome",
                "type": "open_baidu",
                "recipient": "",
                "content": ""
            }

        return None

    def _execute_local_workflow(self, task_type: str, parsed_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        执行 local 工作流

        Args:
            task_type: 任务类型 (open_url, search_web, open_baidu)
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

        return self.execute_workflow(local_workflow_name, params, local_only=True)

    def _map_type_to_workflow(self, task_type: str, local_only: bool = False) -> Optional[str]:
        """
        将任务类型映射到工作流名称

        Args:
            task_type: 任务类型
            local_only: 是否使用 local_only 版本的工作流

        Returns:
            工作流名称
        """
        if local_only:
            type_to_workflow_map = {
                "open_url": "open_url_local",
                "search_web": "search_web_local",
                "open_baidu": "open_baidu_local",
            }
        else:
            type_to_workflow_map = {
                "open_url": "open_url",
                "search_web": "search_web",
                "open_baidu": "open_baidu",
                "new_tab": "new_tab",
                "refresh": "refresh",
                "view_bookmarks": "view_bookmarks",
                "view_history": "view_history",
                "view_downloads": "view_downloads",
                "close_tab": "close_tab",
            }

        return type_to_workflow_map.get(task_type)

    def _map_parsed_data_to_workflow_params(
        self,
        parsed_data: Dict[str, Any],
        workflow_name: str
    ) -> Dict[str, Any]:
        """
        将解析的数据映射到工作流参数

        Args:
            parsed_data: 解析的数据
            workflow_name: 工作流名称

        Returns:
            工作流所需的参数字典
        """
        params = {}
        task_type = parsed_data.get("type", "")

        if workflow_name in ["open_url", "open_url_local"]:
            params["url"] = parsed_data.get("url", "") or parsed_data.get("content", "")

        elif workflow_name in ["search_web", "search_web_local"]:
            params["query"] = parsed_data.get("query", "") or parsed_data.get("content", "")

        elif workflow_name in ["open_baidu", "open_baidu_local"]:
            # 打开百度不需要参数
            pass

        else:
            # 通用映射
            if parsed_data.get("url"):
                params["url"] = parsed_data["url"]
            if parsed_data.get("query"):
                params["query"] = parsed_data["query"]
            if parsed_data.get("content"):
                params["content"] = parsed_data["content"]

        return params

    def detect_current_screen(self) -> ChromeScreen:
        """检测当前 Chrome 界面"""
        if not self._workflow_executor:
            return ChromeScreen.UNKNOWN
        return self._workflow_executor.detect_screen()

    def navigate_to_home(self) -> bool:
        """导航到 Chrome 主页"""
        if not self._workflow_executor:
            return False
        return self._workflow_executor.navigate_to_home()

    def get_screen_ref(self, screen: ChromeScreen) -> Optional[str]:
        """获取界面对应的参考图名称"""
        return SCREEN_DETECT_REFS.get(screen)

    def get_planner_prompt(self) -> str:
        """
        获取规划器提示词

        扩展父类方法，添加工作流相关信息
        """
        base_prompt = super().get_planner_prompt()

        # 添加工作流信息
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
【重要：Chrome 参考图用途】

1. 界面判断参考图：
   - chrome_home_page: Chrome 主页/新标签页
   - chrome_address_bar: 地址栏

2. 点击操作参考图：
   - chrome_address_bar: 地址栏（点击后可输入网址）
   - chrome_search_box: 搜索框
   - chrome_tab_switcher: 标签页切换按钮
   - chrome_menu_button: 菜单按钮
   - chrome_home_button: 主页按钮
   - chrome_refresh_button: 刷新按钮
   - chrome_back_button: 返回按钮

注意：
- 输入网址时先点击地址栏，再输入内容，最后按回车
- Chrome 的地址栏同时支持网址和搜索
"""

        return base_prompt + workflow_info
