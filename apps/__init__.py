"""
apps/__init__.py
应用模块注册表 - 自动发现和注册应用处理器

使用方式：
---------
# 自动发现所有模块
from apps import ModuleRegistry
ModuleRegistry.discover()

# 获取模块
handler = ModuleRegistry.get("wechat")

# 路由任务
handler = ModuleRegistry.route("给张三发微信")
"""
import re
import importlib
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import yaml


class ModuleRegistry:
    """
    模块注册表

    自动发现 apps/ 目录下的所有应用模块，并提供路由功能。
    """

    _handlers: Dict[str, 'AppHandler'] = {}
    _discovered: bool = False
    _logger = None

    @classmethod
    def set_logger(cls, logger):
        """设置日志函数"""
        cls._logger = logger

    @classmethod
    def _log(cls, msg: str):
        if cls._logger:
            cls._logger(f"[Registry] {msg}")
        else:
            print(f"[Registry] {msg}")

    @classmethod
    def discover(cls, apps_dir: Path = None):
        """
        自动发现并注册模块

        扫描 apps/ 目录，找到所有包含 config.yaml 的子目录，
        自动加载并注册为应用模块。
        """
        if cls._discovered:
            return

        if apps_dir is None:
            apps_dir = Path(__file__).parent

        cls._log(f"扫描模块目录: {apps_dir}")

        for module_dir in sorted(apps_dir.iterdir()):
            # 跳过非目录和私有目录
            if not module_dir.is_dir():
                continue
            if module_dir.name.startswith('_'):
                continue
            if module_dir.name == '__pycache__':
                continue

            # 检查 config.yaml 是否存在
            config_file = module_dir / "config.yaml"
            if not config_file.exists():
                continue

            # 加载模块
            try:
                handler = cls._load_handler(module_dir)
                if handler:
                    cls._handlers[module_dir.name] = handler
                    cls._log(f"  注册模块: {module_dir.name} ({handler.module_info.name})")
            except Exception as e:
                cls._log(f"  加载模块失败: {module_dir.name} - {e}")

        cls._discovered = True
        cls._log(f"共注册 {len(cls._handlers)} 个模块")

    @classmethod
    def _load_handler(cls, module_dir: Path) -> 'AppHandler':
        """
        加载模块处理器

        优先级：
        1. 自定义 handler.py 中的 Handler 类
        2. 默认 DefaultHandler
        """
        from apps.base import DefaultHandler

        # 尝试加载自定义 handler
        handler_file = module_dir / "handler.py"
        if handler_file.exists():
            try:
                module = importlib.import_module(f"apps.{module_dir.name}.handler")
                if hasattr(module, 'Handler'):
                    return module.Handler(module_dir)
            except Exception as e:
                cls._log(f"    自定义 handler 加载失败: {e}，使用默认处理器")

        # 使用默认 handler
        return DefaultHandler(module_dir)

    @classmethod
    def get(cls, name: str) -> Optional['AppHandler']:
        """获取指定模块的处理器"""
        if not cls._discovered:
            cls.discover()
        return cls._handlers.get(name)

    @classmethod
    def all(cls) -> Dict[str, 'AppHandler']:
        """获取所有已注册的处理器"""
        if not cls._discovered:
            cls.discover()
        return cls._handlers.copy()

    @classmethod
    def route(cls, task: str) -> Tuple['AppHandler', float]:
        """
        根据任务内容路由到合适的处理器

        Args:
            task: 任务描述

        Returns:
            (handler, score) 最匹配的处理器和匹配得分
        """
        if not cls._discovered:
            cls.discover()

        best_handler = None
        best_score = 0.0

        for name, handler in cls._handlers.items():
            score = handler.match_task(task)
            if score > best_score:
                best_score = score
                best_handler = handler

        # 如果没有匹配或得分太低，使用 system 模块
        if best_handler is None or best_score < 0.3:
            best_handler = cls._handlers.get("system")
            if best_handler is None and cls._handlers:
                # 如果没有 system 模块，使用第一个
                best_handler = list(cls._handlers.values())[0]

        return best_handler, best_score

    @classmethod
    def list_modules(cls) -> List[Dict]:
        """列出所有已注册的模块信息"""
        if not cls._discovered:
            cls.discover()

        result = []
        for name, handler in cls._handlers.items():
            info = handler.module_info
            result.append({
                "id": name,
                "name": info.name,
                "package": info.package,
                "keywords": info.keywords[:5],  # 只显示前5个
            })
        return result

    @classmethod
    def reset(cls):
        """重置注册表（用于测试）"""
        cls._handlers.clear()
        cls._discovered = False
