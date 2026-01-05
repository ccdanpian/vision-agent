# 工作流执行器

WorkflowExecutor 负责实际执行工作流步骤，包括界面检测、导航和恢复。

## 预置流程（复位机制）

**这是工作流执行的关键设计**：在执行任何正式任务前，系统会先执行一个"预置流程"，确保应用处于已知的初始状态（通常是首页）。

### 为什么需要预置流程？

1. **状态不确定性**：用户可能在任意界面启动任务（聊天窗口、设置页、朋友圈等）
2. **提高可靠性**：从已知状态开始执行，避免步骤定位失败
3. **简化工作流设计**：工作流只需假设从首页开始，无需处理各种起始状态

### 预置流程执行顺序

```
execute_workflow() 被调用
        │
        ▼
┌─────────────────────────────────┐
│  _ensure_app_running()          │  ← 预置流程入口
│  1. 启动应用（确保在前台）        │
│  2. 调用 _ensure_at_home_screen()│
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│  _ensure_at_home_screen()       │  ← 复位循环
│  循环最多 N 次：                 │
│  1. 检测是否能看到首页标识       │
│  2. 如果是 → 点击进入，返回成功  │
│  3. 如果否 → 点击返回/取消按钮   │
│  4. 重复直到成功或超过次数       │
└─────────────────────────────────┘
        │
        ▼
    正式任务步骤开始执行
```

### 复位策略

预置流程使用**并行检测 + 优先级点击**策略：

| 检测目标 | 找到后的动作 | 优先级 |
|----------|-------------|--------|
| 首页标识（如底部Tab） | 点击进入，返回成功 | 最高 |
| 取消按钮 | 点击关闭弹窗 | 中 |
| 返回按钮 | 点击返回上一级 | 中 |
| 都没找到 | 按物理返回键 | 最低 |

## 初始化

```python
# apps/wechat/workflow_executor.py 实际代码

class WorkflowExecutor:
    """工作流执行器"""

    def __init__(self, task_runner, handler):
        """
        初始化执行器

        Args:
            task_runner: TaskRunner 实例（用于执行操作）
            handler: WeChatHandler 实例（用于获取参考图）
        """
        self.runner = task_runner
        self.handler = handler
        self._logger = None
        self._max_back_presses = 5  # 最多按返回键次数
        self._back_press_interval = 500  # 返回键间隔 ms
```

## 确保应用运行

```python
# apps/wechat/workflow_executor.py 实际代码

def _ensure_wechat_running(self) -> bool:
    """
    确保微信已打开并在前台，且处于首页状态

    流程：
    1. 检查/启动微信
    2. 确保回到首页（消息Tab页面）

    Returns:
        是否成功确保微信在首页
    """
    WECHAT_PACKAGE = "com.tencent.mm"

    self._log("")
    self._log("+" + "=" * 40 + "+")
    self._log("|       【预置流程】正式任务前准备        |")
    self._log("+" + "=" * 40 + "+")
    self._log("")
    self._log("[预置] 步骤0: 使用系统指令启动微信")

    # 无条件使用系统指令启动微信（确保微信在前台）
    self._log("  执行启动微信指令...")
    self.runner.adb.start_app(WECHAT_PACKAGE)
    time.sleep(config.OPERATION_DELAY * 4)  # 等待微信启动

    # 验证微信是否启动成功
    current_app = self.runner.adb.get_current_app()
    self._log(f"  当前前台应用: {current_app}")

    if current_app != WECHAT_PACKAGE:
        if current_app is None:
            self._log("  无法检测前台应用，通过截图验证...")
            time.sleep(config.OPERATION_DELAY * 2)
            current_screen = self.detect_screen()
            if current_screen == WeChatScreen.UNKNOWN:
                self._log(f"  X 微信启动失败")
                return False
            else:
                self._log(f"  V 检测到微信界面: {current_screen.value}")
        else:
            self._log(f"  X 微信启动失败，当前应用: {current_app}")
            return False
    else:
        self._log("  V 微信已在前台")

    # === 确保回到首页（消息Tab页面）===
    return self._ensure_at_home_screen()
```

## 确保在首页

