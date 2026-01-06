"""
core/mock_adb_controller.py
模拟 ADB 控制器 - 用于调试模式，无需真实设备连接

使用场景：
- 开发测试代码逻辑
- 演示系统功能
- CI/CD 环境测试
- 无设备环境下的功能验证
"""
import time
import random
from typing import Optional, Tuple, List
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import io

import config


class MockADBController:
    """模拟 ADB 控制器，用于调试模式"""

    def __init__(self, device_address: str = "mock:5555"):
        """
        初始化模拟 ADB 控制器

        Args:
            device_address: 设备地址（调试模式下为虚拟地址）
        """
        self.device_address = device_address
        self.adb_path = "mock_adb"
        self._screen_size: Tuple[int, int] = (config.DEBUG_SCREEN_WIDTH, config.DEBUG_SCREEN_HEIGHT)
        self._is_connected: bool = False
        self._current_app: str = "com.tencent.mm/.ui.LauncherUI"  # 默认微信
        self._screen_on: bool = True

        print(f"[MockADB] 初始化模拟设备: {config.DEBUG_DEVICE_NAME}")
        print(f"[MockADB] 屏幕尺寸: {self._screen_size[0]}x{self._screen_size[1]}")

    def connect(self) -> bool:
        """连接到模拟设备"""
        print(f"[MockADB] 连接到模拟设备: {self.device_address}")
        time.sleep(0.1)  # 模拟连接延迟
        self._is_connected = True
        return True

    def disconnect(self) -> bool:
        """断开模拟设备连接"""
        print(f"[MockADB] 断开模拟设备: {self.device_address}")
        self._is_connected = False
        return True

    def is_connected(self) -> bool:
        """检查模拟设备是否已连接"""
        return self._is_connected

    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕分辨率"""
        return self._screen_size

    def get_screen_insets(self) -> dict:
        """获取屏幕安全区域信息"""
        return {
            "top": 0,
            "bottom": 0,
            "left": 0,
            "right": 0
        }

    def tap(self, x: int, y: int) -> bool:
        """模拟点击操作"""
        print(f"[MockADB] 点击: ({x}, {y})")
        time.sleep(0.05)
        return True

    def long_press(self, x: int, y: int, duration_ms: int = 1000) -> bool:
        """模拟长按操作"""
        print(f"[MockADB] 长按: ({x}, {y}), 持续 {duration_ms}ms")
        time.sleep(duration_ms / 1000.0)
        return True

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """模拟滑动操作"""
        print(f"[MockADB] 滑动: ({x1}, {y1}) -> ({x2}, {y2}), 持续 {duration_ms}ms")
        time.sleep(duration_ms / 1000.0)
        return True

    def input_text(self, text: str) -> bool:
        """模拟输入文本"""
        print(f"[MockADB] 输入文本: {text}")
        time.sleep(len(text) * 0.01)  # 模拟输入延迟
        return True

    def input_keyevent(self, keycode: int) -> bool:
        """模拟按键事件"""
        print(f"[MockADB] 按键事件: keycode={keycode}")
        time.sleep(0.05)
        return True

    def press_home(self) -> bool:
        """模拟按 HOME 键"""
        print("[MockADB] 按 HOME 键")
        self._current_app = "com.android.launcher/.Launcher"
        return True

    def press_back(self) -> bool:
        """模拟按返回键"""
        print("[MockADB] 按返回键")
        return True

    def press_enter(self) -> bool:
        """模拟按回车键"""
        print("[MockADB] 按回车键")
        return True

    def screenshot(self, local_path: str) -> bool:
        """
        生成模拟截图

        在调试模式下，生成一个带有文字说明的模拟截图
        """
        print(f"[MockADB] 生成模拟截图: {local_path}")

        # 创建一个空白图像
        width, height = self._screen_size
        img = Image.new('RGB', (width, height), color=(240, 240, 240))
        draw = ImageDraw.Draw(img)

        # 绘制边框
        draw.rectangle([0, 0, width-1, height-1], outline=(100, 100, 100), width=2)

        # 添加文字说明
        try:
            # 尝试使用中文字体
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except:
            # 如果找不到字体，使用默认字体
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # 绘制标题
        title = "Mock Screenshot"
        title_bbox = draw.textbbox((0, 0), title, font=font_large)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (width - title_width) // 2
        draw.text((title_x, height // 3), title, fill=(60, 60, 60), font=font_large)

        # 绘制设备信息
        device_info = f"Device: {config.DEBUG_DEVICE_NAME}"
        info_bbox = draw.textbbox((0, 0), device_info, font=font_small)
        info_width = info_bbox[2] - info_bbox[0]
        info_x = (width - info_width) // 2
        draw.text((info_x, height // 2), device_info, fill=(100, 100, 100), font=font_small)

        # 绘制尺寸信息
        size_info = f"Size: {width}x{height}"
        size_bbox = draw.textbbox((0, 0), size_info, font=font_small)
        size_width = size_bbox[2] - size_bbox[0]
        size_x = (width - size_width) // 2
        draw.text((size_x, height // 2 + 60), size_info, fill=(100, 100, 100), font=font_small)

        # 绘制时间戳
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        time_bbox = draw.textbbox((0, 0), timestamp, font=font_small)
        time_width = time_bbox[2] - time_bbox[0]
        time_x = (width - time_width) // 2
        draw.text((time_x, height * 2 // 3), timestamp, fill=(150, 150, 150), font=font_small)

        # 保存图像
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(local_path)

        time.sleep(0.1)  # 模拟截图延迟
        return True

    def start_app(self, package: str, activity: Optional[str] = None) -> bool:
        """模拟启动应用"""
        app_info = f"{package}/{activity}" if activity else package
        print(f"[MockADB] 启动应用: {app_info}")
        self._current_app = app_info
        time.sleep(0.5)  # 模拟启动延迟
        return True

    def stop_app(self, package: str) -> bool:
        """模拟停止应用"""
        print(f"[MockADB] 停止应用: {package}")
        return True

    def get_current_app(self) -> Optional[str]:
        """获取当前前台应用"""
        return self._current_app

    def dial(self, phone_number: str) -> bool:
        """模拟拨号"""
        print(f"[MockADB] 拨号: {phone_number}")
        time.sleep(0.2)
        return True

    def call(self, phone_number: str) -> bool:
        """模拟直接拨打电话"""
        print(f"[MockADB] 拨打电话: {phone_number}")
        time.sleep(0.5)
        return True

    def get_installed_packages(self) -> List[str]:
        """获取已安装应用列表（模拟）"""
        return [
            "com.tencent.mm",  # 微信
            "com.android.chrome",  # Chrome
            "com.android.settings",  # 设置
        ]

    def is_screen_on(self) -> bool:
        """检查屏幕是否点亮"""
        return self._screen_on

    def wake_up(self) -> bool:
        """模拟唤醒屏幕"""
        print("[MockADB] 唤醒屏幕")
        self._screen_on = True
        return True

    def unlock(self, pin: Optional[str] = None) -> bool:
        """模拟解锁设备"""
        if pin:
            print(f"[MockADB] 使用 PIN 解锁: {pin}")
        else:
            print("[MockADB] 滑动解锁")
        time.sleep(0.5)
        return True

    def get_current_ime(self) -> Optional[str]:
        """获取当前输入法"""
        return "com.android.inputmethod.latin/.LatinIME"

    def list_ime(self) -> List[str]:
        """列出所有输入法"""
        return [
            "com.android.inputmethod.latin/.LatinIME",
            "com.android.adbkeyboard/.AdbIME"
        ]

    def set_ime(self, ime_id: str) -> bool:
        """设置输入法"""
        print(f"[MockADB] 设置输入法: {ime_id}")
        return True

    def is_adbkeyboard_installed(self) -> bool:
        """检查 ADB Keyboard 是否已安装"""
        return True

    def setup_adbkeyboard(self) -> bool:
        """设置 ADB Keyboard"""
        print("[MockADB] 设置 ADB Keyboard")
        return True

    def input_text_chinese(self, text: str) -> bool:
        """模拟输入中文文本"""
        print(f"[MockADB] 输入中文: {text}")
        time.sleep(len(text) * 0.02)
        return True

    def clear_text_field(self) -> bool:
        """模拟清空文本框"""
        print("[MockADB] 清空文本框")
        time.sleep(0.1)
        return True

    def _run_adb(self, *args, timeout: int = 30):
        """
        模拟 ADB 命令执行（用于兼容性）

        Returns:
            模拟的 subprocess.CompletedProcess 对象
        """
        class MockResult:
            def __init__(self):
                self.stdout = ""
                self.stderr = ""
                self.returncode = 0

        return MockResult()
