"""
ai/planner.py
任务规划器 - 将用户任务分解为可执行的步骤序列

职责:
- 分析当前屏幕状态
- 将自然语言任务分解为具体操作步骤
- 为每个步骤指定参考图和验证条件
"""
import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from PIL import Image

from config import LLMConfig
from ai.vision_agent import VisionAgent


class TargetType(Enum):
    """目标类型"""
    ICON = "icon"       # 应用图标
    UI = "ui"           # UI 元素
    DYNAMIC = "dynamic" # 动态描述
    STATE = "state"     # 状态验证


class ActionName(Enum):
    """动作类型"""
    TAP = "tap"
    LONG_PRESS = "long_press"
    SWIPE = "swipe"
    INPUT_TEXT = "input_text"
    PRESS_KEY = "press_key"
    WAIT = "wait"
    GO_HOME = "go_home"      # 特殊动作：返回桌面（连续两次 HOME）
    LAUNCH_APP = "launch_app"  # 直接启动 App（使用包名）
    CALL = "call"            # 直接拨打电话
    OPEN_URL = "open_url"    # 打开网址
    SCREENSHOT = "screenshot"  # 截屏保存


@dataclass
class StepPlan:
    """单步操作计划"""
    step: int                              # 步骤序号
    action: ActionName                      # 动作类型
    target_ref: Optional[str] = None       # 参考图名称或 "dynamic:描述"
    target_type: Optional[TargetType] = None  # 目标类型
    description: str = ""                  # 操作描述
    params: Dict[str, Any] = field(default_factory=dict)  # 额外参数
    verify_ref: Optional[str] = None       # 验证用的参考图名称
    success_condition: Optional[str] = None # 成功条件描述
    fallback: Optional[Dict[str, Any]] = None  # 备选方案
    timeout: int = 3000                    # 超时时间 (ms)
    retry: int = 2                         # 重试次数
    wait_before: int = 0                   # 执行前等待 (ms)
    wait_after: int = 300                  # 执行后等待 (ms)


@dataclass
class TaskPlan:
    """任务计划"""
    analysis: Dict[str, Any]       # 分析结果
    steps: List[StepPlan]          # 步骤列表
    success_criteria: str = ""     # 成功标准
    potential_issues: List[str] = field(default_factory=list)  # 潜在问题


