"""
core/task_runner.py
任务执行器 - 整合所有层，执行完整任务流程

职责:
- 协调 Planner、Locator、Executor、Verifier
- 执行任务计划中的每个步骤
- 处理错误和恢复
- 记录执行日志
- 支持模块化架构，自动路由到相应模块
"""
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from PIL import Image
import io

from config import LLMConfig, get_screenshot_wait, OPERATION_DELAY
from core.adb_controller import ADBController
from core.hybrid_locator import HybridLocator, LocateStrategy, create_hybrid_locator
from core.execution_strategy import (
    ExecutionLevel, StepStrategy, get_step_strategy,
    can_batch_execute, should_verify_at_end
)
from ai.planner import Planner, TaskPlan, StepPlan, ActionName, TargetType, AssetsManager
from ai.verifier import Verifier, VerifyResult, SuggestionAction, BlockerType, Blocker
from ai.vision_agent import VisionAgent
from apps import ModuleRegistry
from apps.base import AppHandler


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ABORTED = "aborted"


class StepStatus(Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """步骤执行结果"""
    step: StepPlan
    status: StepStatus
    start_time: float = 0.0
    end_time: float = 0.0
    retry_count: int = 0
    error_message: str = ""
    screenshot_before: Optional[Image.Image] = None
    screenshot_after: Optional[Image.Image] = None
    verify_result: Optional[VerifyResult] = None


@dataclass
class TaskResult:
    """任务执行结果"""
    status: TaskStatus
    plan: Optional[TaskPlan] = None
    step_results: List[StepResult] = field(default_factory=list)
    total_time: float = 0.0
    error_message: str = ""


class TaskRunner:
    """
    任务执行器

    整合 Planner、Locator（VisionAgent）、Executor（ADBController）、Verifier，
    执行完整的自动化任务流程。
    """

    def __init__(
        self,
        adb: ADBController,
        llm_config: Optional[LLMConfig] = None,
        assets_dir: Optional[Path] = None,
        temp_dir: Optional[Path] = None,
        use_modules: bool = True
    ):
        """
        初始化任务执行器

        Args:
            adb: ADB 控制器实例
            llm_config: LLM 配置
            assets_dir: 参考图库目录
            temp_dir: 临时文件目录
            use_modules: 是否启用模块化架构
        """
        self.adb = adb
        self.planner = Planner(llm_config=llm_config, assets_dir=assets_dir)
        self.locator = VisionAgent(llm_config=llm_config)
        self.verifier = Verifier(llm_config=llm_config)
        self.assets = AssetsManager(assets_dir)

        # 混合定位器（OpenCV + AI）
        self.hybrid_locator = create_hybrid_locator(self.locator)

        # 模块化支持
        self.use_modules = use_modules
        self._current_handler: Optional[AppHandler] = None
        if use_modules:
            ModuleRegistry.discover()

        # 临时目录
        if temp_dir is None:
            temp_dir = Path(__file__).parent.parent / "temp"
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # 配置
        self.max_retries = 3
        self.step_timeout = 10.0  # 秒
        self.default_wait_after = 0.5  # 秒

        # 日志回调
        self._logger: Optional[Callable[[str], None]] = None

        # 屏幕尺寸缓存
        self._screen_size: Optional[tuple] = None

        # 屏幕边距缓存（状态栏和导航栏高度）
        self._screen_insets: Optional[dict] = None

    def set_logger(self, logger_func: Callable[[str], None]):
        """设置日志回调函数"""
        self._logger = logger_func
        self.planner.set_logger(logger_func)
        self.locator.set_logger(logger_func)
        self.verifier.set_logger(logger_func)
        self.assets.set_logger(logger_func)
        self.hybrid_locator.set_logger(logger_func)
        ModuleRegistry.set_logger(logger_func)

    def _log(self, message: str):
        """记录日志"""
        if self._logger:
            self._logger(f"[TaskRunner] {message}")
        else:
            print(f"[TaskRunner] {message}")

    def _timed_operation(self, name: str):
        """计时上下文管理器"""
        class Timer:
            def __init__(timer_self, runner, op_name):
                timer_self.runner = runner
                timer_self.op_name = op_name
                timer_self.start = None
            def __enter__(timer_self):
                timer_self.start = time.time()
                return timer_self
            def __exit__(timer_self, *args):
                elapsed = (time.time() - timer_self.start) * 1000
                timer_self.runner._log(f"⏱ {timer_self.op_name}: {elapsed:.0f}ms")
        return Timer(self, name)

    def _get_screen_size(self) -> tuple:
        """获取屏幕尺寸"""
        if self._screen_size is None:
            self._screen_size = self.adb.get_screen_size()
        return self._screen_size

    def _capture_screenshot(self, wait_before: float = None) -> Image.Image:
        """
        截取当前屏幕

        Args:
            wait_before: 截图前等待时间（秒），如果为 None 则使用当前应用的配置
        """
        # 如果没有指定等待时间，根据当前应用获取配置的等待时间
        if wait_before is None:
            app_name = self._current_handler.module_info.name if self._current_handler else None
            wait_before = get_screenshot_wait(app_name)

        if wait_before > 0:
            time.sleep(wait_before)

        start = time.time()
        screenshot_path = self.temp_dir / "current_screenshot.png"
        self.adb.screenshot(str(screenshot_path))
        img = Image.open(screenshot_path)
        img.load()  # 立即加载图片数据，避免延迟加载导致文件覆盖问题
        elapsed = (time.time() - start) * 1000
        self._log(f"⏱ 截图: {elapsed:.0f}ms")
        return img

    def _get_screen_insets(self) -> dict:
        """获取屏幕边距（状态栏和导航栏高度），带缓存"""
        if self._screen_insets is None:
            self._screen_insets = self.adb.get_screen_insets()
            self._log(f"屏幕边距: top={self._screen_insets['top']}px, bottom={self._screen_insets['bottom']}px")
        return self._screen_insets

    def _capture_screenshot_cropped(self, wait_before: float = None) -> tuple:
        """
        截取当前屏幕并裁剪掉状态栏和导航栏区域

        Args:
            wait_before: 截图前等待时间（秒）

        Returns:
            (cropped_image, top_offset): 裁剪后的图片和顶部偏移量
        """
        # 获取原始截图
        screenshot = self._capture_screenshot(wait_before)

        # 获取边距
        insets = self._get_screen_insets()
        top = insets['top']
        bottom = insets['bottom']

        # 裁剪
        width, height = screenshot.size
        cropped = screenshot.crop((0, top, width, height - bottom))

        self._log(f"裁剪截图: {width}x{height} -> {cropped.size[0]}x{cropped.size[1]} (去除 top={top}, bottom={bottom})")
        return cropped, top

    def run(self, task: str) -> TaskResult:
        """
        执行任务

        Args:
            task: 任务描述

        Returns:
            TaskResult 任务执行结果
        """
        start_time = time.time()
        self._log(f"开始执行任务: {task}")

        # 模块路由
        handler = None
        parsed_data = None
        if self.use_modules:
            from ai.task_classifier import TaskClassifier
            classifier = TaskClassifier()

            # 检查是否为快速模式（联系人:消息 或 联系人 消息 格式）
            if classifier._is_ss_mode(task):
                self._log("检测到 SS 快速模式，尝试解析")
                task_type, parsed_data = classifier.classify_and_parse(task)

                if parsed_data and parsed_data.get("type") and parsed_data["type"] != "invalid":
                    # SS 模式解析成功，使用类型路由
                    type_to_module = {
                        "send_msg": "wechat",
                        "post_moment_only_text": "wechat"
                    }
                    module_name = type_to_module.get(parsed_data["type"])
                    if module_name:
                        handler = ModuleRegistry.get(module_name)
                        if handler:
                            self._current_handler = handler
                            self._log(f"SS 模式路由到模块: {handler.module_info.name} (type={parsed_data['type']})")

            # 快速模式未匹配，使用 LLM 分类器进行分类
            if handler is None:
                self._log("快速模式未匹配，使用 LLM 进行任务分类")
                task_type, parsed_data = classifier.classify_and_parse(task)

                if parsed_data and parsed_data.get("type"):
                    if parsed_data["type"] == "invalid":
                        # LLM 判断为无效输入
                        self._log("LLM 判断为无效输入")
                        error_msg = "❌ 无效的输入指令，请检查格式后重试。"
                        result = TaskResult(
                            status=TaskStatus.FAILED,
                            error_message=error_msg,
                            total_time=0.0
                        )
                        self.state = TaskStatus.FAILED
                        return result
                    elif parsed_data["type"] in ["send_msg", "post_moment_only_text"]:
                        # LLM 分类成功，使用类型路由
                        self._log(f"LLM 分类成功: type={parsed_data['type']}")
                        type_to_module = {
                            "send_msg": "wechat",
                            "post_moment_only_text": "wechat"
                        }
                        module_name = type_to_module.get(parsed_data["type"])
                        if module_name:
                            handler = ModuleRegistry.get(module_name)
                            if handler:
                                self._current_handler = handler
                                self._log(f"LLM 模式路由到模块: {handler.module_info.name} (type={parsed_data['type']})")
                    elif parsed_data["type"] == "others":
                        # 复杂任务，使用关键词路由
                        self._log("LLM 分类为复杂任务，使用关键词路由")
                        handler, score = ModuleRegistry.route(task)
                        if handler:
                            self._current_handler = handler
                            self._log(f"路由到模块: {handler.module_info.name} (匹配度: {score:.2f})")

            # 如果仍无 handler，使用关键词路由作为兜底
            if handler is None:
                handler, score = ModuleRegistry.route(task)
                if handler:
                    self._current_handler = handler
                    self._log(f"兜底路由到模块: {handler.module_info.name} (匹配度: {score:.2f})")

            # 设置 TaskRunner 引用（用于工作流执行）
            if handler:
                if hasattr(handler, 'set_task_runner'):
                    handler.set_task_runner(self)

                # 优先尝试工作流执行（预定义的标准路径）
                if hasattr(handler, 'execute_task_with_workflow'):
                    workflow_result = handler.execute_task_with_workflow(task)
                    if workflow_result:
                        if workflow_result.get("success"):
                            self._log(f"工作流执行成功")
                            return TaskResult(
                                status=TaskStatus.SUCCESS,
                                total_time=time.time() - start_time
                            )
                        elif "missing_params" not in workflow_result:
                            # 工作流执行失败（非参数缺失），返回失败
                            self._log(f"工作流执行失败: {workflow_result.get('message')}")
                            return TaskResult(
                                status=TaskStatus.FAILED,
                                total_time=time.time() - start_time,
                                error_message=workflow_result.get("message", "工作流执行失败")
                            )
                        # 参数缺失，继续使用 AI 规划
                        self._log(f"工作流参数不完整，回退到 AI 规划")

                # 尝试匹配简单任务模板
                # 只有任务足够简单（无分隔符、无多动作词）且有 simple: true 的模板才会匹配
                if handler._is_simple_task(task):
                    template_result = handler.match_template(task)
                    if template_result:
                        template, variables = template_result
                        self._log(f"匹配到简单任务: {template.name}")
                        if variables:
                            self._log(f"提取变量: {variables}")

                        # 使用模板步骤
                        predefined_steps = handler.plan(task)
                        if predefined_steps:
                            self._log(f"使用预定义步骤: {len(predefined_steps)} 步")
                            return self._run_predefined_steps(task, predefined_steps, start_time)
                    else:
                        self._log("无匹配的简单任务模板，交给 AI 规划器处理")
                else:
                    self._log("检测到复合任务，交给 AI 规划器处理")

        # 确保微信在前台并回到首页（如果是微信模块）
        if handler and hasattr(handler, 'workflow_executor') and handler.workflow_executor:
            self._log("执行预设步骤：确保微信在消息页面...")
            if not handler.workflow_executor._ensure_wechat_running():
                return TaskResult(
                    status=TaskStatus.FAILED,
                    error_message="无法启动微信或回到首页"
                )

        # 截取当前屏幕
        try:
            screenshot = self._capture_screenshot()
        except Exception as e:
            self._log(f"截图失败: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error_message=f"无法截取屏幕: {e}"
            )

        # 生成任务计划（使用模块特定的 prompt 如果有的话）
        # 保存 prompt 和 module_images，用于可能的重新规划
        custom_prompt = None
        module_images = None

        try:
            plan_start = time.time()
            if handler:
                # 使用模块的 planner prompt，并传递模块的参考图列表
                custom_prompt = handler.get_planner_prompt()
                module_images = handler.get_available_images()
                plan = self.planner.plan(task, screenshot, system_prompt=custom_prompt, module_images=module_images)
            else:
                plan = self.planner.plan(task, screenshot)
            plan_elapsed = (time.time() - plan_start) * 1000

            self._log(f"⏱ AI规划: {plan_elapsed:.0f}ms")
            self._log(f"生成计划: {len(plan.steps)} 步")
            for i, step in enumerate(plan.steps):
                self._log(f"  步骤 {i+1}: {step.action.value} - {step.description}")
        except Exception as e:
            self._log(f"规划失败: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error_message=f"任务规划失败: {e}"
            )

        if not plan.steps:
            self._log("计划无步骤")
            return TaskResult(
                status=TaskStatus.FAILED,
                plan=plan,
                error_message="任务规划未生成有效步骤"
            )

        # 使用优化的批量执行策略
        step_results = []
        executed_steps = []

        # 将步骤分批
        batches = can_batch_execute(plan.steps)
        self._log(f"步骤分为 {len(batches)} 批执行")

        batch_idx = 0
        while batch_idx < len(batches):
            batch = batches[batch_idx]

            # 批量执行确定性步骤
            if len(batch) > 1:
                self._log(f"\n=== 批量执行 {len(batch)} 个简单步骤 ===")
                for step in batch:
                    self._log(f"  [{step.step}] {step.action.value}: {step.description}")

                for step in batch:
                    result = self._execute_step_fast(step)
                    step_results.append(result)
                    if result.status == StepStatus.SUCCESS:
                        executed_steps.append(step)

                # 批量执行后短暂等待
                time.sleep(0.3)
                batch_idx += 1
                continue

            # 单步执行（需要定位或验证的步骤）
            step = batch[0]
            strategy = get_step_strategy(step)

            self._log(f"\n=== 执行步骤 {step.step}: {step.description} ===")
            self._log(f"    策略: Level {strategy.level.value} ({strategy.level.name})")

            result = self._execute_step_with_strategy(step, strategy, executed_steps)

            # 如果失败，等待后重试一次
            if result.status == StepStatus.FAILED:
                self._log(f"  步骤失败，等待 {OPERATION_DELAY}s 后重试...")
                time.sleep(OPERATION_DELAY)
                result = self._execute_step_with_strategy(step, strategy, executed_steps)

            step_results.append(result)

            step_time = (result.end_time - result.start_time) * 1000
            if result.status == StepStatus.SUCCESS:
                executed_steps.append(step)
                self._log(f"✓ 步骤 {step.step} 成功 (总耗时: {step_time:.0f}ms)")
            elif result.status == StepStatus.SKIPPED:
                self._log(f"⊘ 步骤 {step.step} 跳过: {result.error_message}")
            else:
                self._log(f"✗ 步骤 {step.step} 失败: {result.error_message} (耗时: {step_time:.0f}ms)")

                # 检查是否需要重新规划
                if result.verify_result and result.verify_result.suggestion == SuggestionAction.REPLAN:
                    self._log("尝试重新规划...")
                    try:
                        current_screenshot = self._capture_screenshot()
                        new_plan = self.planner.replan(
                            task,
                            current_screenshot,
                            step,
                            result.error_message,
                            executed_steps,
                            system_prompt=custom_prompt,
                            module_images=module_images
                        )
                        if new_plan.steps:
                            # 用新规划的步骤替换，从头开始执行新步骤
                            batches = can_batch_execute(new_plan.steps)
                            batch_idx = 0  # 重置索引，从新规划的第一步开始
                            self._log(f"重新规划成功，新增 {len(new_plan.steps)} 步，从头执行")
                            continue
                    except Exception as e:
                        self._log(f"重新规划失败: {e}")

                # 失败且无法恢复
                if result.verify_result and result.verify_result.suggestion == SuggestionAction.ABORT:
                    return TaskResult(
                        status=TaskStatus.ABORTED,
                        plan=plan,
                        step_results=step_results,
                        total_time=time.time() - start_time,
                        error_message=result.error_message
                    )

                # 默认：遇到失败立即停止，避免继续执行造成误操作
                return TaskResult(
                    status=TaskStatus.FAILED,
                    plan=plan,
                    step_results=step_results,
                    total_time=time.time() - start_time,
                    error_message=result.error_message
                )

            batch_idx += 1

        # 判断最终结果
        failed_steps = [r for r in step_results if r.status == StepStatus.FAILED]
        if failed_steps:
            status = TaskStatus.FAILED
            error_msg = f"{len(failed_steps)} 个步骤失败"
        else:
            status = TaskStatus.SUCCESS
            error_msg = ""

        total_time = time.time() - start_time
        self._log(f"\n任务完成: {status.value}, 耗时 {total_time:.1f}s")

        return TaskResult(
            status=status,
            plan=plan,
            step_results=step_results,
            total_time=total_time,
            error_message=error_msg
        )

    def _run_predefined_steps(
        self,
        task: str,
        steps: List[Dict[str, Any]],
        start_time: float
    ) -> TaskResult:
        """
        执行预定义步骤（来自模块模板）

        Args:
            task: 原始任务描述
            steps: 预定义步骤列表（字典格式）
            start_time: 任务开始时间

        Returns:
            TaskResult
        """
        step_results = []

        for i, step_dict in enumerate(steps):
            self._log(f"\n=== 执行预定义步骤 {i+1}/{len(steps)} ===")

            # 将字典转换为 StepPlan
            step = self._dict_to_step(step_dict, i + 1)
            if step is None:
                self._log(f"步骤格式错误: {step_dict}")
                continue

            self._log(f"动作: {step.action.value}")
            self._log(f"描述: {step.description}")

            # 执行步骤
            result = self._execute_step(step, [])
            step_results.append(result)

            if result.status == StepStatus.SUCCESS:
                self._log(f"步骤 {i+1} 成功")
            elif result.status == StepStatus.FAILED:
                self._log(f"步骤 {i+1} 失败: {result.error_message}")
                # 预定义步骤失败则停止
                break

        # 判断结果
        failed = [r for r in step_results if r.status == StepStatus.FAILED]
        total_time = time.time() - start_time

        if failed:
            return TaskResult(
                status=TaskStatus.FAILED,
                step_results=step_results,
                total_time=total_time,
                error_message=f"预定义步骤执行失败"
            )

        return TaskResult(
            status=TaskStatus.SUCCESS,
            step_results=step_results,
            total_time=total_time
        )

    # WeChat 动态描述到参考图的映射（中文描述 -> 参考图名称）
    _WECHAT_TARGET_MAPPING = {
        # 底部 Tab
        "微信": "wechat_home_button",
        "微信Tab": "wechat_home_button",
        "聊天": "wechat_home_button",
        "聊天Tab": "wechat_home_button",
        "发现": "wechat_tab_discover_button",
        "发现Tab": "wechat_tab_discover_button",
        "发现tab": "wechat_tab_discover_button",
        "通讯录": "wechat_tab_contacts_button",
        "通讯录Tab": "wechat_tab_contacts_button",
        "我": "wechat_tab_me_button",
        "我Tab": "wechat_tab_me_button",
        # 朋友圈相关
        "朋友圈": "wechat_moments_entry",
        "朋友圈入口": "wechat_moments_entry",
        "朋友圈输入框": "wechat_moments_input_box",
        "朋友圈文字输入框": "wechat_moments_input_box",
        "相机图标": "wechat_moments_camera",
        "发朋友圈相机": "wechat_moments_camera",
        "朋友圈相机": "wechat_moments_camera",
        "添加图片": "wechat_moments_pic_add_start",
        "选择图片": "wechat_moments_pic_add_start",
        "完成选图": "wechat_moments_pic_add_done",
        "图片添加完成": "wechat_moments_pic_add_done",
        "发表按钮": "wechat_moments_publish",
        "发布按钮": "wechat_moments_publish",
        # 顶部按钮
        "+号": "wechat_add_button",
        "+号按钮": "wechat_add_button",
        "加号": "wechat_add_button",
        "添加按钮": "wechat_add_button",
        "搜索": "wechat_search_button",
        "搜索按钮": "wechat_search_button",
        "返回": "wechat_back",
        "返回按钮": "wechat_back",
        # +号菜单
        "扫一扫": "wechat_menu_scan",
        "添加朋友": "wechat_menu_add_friend",
        "发起群聊": "wechat_menu_group_chat",
        "收付款": "wechat_menu_receive_payment",
        # 聊天界面
        "输入框": "wechat_chat_input",
        "聊天输入框": "wechat_chat_input",
        "发送": "wechat_chat_send",
        "发送按钮": "wechat_chat_send",
        "语音按钮": "wechat_chat_voice",
        "表情按钮": "wechat_chat_emoji",
        "更多按钮": "wechat_chat_more",
        # 添加好友流程
        "搜索输入框": "wechat_add_search_input",
        "添加到通讯录": "wechat_add_contact_button",
        "发送申请": "wechat_add_send_button",
        # 页面状态验证（用于 verify_ref）
        "微信首页": "system/wechat_home_page",
        "首页": "system/wechat_home_page",
        "聊天列表": "system/wechat_home_page",
        "微信主页": "system/wechat_home_page",
        "通讯录页面": "system/wechat_contacts_page",
        "联系人页面": "system/wechat_contacts_page",
        "联系人列表": "system/wechat_contacts_page",
        "发现页面": "system/wechat_discover_page",
        "发现页": "system/wechat_discover_page",
        "我的页面": "system/wechat_me_page",
        "我页面": "system/wechat_me_page",
        "个人页面": "system/wechat_me_page",
    }

    def _normalize_target_ref(self, target_ref: Optional[str]) -> Optional[str]:
        """
        规范化 target_ref，将动态描述映射到参考图名称

        如果 target_ref 以 "dynamic:" 开头，检查描述是否匹配已知的参考图，
        如果匹配则返回参考图名称（不带 dynamic: 前缀），否则返回原值。

        Args:
            target_ref: 原始的 target_ref

        Returns:
            规范化后的 target_ref
        """
        if target_ref is None:
            return None

        if not target_ref.startswith("dynamic:"):
            return target_ref

        # 提取描述部分
        description = target_ref[8:]  # 去掉 "dynamic:" 前缀
        self._log(f"  [规范化] 检测到动态描述: '{description}'")

        # 尝试直接匹配
        if description in self._WECHAT_TARGET_MAPPING:
            mapped = self._WECHAT_TARGET_MAPPING[description]
            self._log(f"  [规范化] 直接匹配成功: '{description}' -> '{mapped}'")
            return mapped

        # 尝试模糊匹配（包含关系），优先匹配更长的键
        best_match = None
        best_match_len = 0
        for key, value in self._WECHAT_TARGET_MAPPING.items():
            if key in description or description in key:
                # 优先选择更长的匹配（更具体）
                if len(key) > best_match_len:
                    best_match = (key, value)
                    best_match_len = len(key)

        if best_match:
            self._log(f"  [规范化] 模糊匹配成功: '{description}' 包含 '{best_match[0]}' -> '{best_match[1]}'")
            return best_match[1]

        # 如果有当前处理器，尝试从模块获取映射
        if self._current_handler:
            module_mapping = getattr(self._current_handler, 'target_ref_mapping', {})
            if description in module_mapping:
                mapped = module_mapping[description]
                self._log(f"  [规范化] 模块映射匹配: '{description}' -> '{mapped}'")
                return mapped
            # 模糊匹配，优先匹配更长的键
            best_match = None
            best_match_len = 0
            for key, value in module_mapping.items():
                if key in description or description in key:
                    if len(key) > best_match_len:
                        best_match = (key, value)
                        best_match_len = len(key)
            if best_match:
                self._log(f"  [规范化] 模块模糊匹配: '{description}' 包含 '{best_match[0]}' -> '{best_match[1]}'")
                return best_match[1]

        # 无匹配，返回原值
        self._log(f"  [规范化] 无匹配，保留原值: '{target_ref}'")
        return target_ref

    def _dict_to_step(self, step_dict: Dict[str, Any], step_num: int) -> Optional[StepPlan]:
        """
        将字典格式的步骤转换为 StepPlan

        Args:
            step_dict: 步骤字典
            step_num: 步骤序号

        Returns:
            StepPlan 或 None
        """
        action_str = step_dict.get("action", "")

        # 映射动作名称
        action_map = {
            "tap": ActionName.TAP,
            "long_press": ActionName.LONG_PRESS,
            "swipe": ActionName.SWIPE,
            "input_text": ActionName.INPUT_TEXT,
            "wait": ActionName.WAIT,
            "press_key": ActionName.PRESS_KEY,
            "key_event": ActionName.PRESS_KEY,
            "go_home": ActionName.GO_HOME,
            "launch_app": ActionName.LAUNCH_APP,
            "call": ActionName.CALL,
            "open_url": ActionName.OPEN_URL,
            "screenshot": ActionName.SCREENSHOT,  # 截屏保存
        }

        action = action_map.get(action_str.lower())
        if action is None:
            self._log(f"未知动作类型: {action_str}")
            return None

        # 构建参数
        params = {}

        # 根据动作类型提取参数
        if action == ActionName.WAIT:
            duration = step_dict.get("duration", 1.0)
            if isinstance(duration, float) and duration < 10:
                duration = int(duration * 1000)  # 转换为毫秒
            params["duration"] = duration

        elif action == ActionName.SWIPE:
            params["direction"] = step_dict.get("direction", "up")

        elif action == ActionName.INPUT_TEXT:
            params["text"] = step_dict.get("text", "")

        elif action == ActionName.PRESS_KEY:
            params["keycode"] = step_dict.get("key_code", step_dict.get("keycode", 4))

        elif action == ActionName.LAUNCH_APP:
            params["package"] = step_dict.get("package_name", step_dict.get("package", ""))
            if step_dict.get("activity"):
                params["activity"] = step_dict.get("activity")

        elif action == ActionName.CALL:
            params["number"] = step_dict.get("phone_number", step_dict.get("number", ""))

        elif action == ActionName.OPEN_URL:
            params["url"] = step_dict.get("url", "")

        elif action == ActionName.SCREENSHOT:
            params["save_path"] = step_dict.get("save_path", step_dict.get("path", ""))

        # 规范化 target_ref，将动态描述映射到参考图名称
        raw_target_ref = step_dict.get("target_ref")
        normalized_target_ref = self._normalize_target_ref(raw_target_ref)
        if normalized_target_ref != raw_target_ref:
            self._log(f"  target_ref 规范化: '{raw_target_ref}' -> '{normalized_target_ref}'")

        return StepPlan(
            step=step_num,
            action=action,
            description=step_dict.get("description", ""),
            target_ref=normalized_target_ref,
            params=params,
            wait_before=int(step_dict.get("wait_before", 0)),
            wait_after=int(step_dict.get("wait_after", 500)),
            retry=step_dict.get("retry", 1)
        )

    def _execute_step(
        self,
        step: StepPlan,
        executed_steps: List[StepPlan]
    ) -> StepResult:
        """
        执行单个步骤

        Args:
            step: 步骤计划
            executed_steps: 已执行的步骤列表

        Returns:
            StepResult 步骤执行结果
        """
        result = StepResult(step=step, status=StepStatus.PENDING)
        result.start_time = time.time()

        self._log(f"")
        self._log(f"{'='*50}")
        self._log(f"执行步骤 {step.step}: {step.action.value}")
        self._log(f"{'='*50}")
        self._log(f"  描述: {step.description}")
        if step.target_ref:
            self._log(f"  目标: {step.target_ref}")
        if step.params:
            self._log(f"  参数: {step.params}")

        # 执行前等待
        if step.wait_before > 0:
            time.sleep(step.wait_before / 1000)

        # 截取执行前的屏幕
        try:
            result.screenshot_before = self._capture_screenshot()
        except Exception as e:
            self._log(f"截图失败: {e}")

        # 重试循环
        for attempt in range(step.retry + 1):
            result.retry_count = attempt

            if attempt > 0:
                self._log(f"重试第 {attempt} 次...")
                time.sleep(0.5)

                # 如果是 input_text 重试，先清空输入框
                if step.action == ActionName.INPUT_TEXT:
                    self._log("清空输入框...")
                    self.adb.clear_text_field()
                    time.sleep(0.3)

            try:
                success = self._execute_action(step, result.screenshot_before)

                if success:
                    # 执行后等待
                    wait_time = step.wait_after / 1000 if step.wait_after else self.default_wait_after
                    time.sleep(wait_time)

                    # 截取执行后的屏幕（使用应用配置的等待时间）
                    result.screenshot_after = self._capture_screenshot()

                    # 验证结果
                    verify_result = self._verify_step(step, result.screenshot_before, result.screenshot_after)
                    result.verify_result = verify_result

                    # 检测到 loading 状态时，等待并重试验证
                    loading_retry_count = 0
                    max_loading_retries = 3
                    while (not verify_result.verified and
                           verify_result.blocker and
                           verify_result.blocker.type == BlockerType.LOADING and
                           loading_retry_count < max_loading_retries):
                        loading_retry_count += 1
                        self._log(f"检测到加载状态，等待 1.5 秒后重试验证 ({loading_retry_count}/{max_loading_retries})...")
                        time.sleep(1.5)
                        result.screenshot_after = self._capture_screenshot(wait_before=0)
                        verify_result = self._verify_step(step, result.screenshot_before, result.screenshot_after)
                        result.verify_result = verify_result

                    if verify_result.verified:
                        result.status = StepStatus.SUCCESS
                        break
                    elif verify_result.suggestion == SuggestionAction.DISMISS:
                        # 需要关闭弹窗
                        if verify_result.blocker:
                            self._handle_blocker(verify_result.blocker)
                            continue
                    elif verify_result.suggestion == SuggestionAction.SKIP:
                        result.status = StepStatus.SKIPPED
                        result.error_message = verify_result.suggestion_detail
                        break
                    elif verify_result.suggestion == SuggestionAction.ABORT:
                        result.status = StepStatus.FAILED
                        result.error_message = verify_result.suggestion_detail
                        break
                    else:
                        # 重试
                        result.error_message = verify_result.suggestion_detail or "验证未通过"
                else:
                    result.error_message = "动作执行失败"

            except Exception as e:
                result.error_message = str(e)
                self._log(f"执行异常: {e}")

        # 如果循环结束仍未成功
        if result.status == StepStatus.PENDING:
            result.status = StepStatus.FAILED
            if not result.error_message:
                result.error_message = f"达到最大重试次数 ({step.retry})"

        result.end_time = time.time()
        return result

    def _execute_step_fast(self, step: StepPlan) -> StepResult:
        """
        快速执行步骤（无验证）

        用于确定性步骤（launch_app, press_key, call 等）
        直接执行，不截图，不验证
        """
        result = StepResult(step=step, status=StepStatus.PENDING)
        result.start_time = time.time()

        try:
            success = self._execute_action(step, None)
            result.status = StepStatus.SUCCESS if success else StepStatus.FAILED

            # 简单等待
            strategy = get_step_strategy(step)
            time.sleep(strategy.wait_after_ms / 1000)

        except Exception as e:
            result.status = StepStatus.FAILED
            result.error_message = str(e)

        result.end_time = time.time()
        return result

    def _execute_step_with_strategy(
        self,
        step: StepPlan,
        strategy: StepStrategy,
        executed_steps: List[StepPlan]
    ) -> StepResult:
        """
        根据策略执行步骤

        根据步骤的复杂度决定：
        - 是否需要截图
        - 是否需要 AI 定位
        - 是否需要验证
        """
        result = StepResult(step=step, status=StepStatus.PENDING)
        result.start_time = time.time()

        # 只在需要时截图
        screenshot = None
        if strategy.need_screenshot_before:
            try:
                screenshot = self._capture_screenshot()
                result.screenshot_before = screenshot
            except Exception as e:
                self._log(f"截图失败: {e}")

        try:
            # 执行动作
            success = self._execute_action(step, screenshot)

            if success:
                # 根据策略决定等待时间
                time.sleep(strategy.wait_after_ms / 1000)

                # 根据策略决定是否验证
                if strategy.need_verification:
                    result.screenshot_after = self._capture_screenshot()
                    verify_result = self._verify_step(step, result.screenshot_before, result.screenshot_after)
                    result.verify_result = verify_result

                    # 检测到 loading 状态时，等待并重试验证
                    loading_retry_count = 0
                    max_loading_retries = 3
                    while (not verify_result.verified and
                           verify_result.blocker and
                           verify_result.blocker.type == BlockerType.LOADING and
                           loading_retry_count < max_loading_retries):
                        loading_retry_count += 1
                        self._log(f"检测到加载状态，等待 1.5 秒后重试验证 ({loading_retry_count}/{max_loading_retries})...")
                        time.sleep(1.5)
                        result.screenshot_after = self._capture_screenshot(wait_before=0)
                        verify_result = self._verify_step(step, result.screenshot_before, result.screenshot_after)
                        result.verify_result = verify_result

                    if verify_result.verified:
                        result.status = StepStatus.SUCCESS
                    else:
                        result.status = StepStatus.FAILED
                        result.error_message = verify_result.suggestion_detail or "验证失败"
                else:
                    # 不需要验证，直接成功
                    result.status = StepStatus.SUCCESS
            else:
                result.status = StepStatus.FAILED
                result.error_message = "执行失败"

        except Exception as e:
            self._log(f"执行异常: {e}")
            result.status = StepStatus.FAILED
            result.error_message = str(e)

        result.end_time = time.time()
        return result

    def _execute_action(
        self,
        step: StepPlan,
        screenshot: Optional[Image.Image]
    ) -> bool:
        """
        执行动作

        Args:
            step: 步骤计划
            screenshot: 当前屏幕截图（用于定位）

        Returns:
            是否执行成功
        """
        action = step.action

        if action == ActionName.TAP:
            return self._execute_tap(step, screenshot)
        elif action == ActionName.LONG_PRESS:
            return self._execute_long_press(step, screenshot)
        elif action == ActionName.SWIPE:
            return self._execute_swipe(step)
        elif action == ActionName.INPUT_TEXT:
            return self._execute_input_text(step)
        elif action == ActionName.PRESS_KEY:
            return self._execute_press_key(step)
        elif action == ActionName.WAIT:
            return self._execute_wait(step)
        elif action == ActionName.GO_HOME:
            return self._execute_go_home()
        elif action == ActionName.LAUNCH_APP:
            return self._execute_launch_app(step)
        elif action == ActionName.CALL:
            return self._execute_call(step)
        elif action == ActionName.OPEN_URL:
            return self._execute_open_url(step)
        elif action == ActionName.SCREENSHOT:
            return self._execute_screenshot(step)
        else:
            self._log(f"未知动作类型: {action}")
            return False

    def _execute_tap(self, step: StepPlan, screenshot: Optional[Image.Image]) -> bool:
        """执行点击"""
        coords = self._locate_with_fallback(step, screenshot)
        if coords is None:
            self._log("无法定位目标元素（已尝试 fallback）")
            return False

        x, y = coords
        self._log(f"点击 ({x}, {y})")
        return self.adb.tap(x, y)

    def _execute_long_press(self, step: StepPlan, screenshot: Optional[Image.Image]) -> bool:
        """执行长按"""
        coords = self._locate_with_fallback(step, screenshot)
        if coords is None:
            return False

        x, y = coords
        duration = step.params.get("duration", 1000)
        self._log(f"长按 ({x}, {y}) {duration}ms")
        return self.adb.long_press(x, y, duration)

    def _locate_with_fallback(
        self,
        step: StepPlan,
        screenshot: Optional[Image.Image],
        max_fallback_attempts: int = 3
    ) -> Optional[tuple]:
        """
        定位目标元素，如果失败则尝试 fallback

        流程:
        1. 尝试定位目标
        2. 如果失败且有 fallback，执行 fallback 动作
        3. 重新截图并再次定位
        4. 重复直到成功或达到最大尝试次数

        Args:
            step: 步骤计划
            screenshot: 当前屏幕截图
            max_fallback_attempts: 最大 fallback 尝试次数

        Returns:
            (x, y) 坐标，如果定位失败则返回 None
        """
        # 首次尝试定位
        coords = self._locate_target(step, screenshot)
        if coords is not None:
            return coords

        # 检查是否有 fallback
        if not step.fallback:
            self._log("定位失败，无 fallback 配置")
            return None

        self._log(f"定位失败，尝试 fallback: {step.fallback.get('description', step.fallback.get('action'))}")

        # fallback 循环
        for attempt in range(max_fallback_attempts):
            self._log(f"Fallback 尝试 {attempt + 1}/{max_fallback_attempts}")

            # 执行 fallback 动作
            fallback_success = self._execute_fallback(step.fallback)
            if not fallback_success:
                self._log("Fallback 动作执行失败")
                continue

            # 等待屏幕稳定
            time.sleep(0.5)

            # 重新截图
            new_screenshot = self._capture_screenshot()

            # 再次尝试定位
            coords = self._locate_target(step, new_screenshot)
            if coords is not None:
                self._log(f"Fallback 成功，定位到目标")
                return coords

            self._log(f"Fallback 后仍未找到目标")

        self._log(f"达到最大 fallback 尝试次数 ({max_fallback_attempts})")
        return None

    def _execute_fallback(self, fallback: Dict[str, Any]) -> bool:
        """
        执行 fallback 动作

        Args:
            fallback: fallback 配置 {"action": "swipe", "params": {"direction": "right"}, ...}

        Returns:
            是否执行成功
        """
        action = fallback.get("action", "")
        params = fallback.get("params", {})

        if action == "swipe":
            direction = params.get("direction", "up")
            self._log(f"Fallback: 滑动 {direction}")
            return self._execute_swipe_direction(direction)

        elif action == "tap":
            # fallback 的 tap 需要定位
            target_ref = fallback.get("target_ref")
            if target_ref:
                screenshot = self._capture_screenshot()
                # 创建临时 step 用于定位
                from ai.planner import StepPlan, ActionName
                temp_step = StepPlan(
                    step=0,
                    action=ActionName.TAP,
                    target_ref=target_ref,
                    description=fallback.get("description", "")
                )
                coords = self._locate_target(temp_step, screenshot)
                if coords:
                    return self.adb.tap(coords[0], coords[1])
            return False

        elif action == "press_key":
            keycode = params.get("keycode", 4)  # 默认 BACK
            self._log(f"Fallback: 按键 {keycode}")
            return self.adb.input_keyevent(keycode)

        elif action == "wait":
            duration = params.get("duration", 1000)
            self._log(f"Fallback: 等待 {duration}ms")
            time.sleep(duration / 1000)
            return True

        else:
            self._log(f"未知的 fallback 动作: {action}")
            return False

    def _execute_swipe_direction(self, direction: str) -> bool:
        """按方向执行滑动"""
        screen_width, screen_height = self._get_screen_size()

        if direction == "up":
            x = screen_width // 2
            y1, y2 = screen_height * 3 // 4, screen_height // 4
            return self.adb.swipe(x, y1, x, y2)
        elif direction == "down":
            x = screen_width // 2
            y1, y2 = screen_height // 4, screen_height * 3 // 4
            return self.adb.swipe(x, y1, x, y2)
        elif direction == "left":
            y = screen_height // 2
            x1, x2 = screen_width * 3 // 4, screen_width // 4
            return self.adb.swipe(x1, y, x2, y)
        elif direction == "right":
            y = screen_height // 2
            x1, x2 = screen_width // 4, screen_width * 3 // 4
            return self.adb.swipe(x1, y, x2, y)
        return False

    def _execute_swipe(self, step: StepPlan) -> bool:
        """执行滑动"""
        direction = step.params.get("direction", "up")
        self._log(f"滑动: {direction}")
        return self._execute_swipe_direction(direction)

    def _execute_input_text(self, step: StepPlan) -> bool:
        """
        执行文本输入

        如果指定了 target_ref，会先点击输入框激活它，然后再输入文本。
        输入前会自动清空输入框已有内容（使用全选+删除）。
        支持多种输入方式：
        1. ADBKeyboard broadcast（支持中文）
        2. Base64 编码方式（避免特殊字符问题）
        3. ADB input text（仅英文）
        """
        text = step.params.get("text", "")
        if not text:
            self._log("输入文本为空")
            return False

        # 如果有 target_ref，先点击输入框激活
        if step.target_ref:
            self._log(f"先点击输入框: {step.target_ref}")
            screenshot = self._capture_screenshot()
            coords = self._locate_target(step, screenshot)

            if coords:
                x, y = coords
                self._log(f"点击输入框 ({x}, {y})")
                self.adb.tap(x, y)
                time.sleep(0.8)  # 等待输入框激活和键盘弹出
            else:
                self._log(f"无法定位输入框，尝试直接输入")

        # 清空输入框已有内容（全选 + 删除）
        self._log("清空输入框内容")
        self._clear_input_field()

        self._log(f"输入文本: {text}")

        # 检测是否包含中文或特殊字符
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
        has_special = any(c in text for c in ' ()[]{}!@#$%^&*')

        if has_chinese or has_special:
            self._log("检测到中文或特殊字符，使用中文输入方法")

            # 检查 ADBKeyboard 是否可用
            if self.adb.is_adbkeyboard_installed():
                current_ime = self.adb.get_current_ime()
                self._log(f"当前输入法: {current_ime}")

                # 如果当前不是 ADBKeyboard，尝试切换
                if current_ime and "adbkeyboard" not in current_ime.lower():
                    self._log("切换到 ADBKeyboard")
                    self.adb.setup_adbkeyboard()
                    time.sleep(0.3)

            # 使用中文输入方法
            if self.adb.input_text_chinese(text):
                self._log("中文文本输入成功")
                return True

            # 如果中文输入失败，尝试只输入 ASCII 部分
            self._log("中文输入失败，尝试只输入 ASCII 部分")
            ascii_text = ''.join(c for c in text if ord(c) < 128 and c not in ' ')
            if ascii_text:
                self._log(f"输入 ASCII 部分: {ascii_text}")
                return self.adb.input_text(ascii_text)

            self._log("无法输入中文文本，请确保安装了 ADBKeyboard")
            self._log("下载地址: https://github.com/nickchan0/ADBKeyBoard/releases")
            return False
        else:
            return self.adb.input_text(text)

    def _execute_press_key(self, step: StepPlan) -> bool:
        """执行按键"""
        keycode = step.params.get("keycode")
        if keycode is None:
            self._log("未指定按键码")
            return False

        # 检查是否是"返回首页"类型的操作
        if keycode == 4 and self._is_back_to_home_step(step):
            return self._execute_back_to_home()

        self._log(f"按键: {keycode}")
        return self.adb.input_keyevent(keycode)

    def _is_back_to_home_step(self, step: StepPlan) -> bool:
        """判断步骤是否是返回首页/主页操作"""
        home_keywords = ["首页", "主页", "主界面", "聊天列表", "微信主", "返回微信"]
        description = step.description or ""
        for kw in home_keywords:
            if kw in description:
                return True
        return False

    def _execute_back_to_home(self, max_attempts: int = 6) -> bool:
        """
        返回应用首页

        通过循环按返回键，直到左上角没有返回按钮为止。
        使用 OpenCV 检测返回按钮，快速且可靠。

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功返回首页
        """
        self._log("执行返回首页（循环检测返回按钮）")

        for attempt in range(max_attempts):
            # 截图检测返回按钮
            screenshot = self._capture_screenshot()
            screenshot_bytes = io.BytesIO()
            screenshot.save(screenshot_bytes, format='PNG')
            screenshot_bytes = screenshot_bytes.getvalue()

            # 尝试找返回按钮（使用模块的参考图）
            back_button_found = False
            if self._current_handler:
                back_image_paths = self._current_handler.get_image_variants("wechat_back")
                if back_image_paths:
                    from core.hybrid_locator import LocateStrategy
                    result = self.hybrid_locator.locate_with_variants(
                        screenshot_bytes,
                        back_image_paths,
                        strategy=LocateStrategy.OPENCV_ONLY  # 只用 OpenCV，快速
                    )
                    back_button_found = result.success

            if not back_button_found:
                self._log(f"未检测到返回按钮，已到达首页 (尝试 {attempt} 次)")
                return True

            # 还有返回按钮，继续按返回
            self._log(f"检测到返回按钮，按返回键 (第 {attempt + 1} 次)")
            self.adb.press_back()
            time.sleep(1.0)  # 等待页面切换动画完成

        self._log(f"达到最大尝试次数 ({max_attempts})，可能未完全返回首页")
        return True  # 即使没完全返回，也继续执行

    def _clear_input_field(self):
        """
        清空当前输入框内容

        使用移动到末尾 + 连续删除的方式。
        不需要 AI 判断输入框是否有内容，直接清空。
        """
        # KEYCODE_MOVE_END = 123, KEYCODE_DEL = 67

        # 移动到末尾
        self.adb.input_keyevent(123)
        time.sleep(0.03)

        # 连续删除 30 个字符（足够清空大部分搜索框/输入框）
        del_keys = ["67"] * 30
        self.adb._run_adb("shell", "input", "keyevent", *del_keys)
        time.sleep(0.05)

    def _execute_wait(self, step: StepPlan) -> bool:
        """执行等待"""
        duration = step.params.get("duration", 1000)
        self._log(f"等待 {duration}ms")
        time.sleep(duration / 1000)
        return True

    def _execute_go_home(self) -> bool:
        """
        返回桌面首页

        连续按两次 HOME 键，确保从任何应用回到桌面首页
        """
        self._log("返回桌面首页（连续两次 HOME）")

        # 第一次 HOME
        self.adb.press_home()
        time.sleep(0.3)

        # 第二次 HOME
        self.adb.press_home()
        time.sleep(0.5)

        return True

    def _execute_launch_app(self, step: StepPlan) -> bool:
        """
        直接启动 App

        使用 ADB 命令直接启动应用，无需在桌面查找图标。
        先强制停止应用，确保从首页干净状态启动。
        """
        package = step.params.get("package", "")

        if not package:
            # 尝试从 target_ref 解析包名
            if step.target_ref:
                ref_name = step.target_ref
                # 从 assets 获取包名
                for category in ["icons"]:
                    if ref_name in self.assets.index.get(category, {}):
                        info = self.assets.index[category][ref_name]
                        package = info.get("package", "")
                        break

                # 尝试别名解析
                if not package:
                    resolved = self.assets.resolve_alias(step.target_ref)
                    if resolved:
                        for category in ["icons"]:
                            if resolved in self.assets.index.get(category, {}):
                                info = self.assets.index[category][resolved]
                                package = info.get("package", "")
                                break

        if not package:
            self._log(f"无法获取包名，target_ref: {step.target_ref}")
            return False

        activity = step.params.get("activity", "")

        # 第一次启动（热启动，快）
        self._log(f"启动 App: {package}")
        if activity:
            cmd = f"am start -n {package}/{activity}"
        else:
            cmd = f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
        self.adb._run_adb("shell", *cmd.split())
        time.sleep(0.8)

        # 连续按返回键，确保回到首页（或退出应用）
        self._log("按返回键回到首页...")
        for _ in range(4):
            self.adb.press_back()
            time.sleep(0.2)

        # 再次启动，确保在首页前台
        time.sleep(0.3)
        result = self.adb._run_adb("shell", *cmd.split())
        time.sleep(1)

        return result.returncode == 0

    def _execute_call(self, step: StepPlan) -> bool:
        """
        直接拨打电话

        使用 ADB 的 am start 命令直接拨打电话。
        """
        phone_number = step.params.get("number", "")

        if not phone_number:
            self._log("未指定电话号码")
            return False

        # 清理电话号码（去除空格、横杠等）
        phone_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')

        self._log(f"拨打电话: {phone_number}")

        # 使用 CALL intent 直接拨打
        cmd = f"am start -a android.intent.action.CALL -d tel:{phone_number}"
        result = self.adb._run_adb("shell", *cmd.split())
        time.sleep(1)

        return result.returncode == 0

    def _execute_open_url(self, step: StepPlan) -> bool:
        """
        打开网址

        使用 ADB 的 am start 命令在默认浏览器中打开网址。
        """
        url = step.params.get("url", "")

        if not url:
            self._log("未指定网址")
            return False

        # 确保 URL 有协议前缀
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        self._log(f"打开网址: {url}")

        cmd = f"am start -a android.intent.action.VIEW -d {url}"
        result = self.adb._run_adb("shell", *cmd.split())
        time.sleep(1)

        return result.returncode == 0

    def _execute_screenshot(self, step: StepPlan) -> bool:
        """
        截屏保存

        保存当前屏幕截图到指定路径。
        """
        import os
        from datetime import datetime

        # 获取保存路径
        save_path = step.params.get("save_path", "")

        if not save_path:
            # 默认保存到 temp 目录，使用时间戳命名
            temp_dir = Path(__file__).parent.parent / "temp"
            temp_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = str(temp_dir / f"screenshot_{timestamp}.png")

        # 截图
        screenshot = self._capture_screenshot()

        # 保存
        try:
            screenshot.save(save_path)
            self._log(f"截图已保存: {save_path}")
            return True
        except Exception as e:
            self._log(f"截图保存失败: {e}")
            return False

    def _locate_target(
        self,
        step: StepPlan,
        screenshot: Optional[Image.Image]
    ) -> Optional[tuple]:
        """
        定位目标元素

        使用混合定位策略：
        1. 先尝试模块特定的参考图（OpenCV）
        2. 再尝试全局参考图（OpenCV）
        3. 最后回退到 AI 视觉定位

        Args:
            step: 步骤计划
            screenshot: 当前屏幕截图

        Returns:
            (x, y) 坐标，如果定位失败则返回 None
        """
        if screenshot is None:
            screenshot = self._capture_screenshot()

        target_ref = step.target_ref
        target_type = step.target_type

        self._log(f"===== 定位目标 =====")
        self._log(f"  原始目标: {target_ref}")

        # 规范化 target_ref，将动态描述映射到参考图名称
        if target_ref:
            normalized_ref = self._normalize_target_ref(target_ref)
            if normalized_ref != target_ref:
                self._log(f"  规范化后: {normalized_ref}")
                target_ref = normalized_ref

        self._log(f"  类型: {target_type.value if target_type else 'N/A'}")
        self._log(f"  描述: {step.description}")

        if target_ref is None:
            self._log("  结果: 未指定目标参考，跳过定位")
            return None

        # 动态描述 - 使用 AI 定位
        if target_ref.startswith("dynamic:"):
            description = target_ref[8:]  # 去掉 "dynamic:" 前缀
            self._log(f"  模式: 动态描述定位")
            self._log(f"  描述内容: '{description}'")
            self._log(f"  -> 调用 AI 分析截图...")
            ai_start = time.time()
            result = self.locator.find_element(screenshot, description)
            ai_elapsed = (time.time() - ai_start) * 1000
            if result:
                self._log(f"  结果: 找到 ({result[0]}, {result[1]})")
            else:
                self._log(f"  结果: 未找到")
            self._log(f"  ⏱ AI定位: {ai_elapsed:.0f}ms")
            return result

        # 参考图匹配 - 使用混合定位器
        self._log(f"  模式: 混合定位 (OpenCV + AI)")

        # 1. 尝试模块特定的参考图（支持多变体）
        ref_image_paths = []
        if self._current_handler:
            ref_image_paths = self._current_handler.get_image_variants(target_ref)
            if ref_image_paths:
                if len(ref_image_paths) > 1:
                    self._log(f"  使用模块参考图: {ref_image_paths[0].name} (+{len(ref_image_paths)-1} 变体)")
                else:
                    self._log(f"  使用模块参考图: {ref_image_paths[0].name}")
                self._log(f"  参考图完整路径: {ref_image_paths[0]}")
                if ref_image_paths[0].exists():
                    self._log(f"  参考图文件存在: 是")
                else:
                    self._log(f"  参考图文件存在: 否！请检查路径！")

        # 2. 尝试全局参考图
        if not ref_image_paths:
            ref_image_path = self.assets.get_path(target_ref)
            if ref_image_path is None:
                # 尝试别名
                self._log(f"  尝试别名解析: '{target_ref}'")
                resolved = self.assets.resolve_alias(target_ref)
                if resolved:
                    ref_image_path = self.assets.get_path(resolved)

            if ref_image_path:
                ref_image_paths = [ref_image_path]

        # 3. 使用混合定位器
        if ref_image_paths:
            self._log(f"  -> 使用混合定位器 (OpenCV 优先)...")

            # 将截图转换为字节
            screenshot_bytes = io.BytesIO()
            screenshot.save(screenshot_bytes, format='PNG')
            screenshot_bytes = screenshot_bytes.getvalue()

            # 调试：保存当前截图用于对比
            debug_screenshot_path = ref_image_paths[0].parent / "debug_screenshot.png"
            screenshot.save(debug_screenshot_path)
            self._log(f"  调试: 截图已保存到 {debug_screenshot_path}")

            # 调用混合定位器（支持多变体）
            locate_start = time.time()
            if len(ref_image_paths) == 1:
                locate_result = self.hybrid_locator.locate(
                    screenshot_bytes,
                    ref_image_paths[0],
                    strategy=LocateStrategy.OPENCV_FIRST
                )
            else:
                locate_result = self.hybrid_locator.locate_with_variants(
                    screenshot_bytes,
                    ref_image_paths,
                    strategy=LocateStrategy.OPENCV_FIRST
                )
            locate_elapsed = (time.time() - locate_start) * 1000

            if locate_result.success:
                self._log(f"  方法: {locate_result.method_used}")
                self._log(f"  置信度: {locate_result.confidence:.3f}")
                if locate_result.details.get("matched_variant"):
                    self._log(f"  匹配变体: {locate_result.details['matched_variant']}")
                if locate_result.fallback_used:
                    self._log(f"  (使用了回退)")
                self._log(f"  结果: 找到 ({locate_result.center_x}, {locate_result.center_y})")
                self._log(f"  ⏱ 定位耗时: {locate_elapsed:.0f}ms")
                return (locate_result.center_x, locate_result.center_y)
            else:
                self._log(f"  混合定位失败: {locate_result.details} ({locate_elapsed:.0f}ms)")

        # 4. 回退到 AI 描述定位
        self._log(f"  回退到 AI 描述定位")
        self._log(f"  描述内容: '{step.description}'")
        self._log(f"  -> 调用 AI 分析截图...")
        ai_start = time.time()
        result = self.locator.find_element(screenshot, step.description)
        ai_elapsed = (time.time() - ai_start) * 1000
        if result:
            self._log(f"  结果: 找到 ({result[0]}, {result[1]})")
        else:
            self._log(f"  结果: 未找到")
        self._log(f"  ⏱ AI定位: {ai_elapsed:.0f}ms")
        return result

    def _verify_step(
        self,
        step: StepPlan,
        before_screenshot: Optional[Image.Image],
        after_screenshot: Image.Image
    ) -> VerifyResult:
        """
        验证步骤执行结果

        Args:
            step: 步骤计划
            before_screenshot: 执行前截图
            after_screenshot: 执行后截图

        Returns:
            VerifyResult 验证结果
        """
        # 某些动作不需要验证，直接返回成功
        skip_verify_actions = [
            ActionName.WAIT,        # 等待动作不需要屏幕变化
            ActionName.GO_HOME,     # 可能已在桌面
        ]

        # PRESS_KEY 需要特殊处理：
        # - 返回键 (keycode 4) 有导航目的时需要验证
        # - 其他按键通常不需要验证
        if step.action == ActionName.PRESS_KEY:
            keycode = step.params.get("keycode", 4)
            has_navigation_goal = self._step_has_navigation_goal(step)

            if keycode == 4 and has_navigation_goal:
                # 返回键有明确导航目标，需要验证是否到达目的地
                self._log(f"返回键有导航目标，需要验证")
            else:
                # 其他按键不需要验证
                self._log(f"跳过验证 ({step.action.value} 动作)")
                return VerifyResult(
                    verified=True,
                    confidence=1.0,
                    current_state="动作已执行",
                    matches_expected=True,
                    screen_changed=False,
                    change_description="无需验证",
                    blocker=None,
                    suggestion=SuggestionAction.CONTINUE,
                    suggestion_detail=""
                )

        if step.action in skip_verify_actions:
            self._log(f"跳过验证 ({step.action.value} 动作)")
            return VerifyResult(
                verified=True,
                confidence=1.0,
                current_state="动作已执行",
                matches_expected=True,
                screen_changed=False,
                change_description="无需验证",
                blocker=None,
                suggestion=SuggestionAction.CONTINUE,
                suggestion_detail=""
            )

        # 某些动作使用简化验证（只检查是否出错，不要求屏幕变化）
        lenient_verify_actions = [
            ActionName.LAUNCH_APP,  # 应用可能已打开
            ActionName.OPEN_URL,    # 页面可能已加载
            ActionName.CALL,        # 通话界面
        ]

        if step.action in lenient_verify_actions and not step.verify_ref and not step.success_condition:
            self._log(f"使用宽松验证 ({step.action.value} 动作)")
            # 只检查是否有明显错误
            return self.verifier.verify_with_description(
                after_screenshot,
                f"检查屏幕是否显示错误或异常弹窗（如果没有错误则视为成功）",
                None  # 不比较前后截图
            )

        # 如果有验证参考图
        if step.verify_ref:
            ref_image = self.assets.get_image(step.verify_ref)
            if ref_image:
                self._log(f"使用参考图验证: {step.verify_ref}")
                return self.verifier.verify_with_reference(
                    ref_image,
                    after_screenshot,
                    step.success_condition
                )

        # 使用成功条件描述验证
        if step.success_condition:
            self._log(f"使用描述验证: {step.success_condition}")
            return self.verifier.verify_with_description(
                after_screenshot,
                step.success_condition,
                before_screenshot
            )

        # 对于 input_text，验证输入的文本是否正确
        if step.action == ActionName.INPUT_TEXT:
            expected_text = step.params.get("text", "")
            self._log(f"验证输入文本: 期望 '{expected_text}'")
            verify_start = time.time()
            result = self.verifier.verify_with_description(
                after_screenshot,
                f"检查输入框中是否正确显示文本 '{expected_text}'（注意：不能重复、不能缺少字符）",
                before_screenshot
            )
            self._log(f"⏱ AI验证: {(time.time() - verify_start) * 1000:.0f}ms")
            return result

        # 默认验证：结合步骤描述检查是否达到预期状态
        # 对于导航类步骤，需要严格验证是否到达目的地
        has_nav_goal = self._step_has_navigation_goal(step)

        if has_nav_goal:
            # 导航步骤：严格验证是否到达目的地
            self._log("使用导航目标验证")
            verify_prompt = (
                f"步骤意图: {step.description}\n"
                f"请验证当前屏幕是否达到了上述意图描述的目标状态。\n"
                f"- 如果是'返回首页/主页'，需要看到微信的主聊天列表界面\n"
                f"- 如果是'进入某个页面'，需要看到该页面的标志性元素\n"
                f"- 如果当前仍在其他页面（如联系人详情、设置页等），应该判定为未达到目标\n"
                f"只有真正达到目标状态才算验证通过。"
            )
        else:
            # 非导航步骤：检查屏幕是否有预期变化
            self._log("使用变化检测验证")
            verify_prompt = f"执行 {step.action.value} ({step.description}) 后屏幕有预期变化"

        verify_start = time.time()
        result = self.verifier.verify_with_description(
            after_screenshot,
            verify_prompt,
            before_screenshot
        )
        verify_elapsed = (time.time() - verify_start) * 1000
        self._log(f"⏱ AI验证: {verify_elapsed:.0f}ms")

        # 如果导航验证失败，建议重新规划
        if has_nav_goal and not result.verified:
            self._log("导航未达到目标，建议重新规划")
            result.suggestion = SuggestionAction.REPLAN
            result.suggestion_detail = f"未能到达目标: {step.description}"

        return result

    def _step_has_navigation_goal(self, step: StepPlan) -> bool:
        """
        判断步骤是否有明确的导航目标

        用于确定返回键操作是否需要验证。
        如果步骤描述中包含导航相关关键词，说明有明确目标。

        Args:
            step: 步骤计划

        Returns:
            是否有导航目标
        """
        # 导航相关关键词
        navigation_keywords = [
            "回到", "返回", "进入", "打开", "到达",
            "首页", "主页", "主界面", "聊天列表",
            "退出", "关闭", "离开"
        ]

        description = step.description or ""
        success_condition = step.success_condition or ""
        combined = description + success_condition

        for keyword in navigation_keywords:
            if keyword in combined:
                return True

        return False

    def _handle_blocker(self, blocker) -> bool:
        """
        处理阻挡物（弹窗等）

        Args:
            blocker: Blocker 对象

        Returns:
            是否成功处理
        """
        self._log(f"处理阻挡物: {blocker.type.value} - {blocker.description}")

        if blocker.dismiss_suggestion is None:
            # 默认尝试按返回键
            self._log("尝试按返回键关闭")
            self.adb.press_back()
            time.sleep(0.5)
            return True

        suggestion = blocker.dismiss_suggestion

        if suggestion.action == "tap":
            # 需要定位并点击
            screenshot = self._capture_screenshot()
            target = suggestion.target_ref

            if target and target.startswith("dynamic:"):
                coords = self.locator.find_element(screenshot, target[8:])
            else:
                ref_image = self.assets.get_image(target) if target else None
                if ref_image:
                    coords = self.locator.find_element_by_image(ref_image, screenshot)
                else:
                    coords = self.locator.find_element(screenshot, suggestion.description)

            if coords:
                self._log(f"点击关闭按钮 ({coords[0]}, {coords[1]})")
                self.adb.tap(coords[0], coords[1])
                time.sleep(0.5)
                return True

        elif suggestion.action == "press_key":
            keycode = suggestion.keycode or 4  # 默认 BACK
            self._log(f"按键 {keycode} 关闭")
            self.adb.input_keyevent(keycode)
            time.sleep(0.5)
            return True

        elif suggestion.action == "swipe":
            # 滑动关闭（如下滑关闭通知）
            screen_width, screen_height = self._get_screen_size()
            self.adb.swipe(
                screen_width // 2, screen_height // 4,
                screen_width // 2, screen_height * 3 // 4
            )
            time.sleep(0.5)
            return True

        return False

    def run_simple(self, task: str) -> bool:
        """
        简单执行模式 - 返回成功/失败

        Args:
            task: 任务描述

        Returns:
            是否成功
        """
        result = self.run(task)
        return result.status == TaskStatus.SUCCESS