```python
# apps/wechat/workflow_executor.py 实际代码

def _ensure_at_home_screen(self, max_attempts: int = 5) -> bool:
    """
    确保微信处于首页（消息页面）

    流程：
    1. 用 wechat_home_button 检测是否能看到底部消息Tab
    2. 如果能看到，直接返回成功
    3. 如果看不到，优先点击取消按钮，其次点击返回按钮
    4. 重复直到能看到消息Tab

    Args:
        max_attempts: 最大尝试次数

    Returns:
        是否成功回到首页
    """
    self._log("")
    self._log("[预置] 步骤1: 确保微信在消息页面")

    for attempt in range(max_attempts):
        self._log(f"  检测第 {attempt + 1}/{max_attempts} 次...")
        # 使用裁剪截图（去除状态栏和导航栏）
        screenshot, top_offset = self.runner._capture_screenshot_cropped()
        screenshot_bytes = self._image_to_bytes(screenshot)

        # 获取所有需要检测的目标
        home_btn_paths = self.handler.get_image_variants("wechat_home_button")
        cancel_paths = self.handler.get_image_variants("wechat_cancel_button")
        back_paths = self.handler.get_image_variants("wechat_back")

        # 构建并行检测目标
        targets = {}
        if home_btn_paths:
            targets["home_button"] = home_btn_paths
        if cancel_paths:
            targets["cancel_button"] = cancel_paths
        if back_paths:
            targets["back_button"] = back_paths

        if not targets:
            self._log(f"  无可用参考图，按物理返回键")
            self.runner.adb.press_back()
            time.sleep(config.OPERATION_DELAY * 2)
            continue

        # 并行检测多个目标
        results = self.runner.hybrid_locator.locate_multiple_parallel(
            screenshot_bytes, targets
        )

        # 检查是否能看到消息Tab
        home_result = results.get("home_button")
        if home_result and home_result.success:
            # 点击 home_button 确保进入聊天列表页（坐标需要加上 top_offset）
            tap_y = home_result.center_y + top_offset
            self._log(f"  检测到消息Tab，点击进入聊天界面 ({home_result.center_x}, {tap_y})")
            self.runner.adb.tap(home_result.center_x, tap_y)
            time.sleep(config.OPERATION_DELAY * 2)
            self._log(f"  V 已进入消息页面")
            return True

        self._log(f"  未检测到消息Tab，尝试返回...")

        # 优先点击取消按钮
        cancel_result = results.get("cancel_button")
        if cancel_result and cancel_result.success:
            tap_y = cancel_result.center_y + top_offset
            self._log(f"  找到取消按钮，点击 ({cancel_result.center_x}, {tap_y})")
            self.runner.adb.tap(cancel_result.center_x, tap_y)
            time.sleep(config.OPERATION_DELAY * 2)
            continue

        # 其次点击返回按钮
        back_result = results.get("back_button")
        if back_result and back_result.success:
            tap_y = back_result.center_y + top_offset
            self._log(f"  找到返回按钮，点击 ({back_result.center_x}, {tap_y})")
            self.runner.adb.tap(back_result.center_x, tap_y)
            time.sleep(config.OPERATION_DELAY * 2)
            continue

        # 都没找到，等待后重试
        self._log(f"  未找到取消/返回按钮，等待后重试...")
        time.sleep(config.OPERATION_DELAY * 2)

    self._log(f"  X 无法回到消息页面")
    return False
```

## 界面检测

```python
# apps/wechat/workflow_executor.py 实际代码

def detect_screen(self, screenshot: Optional[Image.Image] = None) -> WeChatScreen:
    """
    检测当前界面

    Args:
        screenshot: 屏幕截图，如果为 None 则自动截取

    Returns:
        当前界面类型
    """
    if screenshot is None:
        screenshot = self.runner._capture_screenshot()

    self._log("检测当前界面...")

    # 按优先级检测各界面（首页最优先）
    detection_order = [
        WeChatScreen.HOME,
        WeChatScreen.CONTACTS,
        WeChatScreen.DISCOVER,
        WeChatScreen.ME,
        WeChatScreen.CHAT,
        WeChatScreen.MOMENTS,
        WeChatScreen.SEARCH,
    ]

    # 转换截图为 bytes（hybrid_locator 需要）
    screenshot_bytes = self._image_to_bytes(screenshot)

    for screen in detection_order:
        # 获取主参考图和备用参考图
        ref_names = []
        if screen in SCREEN_DETECT_REFS:
            ref_names.append(SCREEN_DETECT_REFS[screen])
        if screen in SCREEN_DETECT_REFS_FALLBACK:
            ref_names.append(SCREEN_DETECT_REFS_FALLBACK[screen])

        for ref_name in ref_names:
            # 获取参考图路径
            ref_path = self.handler.get_image_path(ref_name)
            if not ref_path or not ref_path.exists():
                self._log(f"  参考图不存在: {ref_name}")
                continue

            # 使用 OpenCV 检测
            try:
                result = self.runner.hybrid_locator.locate(
                    screenshot_bytes,
                    ref_path,
                    LocateStrategy.OPENCV_FIRST
                )
                if result.success:
                    self._log(f"  V 检测到界面: {screen.value} (匹配: {ref_name})")
                    return screen
                else:
                    self._log(f"  尝试 {ref_name}: 未匹配")
            except Exception as e:
                self._log(f"  检测 {screen.value} 失败: {e}")

    self._log("  X 未识别的界面")
    return WeChatScreen.UNKNOWN
```

