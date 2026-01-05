"""
apps/base.py
应用模块基类 - 定义标准接口和默认实现

包含：
- ModuleInfo: 模块元信息
- ModuleAssets: 模块资源管理
- AppHandler: 抽象基类
- DefaultHandler: 默认实现
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import yaml


@dataclass
class ModuleInfo:
    """模块元信息"""
    name: str                           # 显示名称
    package: Optional[str] = None       # 应用包名（如 com.tencent.mm）
    version: str = "1.0.0"              # 模块版本
    description: str = ""               # 模块描述
    keywords: List[str] = field(default_factory=list)  # 路由关键词
    author: str = ""                    # 作者

    @classmethod
    def from_yaml(cls, data: dict) -> 'ModuleInfo':
        """从 YAML 数据创建"""
        return cls(
            name=data.get('name', '未命名'),
            package=data.get('package'),
            version=data.get('version', '1.0.0'),
            description=data.get('description', ''),
            keywords=data.get('keywords', []),
            author=data.get('author', ''),
        )


@dataclass
class TaskTemplate:
    """任务模板"""
    name: str                           # 任务名称
    description: str                    # 任务描述
    patterns: List[str]                 # 匹配模式（正则）
    steps: List[Dict[str, Any]]         # 预定义步骤
    variables: List[str] = field(default_factory=list)  # 需要提取的变量
    simple: bool = False                # 是否为简单任务（直接执行，不经过 AI）

    @classmethod
    def from_yaml(cls, data: dict) -> 'TaskTemplate':
        """从 YAML 数据创建"""
        return cls(
            name=data.get('name', ''),
            description=data.get('description', ''),
            patterns=data.get('patterns', []),
            steps=data.get('steps', []),
            variables=data.get('variables', []),
            simple=data.get('simple', False),
        )


class ModuleAssets:
    """
    模块资源管理器

    管理模块的参考图片、提示词模板等资源。
    """

    def __init__(self, module_dir: Path):
        self.module_dir = module_dir
        self.images_dir = module_dir / "images"
        self.prompts_dir = module_dir / "prompts"

        self._image_cache: Dict[str, Path] = {}
        self._prompt_cache: Dict[str, str] = {}
        self._aliases: Dict[str, str] = {}

        self._load_aliases()

    def _load_aliases(self):
        """加载图片别名配置"""
        alias_file = self.images_dir / "aliases.yaml"
        if alias_file.exists():
            with open(alias_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                self._aliases = data.get('aliases', {})

    def get_image(self, name: str) -> Optional[Path]:
        """
        获取参考图片路径

        支持：
        - 直接文件名: "wechat_icon.png"
        - 别名: "微信图标" -> "wechat_icon.png"
        - 子目录路径: "contacts/zhanghua" -> contacts/zhanghua.png
        - 联系人别名: "张华" -> contacts/zhanghua.png
        """
        # 检查缓存
        if name in self._image_cache:
            return self._image_cache[name]

        # 检查别名
        actual_name = self._aliases.get(name, name)

        # 搜索图片
        if not self.images_dir.exists():
            return None

        # 尝试精确匹配（支持子目录路径，如 contacts/zhanghua）
        for ext in ['.png', '.jpg', '.jpeg', '.webp']:
            path = self.images_dir / f"{actual_name}{ext}"
            if path.exists():
                self._image_cache[name] = path
                return path

        # 尝试带扩展名的匹配
        path = self.images_dir / actual_name
        if path.exists():
            self._image_cache[name] = path
            return path

        # 在根目录模糊匹配
        for file in self.images_dir.iterdir():
            if file.is_file() and actual_name.lower() in file.stem.lower():
                self._image_cache[name] = file
                return file

        # 在 contacts 子目录中搜索（用于联系人）
        contacts_dir = self.images_dir / "contacts"
        if contacts_dir.exists():
            for ext in ['.png', '.jpg', '.jpeg', '.webp']:
                path = contacts_dir / f"{actual_name}{ext}"
                if path.exists():
                    self._image_cache[name] = path
                    return path
            # 模糊匹配联系人
            for file in contacts_dir.iterdir():
                if file.is_file() and actual_name.lower() in file.stem.lower():
                    self._image_cache[name] = file
                    return file

        return None

    def get_image_variants(self, name: str) -> List[Path]:
        """
        获取参考图片的所有变体路径

        支持多设备适配：
        - wechat_add_button.png (主图)
        - wechat_add_button_v1.png (变体1)
        - wechat_add_button_v2.png (变体2)

        Args:
            name: 参考图名称

        Returns:
            所有变体的路径列表（按优先级排序）
        """
        variants = []

        # 先获取主图
        primary = self.get_image(name)
        if primary:
            variants.append(primary)

        # 检查别名
        actual_name = self._aliases.get(name, name)

        # 查找变体 (_v1, _v2, _v3, ...)
        if not self.images_dir.exists():
            return variants

        for i in range(1, 10):  # 支持最多 9 个变体（从 _v1 开始）
            variant_name = f"{actual_name}_v{i}"
            for ext in ['.png', '.jpg', '.jpeg', '.webp']:
                path = self.images_dir / f"{variant_name}{ext}"
                if path.exists():
                    variants.append(path)
                    break

        return variants

    def list_images(self) -> List[str]:
        """列出所有可用的参考图片（包括子目录）"""
        if not self.images_dir.exists():
            return []

        images = []
        valid_exts = ['.png', '.jpg', '.jpeg', '.webp']

        # 根目录图片
        for file in self.images_dir.iterdir():
            if file.is_file() and file.suffix.lower() in valid_exts:
                images.append(file.stem)

        # 扫描子目录（contacts, system 等）
        subdirs = ["contacts", "system"]
        for subdir in subdirs:
            subdir_path = self.images_dir / subdir
            if subdir_path.exists():
                for file in subdir_path.iterdir():
                    if file.is_file() and file.suffix.lower() in valid_exts:
                        images.append(f"{subdir}/{file.stem}")

        return sorted(images)

    def list_contacts(self) -> List[str]:
        """列出所有联系人参考图"""
        contacts_dir = self.images_dir / "contacts"
        if not contacts_dir.exists():
            return []

        contacts = []
        valid_exts = ['.png', '.jpg', '.jpeg', '.webp']
        for file in contacts_dir.iterdir():
            if file.is_file() and file.suffix.lower() in valid_exts:
                contacts.append(file.stem)

        # 添加别名映射的联系人
        for alias, target in self._aliases.items():
            if target.startswith("contacts/"):
                contacts.append(alias)

        return sorted(set(contacts))

    def get_prompt(self, name: str) -> Optional[str]:
        """获取提示词模板"""
        if name in self._prompt_cache:
            return self._prompt_cache[name]

        if not self.prompts_dir.exists():
            return None

        # 尝试加载
        for ext in ['.txt', '.md', '']:
            path = self.prompts_dir / f"{name}{ext}"
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self._prompt_cache[name] = content
                    return content

        return None

    def get_all_prompts(self) -> Dict[str, str]:
        """获取所有提示词模板"""
        if not self.prompts_dir.exists():
            return {}

        prompts = {}
        for file in self.prompts_dir.iterdir():
            if file.is_file():
                with open(file, 'r', encoding='utf-8') as f:
                    prompts[file.stem] = f.read()

        return prompts


class AppHandler(ABC):
    """
    应用处理器抽象基类

    每个应用模块需要实现这个接口。
    提供统一的任务处理流程。
    """

    def __init__(self, module_dir: Path):
        self.module_dir = module_dir
        self.module_info = self._load_config()
        self.assets = ModuleAssets(module_dir)
        self.tasks = self._load_tasks()
        self._logger = None

    def set_logger(self, logger):
        """设置日志函数"""
        self._logger = logger

    def _log(self, msg: str):
        if self._logger:
            self._logger(f"[{self.module_info.name}] {msg}")
        else:
            print(f"[{self.module_info.name}] {msg}")

    def _load_config(self) -> ModuleInfo:
        """加载模块配置"""
        config_file = self.module_dir / "config.yaml"
        if not config_file.exists():
            return ModuleInfo(name=self.module_dir.name)

        with open(config_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        return ModuleInfo.from_yaml(data)

    def _load_tasks(self) -> List[TaskTemplate]:
        """加载预定义任务"""
        tasks_file = self.module_dir / "tasks.yaml"
        if not tasks_file.exists():
            return []

        with open(tasks_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        tasks = []
        for task_data in data.get('tasks', []):
            tasks.append(TaskTemplate.from_yaml(task_data))

        return tasks

    def match_task(self, task: str) -> float:
        """
        计算任务与本模块的匹配度

        Args:
            task: 任务描述

        Returns:
            0.0 - 1.0 的匹配得分
        """
        score = 0.0
        task_lower = task.lower()

        # 1. 任务模板匹配 (最高优先级，权重 0.5)
        template_matched = False
        for template in self.tasks:
            for pattern in template.patterns:
                try:
                    if re.search(pattern, task, re.IGNORECASE):
                        score += 0.5
                        template_matched = True
                        break
                except re.error:
                    continue
            if template_matched:
                break

        # 2. 关键词匹配 (权重 0.4)
        # 使用命中数而非比例，每个命中加 0.1，最多 0.4
        keyword_hits = 0
        for keyword in self.module_info.keywords:
            keyword_lower = keyword.lower()
            # 检查是否为正则表达式模式（包含 . * + ? 等）
            if any(c in keyword for c in '.*+?[]()'):
                try:
                    if re.search(keyword_lower, task_lower):
                        keyword_hits += 1
                except re.error:
                    pass
            elif keyword_lower in task_lower:
                keyword_hits += 1
                # 完全匹配给更高分
                if keyword_lower == task_lower:
                    keyword_hits += 2

        if keyword_hits > 0:
            keyword_score = min(keyword_hits * 0.1, 0.4)
            score += keyword_score

        # 3. 包名匹配 (权重 0.1)
        if self.module_info.package:
            if self.module_info.package.lower() in task_lower:
                score += 0.1

        return min(score, 1.0)

    def _is_simple_task(self, task: str) -> bool:
        """
        检测任务是否足够简单，可以使用预定义模板

        简单任务特征：
        - 任务描述较短（通常少于15个字符）
        - 不包含逗号、顿号等分隔符
        - 不包含多个动作词
        """
        # 包含分隔符说明是复合任务
        if any(sep in task for sep in ['，', ',', '、', '；', ';', '然后', '再', '接着', '之后']):
            return False

        # 包含多个动作词说明是复合任务
        action_words = ['打开', '启动', '添加', '发送', '搜索', '点击', '输入', '查看', '关闭']
        action_count = sum(1 for word in action_words if word in task)
        if action_count >= 2:
            return False

        return True

    def match_template(self, task: str) -> Optional[Tuple[TaskTemplate, Dict[str, str]]]:
        """
        匹配预定义任务模板

        只有标记为 simple: true 的模板才会被匹配。
        复杂任务（包含多个动作）交给 AI 规划器处理。

        Args:
            task: 任务描述

        Returns:
            (模板, 提取的变量) 或 None
        """
        # 先检查是否为简单任务
        if not self._is_simple_task(task):
            return None

        for template in self.tasks:
            # 只匹配简单任务模板
            if not getattr(template, 'simple', False):
                continue

            for pattern in template.patterns:
                try:
                    match = re.search(pattern, task, re.IGNORECASE)
                    if match:
                        # 提取变量
                        variables = {}
                        for var_name in template.variables:
                            try:
                                variables[var_name] = match.group(var_name)
                            except (IndexError, KeyError):
                                pass

                        return template, variables
                except re.error:
                    continue

        return None

    @abstractmethod
    def plan(self, task: str, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        规划任务步骤

        Args:
            task: 任务描述
            context: 上下文信息（如当前屏幕状态）

        Returns:
            步骤列表，每个步骤是一个字典
        """
        pass

    @abstractmethod
    def get_planner_prompt(self) -> str:
        """
        获取 AI 规划器的提示词

        Returns:
            系统提示词
        """
        pass

    def get_available_images(self) -> List[str]:
        """获取可用的参考图片列表"""
        return self.assets.list_images()

    def get_image_path(self, name: str) -> Optional[Path]:
        """获取参考图片路径"""
        return self.assets.get_image(name)

    def get_image_variants(self, name: str) -> List[Path]:
        """获取参考图片的所有变体路径（用于多设备适配）"""
        return self.assets.get_image_variants(name)

    def prepare_app(self, adb_controller) -> bool:
        """
        准备应用（如启动应用）

        Args:
            adb_controller: ADB 控制器

        Returns:
            是否成功
        """
        if self.module_info.package:
            self._log(f"启动应用: {self.module_info.package}")
            return adb_controller.launch_app(self.module_info.package)
        return True

    def cleanup(self, adb_controller) -> None:
        """
        清理工作（如返回桌面）

        Args:
            adb_controller: ADB 控制器
        """
        pass