class AssetsManager:
    """参考图库管理器"""

    def __init__(self, assets_dir: Optional[Path] = None):
        """
        初始化参考图库管理器

        Args:
            assets_dir: assets 目录路径，默认为项目根目录下的 assets
        """
        if assets_dir is None:
            assets_dir = Path(__file__).parent.parent / "assets"
        self.assets_dir = assets_dir
        self.index: Dict[str, Any] = {}
        self._logger = None
        self._load_index()

    def set_logger(self, logger_func):
        """设置日志函数"""
        self._logger = logger_func

    def _log(self, message: str):
        """记录日志"""
        if self._logger:
            self._logger(f"[Assets] {message}")
        else:
            print(f"[Assets] {message}")

    def _load_index(self):
        """加载 index.json"""
        index_file = self.assets_dir / "index.json"
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                self.index = json.load(f)

    def get_image(self, ref_name: str) -> Optional[Image.Image]:
        """
        获取参考图片

        Args:
            ref_name: 参考图名称（如 "wechat", "search_icon", "home_screen"）

        Returns:
            PIL Image 对象，如果未找到则返回 None
        """
        # 在各类别中查找
        for category in ["icons", "ui", "states"]:
            if ref_name in self.index.get(category, {}):
                info = self.index[category][ref_name]
                path = self.assets_dir / info["path"]
                if path.exists():
                    img = Image.open(path)
                    aliases = info.get("aliases", [])
                    self._log(f"找到参考图: {ref_name} -> {path.name} ({img.size[0]}x{img.size[1]})")
                    if aliases:
                        self._log(f"  别名: {', '.join(aliases)}")
                    return img
                else:
                    self._log(f"参考图配置存在但文件不存在: {ref_name} -> {path}")

        self._log(f"未找到参考图: '{ref_name}' (已搜索 icons/ui/states)")
        return None

    def get_path(self, ref_name: str) -> Optional[Path]:
        """获取参考图路径"""
        for category in ["icons", "ui", "states"]:
            if ref_name in self.index.get(category, {}):
                info = self.index[category][ref_name]
                path = self.assets_dir / info["path"]
                if path.exists():
                    return path
        return None

    def resolve_alias(self, name: str) -> Optional[str]:
        """
        解析别名

        Args:
            name: 名称或别名（如 "微信", "WeChat"）

        Returns:
            标准参考名称（如 "wechat"），如果未找到则返回 None
        """
        # 直接匹配
        for category in ["icons", "ui", "states"]:
            if name in self.index.get(category, {}):
                self._log(f"别名解析: '{name}' -> '{name}' (直接匹配)")
                return name

        # 别名匹配
        for category in ["icons", "ui", "states"]:
            for ref_name, info in self.index.get(category, {}).items():
                aliases = info.get("aliases", [])
                if name in aliases or name.lower() in [a.lower() for a in aliases]:
                    self._log(f"别名解析: '{name}' -> '{ref_name}' (通过别名)")
                    return ref_name

        self._log(f"别名解析失败: '{name}' 未匹配任何参考图")
        return None

    def get_available_refs(self) -> Dict[str, List[str]]:
        """
        获取所有可用的参考图列表

        Returns:
            按类别分组的参考图名称列表
        """
        result = {
            "icons": [],
            "ui": [],
            "states": []
        }
        for category in result.keys():
            for ref_name, info in self.index.get(category, {}).items():
                # 检查文件是否实际存在
                path = self.assets_dir / info.get("path", "")
                if path.exists():
                    aliases = info.get("aliases", [])
                    desc = info.get("description", "")
                    entry = f"{ref_name}"
                    if aliases:
                        entry += f" ({', '.join(aliases[:2])})"
                    if desc:
                        entry += f" - {desc}"
                    result[category].append(entry)
        return result


class Planner:
    """
    任务规划器

    将用户的自然语言任务分解为可执行的步骤序列。
    """

    def __init__(
        self,
        llm_config: Optional[LLMConfig] = None,
        assets_dir: Optional[Path] = None
    ):
        """
        初始化规划器

        Args:
            llm_config: LLM 配置，如果为 None 则从环境变量加载
            assets_dir: assets 目录路径
        """
        self.vision = VisionAgent(llm_config=llm_config)
        self.assets = AssetsManager(assets_dir)
        self._logger = None

    def set_logger(self, logger_func):
        """设置日志回调函数"""
        self._logger = logger_func
        self.vision.set_logger(logger_func)

    def _log(self, message: str):
        """记录日志"""
        if self._logger:
            self._logger(f"[Planner] {message}")
        else:
            print(f"[Planner] {message}")

    def plan(
        self,
        task: str,
        screenshot: Image.Image,
        history: Optional[List[StepPlan]] = None,
        system_prompt: Optional[str] = None,
        module_images: Optional[List[str]] = None
    ) -> TaskPlan:
        """
        生成任务执行计划

        Args:
            task: 用户任务描述
            screenshot: 当前屏幕截图
            history: 已执行的步骤历史
            system_prompt: 自定义系统提示词（模块特定）

        Returns:
            TaskPlan 任务计划对象
        """
        self._log(f"===== 任务规划 =====")
        self._log(f"  任务: {task}")
        self._log(f"  截图: {screenshot.size[0]}x{screenshot.size[1]}")

        # 获取可用参考图
        available_refs = self.assets.get_available_refs()
        total_refs = sum(len(v) for v in available_refs.values())
        self._log(f"  可用参考图: {total_refs} 个")
        for category, items in available_refs.items():
            if items:
                self._log(f"    {category}: {len(items)} 个")

        # 构建提示词
        if module_images:
            self._log(f"  模块参考图: {len(module_images)} 个")
            self._log(f"    前10个: {module_images[:10]}")
        else:
            self._log(f"  模块参考图: 无")

        prompt = self._build_prompt(task, available_refs, history, module_images)

        # 使用自定义或默认系统提示词
        sys_prompt = system_prompt if system_prompt else self._get_system_prompt()
        if system_prompt:
            self._log(f"  使用模块自定义提示词")

        # 调用 LLM
        self._log(f"  -> 调用 LLM 生成计划...")
        self._log(f"  API: {self.vision.config.provider}/{self.vision.config.model}")
        image_b64 = self.vision._image_to_base64(screenshot)

        if self.vision.config.provider == "claude":
            response = self.vision._call_claude(
                sys_prompt,
                prompt,
                image_b64
            )
        else:
            response = self.vision._call_openai_compatible(
                sys_prompt + "\n只返回JSON，不要其他内容。",
                prompt,
                image_b64,
                json_mode=True
            )

        self._log(f"LLM 响应: {response[:500]}...")

        # 解析响应
        return self._parse_response(response)

    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是 Android 自动化任务规划专家。分析当前屏幕截图，将用户任务分解为具体执行步骤。

