"""
./config.py
配置文件 - 支持自定义 LLM API
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# 获取项目根目录的 .env 文件路径
_PROJECT_ROOT = Path(__file__).parent
_ENV_FILE = _PROJECT_ROOT / ".env"

# override=True 强制使用 .env 文件的值，覆盖系统环境变量
load_dotenv(_ENV_FILE, override=True)

# ============================================================
# ADB 配置
# ============================================================
def _find_adb_path() -> str:
    """自动检测 ADB 路径"""
    # 优先使用环境变量
    env_path = os.getenv("ADB_PATH", "")
    if env_path:
        return env_path

    # Windows: 尝试 Android SDK 常见位置
    if os.name == 'nt':
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"),
            "D:/work/Android/Sdk/platform-tools/adb.exe",
            "C:/Android/Sdk/platform-tools/adb.exe",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path

    # 默认假设 adb 在 PATH 中
    return "adb"

ADB_PATH = _find_adb_path()
DEFAULT_ADB_PORT = 5555
DEFAULT_DEVICE = os.getenv("DEFAULT_DEVICE", "")  # 默认设备地址，如 emulator-5554 或 192.168.1.100:5555

# ============================================================
# scrcpy 配置
# ============================================================
SCRCPY_PATH = os.getenv("SCRCPY_PATH", "scrcpy")
SCRCPY_MAX_SIZE = int(os.getenv("SCRCPY_MAX_SIZE", "1280"))
SCRCPY_BITRATE = os.getenv("SCRCPY_BITRATE", "8M")

# ============================================================
# 录制配置
# ============================================================
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
RECORD_FPS = int(os.getenv("RECORD_FPS", "30"))
RECORD_AUDIO = os.getenv("RECORD_AUDIO", "true").lower() == "true"

# ============================================================
# LLM 配置
# ============================================================

# 默认提供商: claude, openai, custom
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude")

# --- Claude (Anthropic) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# --- 自定义 LLM (OpenAI 兼容 API) ---
CUSTOM_LLM_API_KEY = os.getenv("CUSTOM_LLM_API_KEY", "")
CUSTOM_LLM_BASE_URL = os.getenv("CUSTOM_LLM_BASE_URL", "")
CUSTOM_LLM_MODEL = os.getenv("CUSTOM_LLM_MODEL", "")

# --- 通用 LLM 设置 ---
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))

# ============================================================
# OCR 配置
# ============================================================
OCR_LANG = os.getenv("OCR_LANG", "ch")  # ch: 中英文, en: 英文
OCR_USE_GPU = os.getenv("OCR_USE_GPU", "false").lower() == "true"

# ============================================================
# 任务配置
# ============================================================
SCREENSHOT_INTERVAL = float(os.getenv("SCREENSHOT_INTERVAL", "1.0"))
MAX_RETRY = int(os.getenv("MAX_RETRY", "5"))
OPERATION_DELAY = float(os.getenv("OPERATION_DELAY", "0.5"))

# ============================================================
# 应用截图等待时间配置（秒）
# ============================================================
SCREENSHOT_WAIT_DEFAULT = float(os.getenv("SCREENSHOT_WAIT_DEFAULT", "0.3"))
SCREENSHOT_WAIT_APPS = {
    "wechat": float(os.getenv("SCREENSHOT_WAIT_WECHAT", "0.3")),
    "chrome": float(os.getenv("SCREENSHOT_WAIT_CHROME", "1.0")),
    "system": float(os.getenv("SCREENSHOT_WAIT_SYSTEM", "0.3")),
}

def get_screenshot_wait(app_name: str = None) -> float:
    """
    获取应用的截图等待时间

    Args:
        app_name: 应用名称（wechat, chrome, system 等）

    Returns:
        等待时间（秒）
    """
    if app_name and app_name.lower() in SCREENSHOT_WAIT_APPS:
        return SCREENSHOT_WAIT_APPS[app_name.lower()]
    return SCREENSHOT_WAIT_DEFAULT


@dataclass
class LLMConfig:
    """
    LLM 配置类 - 用于运行时自定义 LLM 设置

    使用示例:
        # 使用默认配置
        config = LLMConfig.from_env()

        # 自定义配置
        config = LLMConfig(
            provider="custom",
            api_key="sk-xxx",
            base_url="https://api.example.com/v1",
            model="my-model"
        )

        # 从字典创建
        config = LLMConfig.from_dict({
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o"
        })
    """
    provider: str = "claude"  # claude, openai, custom
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    max_tokens: int = 1024
    temperature: float = 0.0
    timeout: int = 60
    extra_params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls, provider: Optional[str] = None) -> "LLMConfig":
        """
        从环境变量创建配置

        Args:
            provider: 指定提供商，如果为 None 则使用 LLM_PROVIDER 环境变量
        """
        provider = provider or LLM_PROVIDER

        if provider == "claude":
            return cls(
                provider="claude",
                api_key=ANTHROPIC_API_KEY,
                base_url=ANTHROPIC_BASE_URL,
                model=CLAUDE_MODEL,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
                timeout=LLM_TIMEOUT,
            )
        elif provider == "openai":
            return cls(
                provider="openai",
                api_key=OPENAI_API_KEY,
                base_url=OPENAI_BASE_URL,
                model=OPENAI_MODEL,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
                timeout=LLM_TIMEOUT,
            )
        elif provider == "custom":
            return cls(
                provider="custom",
                api_key=CUSTOM_LLM_API_KEY,
                base_url=CUSTOM_LLM_BASE_URL,
                model=CUSTOM_LLM_MODEL,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
                timeout=LLM_TIMEOUT,
            )
        else:
            raise ValueError(f"不支持的 LLM 提供商: {provider}")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMConfig":
        """从字典创建配置"""
        return cls(
            provider=data.get("provider", "custom"),
            api_key=data.get("api_key", ""),
            base_url=data.get("base_url", ""),
            model=data.get("model", ""),
            max_tokens=data.get("max_tokens", 1024),
            temperature=data.get("temperature", 0.0),
            timeout=data.get("timeout", 60),
            extra_params=data.get("extra_params", {}),
        )

    @classmethod
    def custom(
        cls,
        api_key: str,
        base_url: str,
        model: str,
        **kwargs
    ) -> "LLMConfig":
        """
        创建自定义 LLM 配置的便捷方法

        Args:
            api_key: API 密钥
            base_url: API 基础 URL
            model: 模型名称
            **kwargs: 其他参数 (max_tokens, temperature, timeout, extra_params)

        示例:
            config = LLMConfig.custom(
                api_key="sk-xxx",
                base_url="https://api.deepseek.com/v1",
                model="deepseek-chat"
            )
        """
        return cls(
            provider="custom",
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_tokens=kwargs.get("max_tokens", 1024),
            temperature=kwargs.get("temperature", 0.0),
            timeout=kwargs.get("timeout", 60),
            extra_params=kwargs.get("extra_params", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "provider": self.provider,
            "api_key": self.api_key[:8] + "..." if self.api_key else "",
            "base_url": self.base_url,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "timeout": self.timeout,
        }

    def __repr__(self) -> str:
        return f"LLMConfig(provider={self.provider}, model={self.model}, base_url={self.base_url})"


# ============================================================
# 预设的第三方 LLM 配置
# ============================================================

# 常见第三方 API 的预设配置
LLM_PRESETS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-128k",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4v",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-vl-max",
    },
    "yi": {
        "base_url": "https://api.lingyiwanwu.com/v1",
        "model": "yi-vision",
    },
    "azure": {
        "base_url": "",  # 需要用户自己设置
        "model": "gpt-4o",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llava",
    },
    "lmstudio": {
        "base_url": "http://localhost:1234/v1",
        "model": "local-model",
    },
}


def get_preset_config(preset_name: str, api_key: str = "") -> LLMConfig:
    """
    获取预设的 LLM 配置

    Args:
        preset_name: 预设名称 (deepseek, moonshot, zhipu, qwen, yi, azure, ollama, lmstudio)
        api_key: API 密钥

    Returns:
        LLMConfig 实例
    """
    if preset_name not in LLM_PRESETS:
        raise ValueError(f"未知的预设: {preset_name}，可用预设: {list(LLM_PRESETS.keys())}")

    preset = LLM_PRESETS[preset_name]
    return LLMConfig.custom(
        api_key=api_key,
        base_url=preset["base_url"],
        model=preset["model"],
    )