class DefaultHandler(AppHandler):
    """
    默认处理器

    当模块没有自定义 handler 时使用。
    使用通用的 AI 规划逻辑。
    """

    def plan(self, task: str, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        使用预定义模板或返回空列表让 AI 规划
        """
        # 尝试匹配模板
        result = self.match_template(task)
        if result:
            template, variables = result
            self._log(f"匹配到模板: {template.name}")

            # 替换变量
            steps = []
            for step in template.steps:
                step_copy = step.copy()
                for key, value in step_copy.items():
                    if isinstance(value, str):
                        for var_name, var_value in variables.items():
                            step_copy[key] = value.replace(f"{{{var_name}}}", var_value)
                steps.append(step_copy)

            return steps

        # 没有匹配的模板，返回空让 AI 规划
        return []

    def get_planner_prompt(self) -> str:
        """获取默认的规划器提示词"""
        # 尝试加载模块自定义提示词
        custom_prompt = self.assets.get_prompt("planner")
        if custom_prompt:
            return custom_prompt

        # 返回默认提示词
        available_images = self.get_available_images()
        images_hint = ""
        if available_images:
            images_hint = f"\n\n可用的参考图片:\n" + "\n".join(f"- {img}" for img in available_images[:10])

        return f"""你是一个 Android 自动化任务规划器，负责为【{self.module_info.name}】模块规划操作步骤。

模块信息：
- 名称: {self.module_info.name}
- 包名: {self.module_info.package or '无'}
- 描述: {self.module_info.description or '通用模块'}
{images_hint}

你的任务是将用户的自然语言指令分解为具体的操作步骤。

可用的操作类型：
1. tap - 点击元素
2. long_press - 长按元素
3. swipe - 滑动屏幕
4. input_text - 输入文字
5. wait - 等待
6. launch_app - 启动应用
7. call - 拨打电话
8. open_url - 打开网址

每个步骤需要包含：
- action: 操作类型
- description: 步骤描述
- target_ref: 目标元素（用于 tap/long_press/input_text）
- 其他参数根据操作类型而定

请以 JSON 格式返回步骤列表。"""