【规划规则】
1. 分析当前屏幕状态，确定起点
2. 规划到达目标状态的最短路径
3. 每一步必须指定:
   - action: tap / long_press / swipe / input_text / press_key / wait / go_home
   - target_ref: 参考图名称 或 "dynamic:描述"
   - target_type: icon / ui / dynamic / state
   - description: 操作说明
4. 对于关键步骤，指定 verify_ref 进行验证
5. 对于可能失败的步骤，提供 fallback 备选方案
6. 动态元素使用 "dynamic:{精确描述}" 格式

【特殊规则】
- 打开应用：优先使用 launch_app 动作（直接启动，无需在桌面查找图标）
- 拨打电话：优先使用 call 动作（直接拨打，无需打开拨号盘输入号码）
- 打开网址：优先使用 open_url 动作（直接打开浏览器）
- 返回桌面：使用 go_home 动作（会自动连续按两次 HOME 键，确保从任何应用回到桌面首页）
- 滑动方向：向上滑动查看更多内容，左右滑动切换桌面页面
- swipe 参数: direction (up/down/left/right)

【动作参数说明】
- launch_app: 直接启动App，需要 target_ref（如 wechat）或 params.package（如 com.tencent.mm）
- call: 直接拨打电话，需要 params.number（如 10086）
- open_url: 打开网址，需要 params.url（如 www.baidu.com）
- tap: 点击，需要 target_ref
- long_press: 长按，需要 target_ref, 可选 params.duration (ms)
- swipe: 滑动，需要 params.direction (up/down/left/right)
- input_text: 输入文字，需要 params.text，可选 target_ref 指定输入框（会自动先点击激活）
- press_key: 按键，需要 params.keycode (3=HOME, 4=BACK, 66=ENTER)
- wait: 等待，需要 params.duration (ms)
- go_home: 返回桌面首页，无需参数

【input_text 注意事项】
input_text 动作会自动处理输入框激活：
1. 如果指定了 target_ref（如 "dynamic:搜索框"），会先点击该元素激活输入框
2. 然后自动输入文本
3. 不需要单独的 tap 步骤来点击输入框
示例：{"action": "input_text", "target_ref": "dynamic:搜索框", "params": {"text": "关键词"}}

【优先使用直接命令】
当任务可以通过直接命令完成时，应优先选择：
1. "打开微信" → launch_app (target_ref: wechat)，而不是在桌面找图标点击
2. "拨打10086" → call (params.number: 10086)，而不是打开拨号盘输入号码
3. "打开百度" → open_url (params.url: www.baidu.com)，而不是打开浏览器再输入网址

【输出格式】
严格输出 JSON，结构如下:
{
  "analysis": {
    "current_screen": "当前屏幕描述",
    "target_state": "目标状态描述",
    "estimated_steps": 步骤数量
  },
  "steps": [
    {
      "step": 1,
      "action": "tap",
      "target_ref": "wechat",
      "target_type": "icon",
      "description": "点击微信图标",
      "verify_ref": "wechat_main",
      "timeout": 3000,
      "retry": 2,
      "wait_after": 1000
    }
  ],
  "success_criteria": "任务成功的标准",
  "potential_issues": ["可能遇到的问题1", "问题2"]
}"""

    def _build_prompt(
        self,
        task: str,
        available_refs: Dict[str, List[str]],
        history: Optional[List[StepPlan]] = None,
        module_images: Optional[List[str]] = None
    ) -> str:
        """构建用户提示词"""
        # 格式化可用参考图
        icons_str = "\n".join(f"  - {r}" for r in available_refs.get("icons", [])[:15])
        ui_str = "\n".join(f"  - {r}" for r in available_refs.get("ui", [])[:15])
        states_str = "\n".join(f"  - {r}" for r in available_refs.get("states", [])[:10])

        prompt = f"""【用户任务】
{task}