## 带 AI 回退的智能导航

```python
# apps/wechat/workflow_executor.py 实际代码

def navigate_to_home_with_ai_fallback(self, max_attempts: int = 5) -> Dict[str, Any]:
    """
    导航回首页，带 AI 回退

    流程：
    1. 先尝试预定义方法
    2. 如果失败，让 AI 分析当前界面并尝试导航

    Args:
        max_attempts: 预定义方法的最大尝试次数

    Returns:
        {"success": bool, "method": str, "message": str}
    """
    # 1. 先尝试预定义方法
    if self.navigate_to_home(max_attempts):
        return {
            "success": True,
            "method": "predefined",
            "message": "预定义方法成功导航到首页"
        }

    self._log("  预定义方法失败，尝试 AI 辅助导航...")

    # 2. 使用 AI 分析并尝试导航
    for ai_attempt in range(3):
        screenshot = self.runner._capture_screenshot()

        # 让 AI 分析当前界面并给出导航建议
        ai_result = self._ai_navigate_step(screenshot, ai_attempt + 1)

        if ai_result["at_home"]:
            self._log(f"  V AI 辅助成功到达首页 (尝试 {ai_attempt + 1} 次)")
            return {
                "success": True,
                "method": "ai_assisted",
                "message": f"AI 辅助导航成功 (尝试 {ai_attempt + 1} 次)"
            }

        if not ai_result["action_taken"]:
            # AI 无法识别或无法给出建议
            self._log(f"  AI 无法继续导航: {ai_result['message']}")
            break

        time.sleep(0.5)

    # 最终验证
    current_screen = self.detect_screen()
    if current_screen == WeChatScreen.HOME:
        return {
            "success": True,
            "method": "ai_assisted",
            "message": "AI 辅助导航成功"
        }

    return {
        "success": False,
        "method": "failed",
        "message": f"预定义方法和 AI 辅助都无法导航到首页，当前界面: {current_screen.value}"
    }
```

## 工作流执行

```python
# apps/wechat/workflow_executor.py 实际代码

def execute_workflow(
    self,
    workflow: Workflow,
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    执行工作流

    Args:
        workflow: 工作流定义
        params: 工作流参数

    Returns:
        执行结果 {"success": bool, "message": str, "data": Any}
    """
    self._log(f"=== 执行工作流: {workflow.name} ===")
    self._log(f"  描述: {workflow.description}")
    self._log(f"  参数: {params}")

    # 检查必需参数
    missing_params = [p for p in workflow.required_params if p not in params]
    if missing_params:
        return {
            "success": False,
            "message": f"缺少必需参数: {missing_params}",
            "data": None
        }

    # 合并默认参数
    full_params = {**workflow.optional_params, **params}

    # 0. 确保微信已打开并在前台
    if not self._ensure_wechat_running():
        return {
            "success": False,
            "message": "无法启动微信",
            "data": None
        }

    # 1. 检测当前界面
    current_screen = self.detect_screen()
    self._log(f"  当前界面: {current_screen.value}")
    self._log(f"  有效起点: {[s.value for s in workflow.valid_start_screens]}")

    # 2. 确保在有效起始界面
    need_navigate = False

    if current_screen == WeChatScreen.UNKNOWN:
        self._log(f"  未识别界面，需要先回首页")
        need_navigate = True
    elif current_screen not in workflow.valid_start_screens:
        self._log(f"  不在有效起始界面，需要先回首页")
        need_navigate = True
    elif current_screen != WeChatScreen.HOME and WeChatScreen.HOME in workflow.valid_start_screens:
        # 虽然在有效起点（如 CHAT），但首页也是有效起点，优先回首页
        self._log(f"  当前在 {current_screen.value}，但优先从首页开始")
        need_navigate = True

    if need_navigate:
        self._log(f"  === 导航到首页（带 AI 回退）===")
        nav_result = self.navigate_to_home_with_ai_fallback()

        if not nav_result["success"]:
            self._log(f"  X 导航失败: {nav_result['message']}")
            return {
                "success": False,
                "message": nav_result["message"],
                "data": None
            }

        self._log(f"  V 已确认在首页 (方法: {nav_result['method']})")

    # 3. 执行工作流步骤
    for i, step in enumerate(workflow.steps):
        step_desc = self._render_template(step.description, full_params)
        self._log(f"  步骤 {i + 1}: {step_desc}")

        result = self._execute_step(step, full_params)
        if not result["success"]:
            self._log(f"  X 步骤失败: {result['message']}")

            # 尝试恢复
            if self._try_recover(step, full_params):
                # 重试当前步骤
                result = self._execute_step(step, full_params)
                if not result["success"]:
                    return {
                        "success": False,
                        "message": f"步骤 {i + 1} 失败: {result['message']}",
                        "data": None
                    }
            else:
                return {
                    "success": False,
                    "message": f"步骤 {i + 1} 失败且无法恢复: {result['message']}",
                    "data": None
                }

        self._log(f"  V 步骤 {i + 1} 完成")

        # 检查是否到达期望界面
        if step.expect_screen:
            time.sleep(0.3)  # 等待界面切换
            actual_screen = self.detect_screen()
            if actual_screen != step.expect_screen:
                self._log(f"  ! 界面不符: 期望 {step.expect_screen.value}, 实际 {actual_screen.value}")

    self._log(f"=== 工作流完成 ===")
    return {
        "success": True,
        "message": "工作流执行成功",
        "data": None
    }
```