【当前屏幕】
已附带当前屏幕截图

【可用参考图库】
图标类 (target_type=icon):
{icons_str if icons_str else "  (暂无预置图标，请使用 dynamic 类型)"}

UI元素类 (target_type=ui):
{ui_str if ui_str else "  (暂无预置UI元素，请使用 dynamic 类型)"}

状态验证类 (verify_ref):
{states_str if states_str else "  (暂无预置状态图)"}

注意: 如果需要的参考图不在列表中，请使用 "dynamic:具体描述" 格式。"""

        # 追加模块参考图提示
        if module_images:
            module_images_str = "\n".join(f"  - {r}" for r in module_images[:20])
            module_hint = f"\n\n【模块参考图库（优先使用）】\n{module_images_str}\n\n请优先使用上述名称作为 target_ref（禁止对这些元素使用 dynamic: 前缀）。"
            prompt += module_hint
            self._log(f"  追加模块参考图提示: {len(module_images)} 个图片名称")
            self._log(f"  提示内容预览: {module_hint[:200]}...")
        else:
            self._log(f"  未追加模块参考图提示（module_images 为空）")

        # 添加历史记录
        if history:
            history_str = "\n".join([
                f"  第{s.step}步: {s.action.value} - {s.description}"
                for s in history[-5:]
            ])
            prompt += f"\n\n【已执行步骤】\n{history_str}"

        return prompt

    def _parse_response(self, response: str) -> TaskPlan:
        """解析 LLM 响应"""
        # 尝试提取 JSON（支持对象 {} 或数组 []）
        json_match = re.search(r'[\[\{][\s\S]*[\]\}]', response)
        if not json_match:
            self._log("无法从响应中提取 JSON")
            return self._create_fallback_plan("无法解析 LLM 响应")

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            self._log(f"JSON 解析错误: {e}")
            return self._create_fallback_plan(f"JSON 解析错误: {e}")

        # 处理不同的响应格式
        success_criteria = ""
        potential_issues = []

        if isinstance(data, list):
            # 直接返回步骤数组
            steps_data = data
            analysis = {}
        else:
            # 标准格式：{ analysis: {...}, steps: [...] }
            analysis = data.get("analysis", {})
            steps_data = data.get("steps", [])
            success_criteria = data.get("success_criteria", "")
            potential_issues = data.get("potential_issues", [])

        # 解析步骤
        steps = []
        for i, step_data in enumerate(steps_data):
            try:
                step = self._parse_step(step_data)
                step.step = i + 1  # 设置步骤序号
                steps.append(step)
            except Exception as e:
                self._log(f"解析步骤失败: {e}, data={step_data}")

        if not steps:
            return self._create_fallback_plan("没有解析出有效步骤")

        # 输出规划结果详情
        self._log(f"===== 规划结果 =====")
        self._log(f"  生成 {len(steps)} 个步骤:")
        for step in steps:
            self._log(f"    [{step.step}] {step.action.value}: {step.description}")
            if step.target_ref:
                self._log(f"        目标: {step.target_ref} (类型: {step.target_type.value if step.target_type else 'N/A'})")
            if step.params:
                self._log(f"        参数: {step.params}")
            if step.fallback:
                self._log(f"        备选: {step.fallback}")

        if success_criteria:
            self._log(f"  成功标准: {success_criteria}")

        return TaskPlan(
            analysis=analysis,
            steps=steps,
            success_criteria=success_criteria,
            potential_issues=potential_issues
        )

    def _parse_step(self, data: Dict[str, Any]) -> StepPlan:
        """解析单个步骤"""
        # 解析动作类型
        action_str = data.get("action", "")

        # 如果 action 为空，根据参数推断动作类型
        if not action_str:
            if "keycode" in data or "key_code" in data:
                action_str = "press_key"
            elif "package_name" in data or "package" in data:
                action_str = "launch_app"
            elif "url" in data:
                action_str = "open_url"
            elif "phone_number" in data or "number" in data:
                action_str = "call"
            elif "text" in data:
                action_str = "input_text"
            elif "direction" in data:
                action_str = "swipe"
            else:
                action_str = "wait"

        # 动作名称别名映射（LLM 可能使用不同的名称）
        action_aliases = {
            "key_event": "press_key",
            "keyevent": "press_key",
            "press": "press_key",
            "click": "tap",
            "type": "input_text",
            "enter_text": "input_text",
            "start_app": "launch_app",
            "open_app": "launch_app",
            "scroll": "swipe",
            "dial": "call",
            "phone": "call",
            "browse": "open_url",
            "home": "go_home",
        }
        action_str = action_aliases.get(action_str, action_str)

        try:
            action = ActionName(action_str)
        except ValueError:
            action = ActionName.WAIT

        # 解析目标类型
        target_type = None
        target_type_str = data.get("target_type")
        if target_type_str:
            try:
                target_type = TargetType(target_type_str)
            except ValueError:
                pass

        # 解析参数 - 支持顶层参数和嵌套 params
        params = data.get("params", {})

        # 将顶层的常用参数合并到 params
        param_keys = [
            "package_name", "package",  # launch_app
            "phone_number", "number",   # call
            "url",                      # open_url
            "text",                     # input_text
            "direction",                # swipe
            "duration",                 # wait, long_press
            "keycode", "key_code",      # press_key
            "activity",                 # launch_app
        ]
        for key in param_keys:
            if key in data and key not in params:
                params[key] = data[key]

        # 标准化参数名
        if "package_name" in params and "package" not in params:
            params["package"] = params["package_name"]
        if "phone_number" in params and "number" not in params:
            params["number"] = params["phone_number"]
        if "key_code" in params and "keycode" not in params:
            params["keycode"] = params["key_code"]

        # 支持 target_ref 或 target
        target_ref = data.get("target_ref") or data.get("target")

        return StepPlan(
            step=data.get("step", 0),
            action=action,
            target_ref=target_ref,
            target_type=target_type,
            description=data.get("description", ""),
            params=params,
            verify_ref=data.get("verify_ref"),
            success_condition=data.get("success_condition"),
            fallback=data.get("fallback"),
            timeout=data.get("timeout", 3000),
            retry=data.get("retry", 2),
            wait_before=data.get("wait_before", 0),
            wait_after=data.get("wait_after", 300)
        )

    def _create_fallback_plan(self, reason: str) -> TaskPlan:
        """创建错误回退计划"""
        return TaskPlan(
            analysis={
                "current_screen": "未知",
                "target_state": "未知",
                "error": reason
            },
            steps=[],
            success_criteria="",
            potential_issues=[reason]
        )

    def replan(
        self,
        original_task: str,
        current_screenshot: Image.Image,
        failed_step: StepPlan,
        failure_reason: str,
        executed_steps: List[StepPlan],
        system_prompt: Optional[str] = None,
        module_images: Optional[List[str]] = None
    ) -> TaskPlan:
        """
        重新规划（在步骤失败后）

        Args:
            original_task: 原始任务
            current_screenshot: 当前屏幕截图
            failed_step: 失败的步骤
            failure_reason: 失败原因
            executed_steps: 已执行的步骤
            system_prompt: 自定义系统提示词（模块特定）
            module_images: 模块参考图列表

        Returns:
            新的 TaskPlan
        """
        self._log(f"重新规划: 步骤 {failed_step.step} 失败 - {failure_reason}")

        # 构建带有失败信息的任务描述
        context = f"""原始任务: {original_task}

失败信息:
- 失败步骤: 第 {failed_step.step} 步 - {failed_step.description}
- 失败原因: {failure_reason}
- 已完成步骤数: {len(executed_steps)}

请分析当前屏幕状态，重新规划完成任务的步骤。"""

        return self.plan(
            context,
            current_screenshot,
            history=executed_steps,
            system_prompt=system_prompt,
            module_images=module_images
        )