## 参数解析

```python
# apps/wechat/workflow_executor.py 实际代码

def parse_task_params(task: str, param_hints: Dict[str, str]) -> Dict[str, Any]:
    """
    从任务描述中解析参数

    Args:
        task: 任务描述，如 "给张三发消息说你好"
        param_hints: 参数提示

    Returns:
        解析出的参数
    """
    params = {}

    # 解析联系人名称
    if "contact" in param_hints:
        # 尝试多种格式：
        # 1. "给XXX：" (冒号分隔)
        # 2. "给XXX发/说" (传统格式)
        match = re.search(r'给\s*([^\s:：，。\d]+?)(?:[：:]|发|说|$)', task)
        if match:
            params["contact"] = match.group(1)

    # 解析消息内容
    if "message" in param_hints:
        # 1. 先尝试冒号后的内容
        match = re.search(r'[:：]\s*(.+)', task)
        if match:
            params["message"] = match.group(1).strip()
        else:
            # 2. 尝试引号内容
            match = re.search(r'[""「」\'](.*?)[""」」\']', task)
            if match:
                params["message"] = match.group(1)
            else:
                # 3. 尝试 "说XXX"
                match = re.search(r'说\s*([^，。]+?)(?:$|，|。|然后|截图|发朋友圈)', task)
                if match:
                    params["message"] = match.group(1).strip()
                elif "moments_content" in param_hints:
                    # 如果没有明确的消息内容，且是复合任务，使用默认消息
                    params["message"] = "你好"

    # 解析朋友圈内容
    if "content" in param_hints or "moments_content" in param_hints:
        key = "content" if "content" in param_hints else "moments_content"
        # 引号内容（第二个引号内容，第一个可能是消息）
        quotes = re.findall(r'[""「」\'](.*?)[""」」\']', task)
        if len(quotes) >= 2:
            params[key] = quotes[1]  # 第二个引号是朋友圈内容
        elif len(quotes) == 1 and "message" not in params:
            params[key] = quotes[0]
        else:
            # "发朋友圈XXX"
            match = re.search(r'发朋友圈\s*(.+)', task)
            if match:
                params[key] = match.group(1).strip()
            elif key == "moments_content":
                # 复合任务默认使用消息内容作为朋友圈配文
                if "message" in params:
                    params[key] = f"分享一下：{params['message']}"

    # 解析搜索关键词
    if "keyword" in param_hints:
        match = re.search(r'搜索\s*(.+)', task)
        if match:
            params["keyword"] = match.group(1).strip()

    # 解析微信号
    if "wechat_id" in param_hints:
        match = re.search(r'(?:加|添加)[^\d]*(\d+|[a-zA-Z][\w-]+)', task)
        if match:
            params["wechat_id"] = match.group(1)

    return params
```

## 执行流程图

```
execute_workflow(workflow, params)
            │
            ▼
    ┌───────────────────┐
    │ 检查必需参数       │
    └─────────┬─────────┘
              │
              ▼
    ┌───────────────────┐
    │ _ensure_app_running │
    │ 启动应用 + 回首页   │
    └─────────┬─────────┘
              │
              ▼
    ┌───────────────────┐
    │ detect_screen      │
    │ 检测当前界面       │
    └─────────┬─────────┘
              │
              ▼
    ┌───────────────────┐
    │ 需要导航到首页?    │
    └─────────┬─────────┘
              │
      ┌───────┴───────┐
      │是             │否
      ▼               │
┌─────────────────┐   │
│ navigate_to_home │   │
│ (带 AI 回退)     │   │
└────────┬────────┘   │
         │            │
         └──────┬─────┘
                │
                ▼
    ┌───────────────────┐
    │ 循环执行 steps     │
    │ _execute_step()   │
    └─────────┬─────────┘
              │
         失败? ─────────┐
              │        │
              ▼        ▼
         成功      _try_recover()
              │        │
              │    成功? ────┐
              │        │    │
              │        ▼    │
              │    重试步骤  │
              │        │    │
              └───┬────┘    │
                  │    失败  │
                  ▼    ─────┘
            返回结果
```
