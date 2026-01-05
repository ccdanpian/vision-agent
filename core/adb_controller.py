"""
core/adb_controller.py
ADB 控制模块 - 通过 ADB 命令控制 Android 设备
"""
import subprocess
import time
import re
from typing import Optional, Tuple, List
from pathlib import Path

import config


class ADBController:
    """ADB 控制器，封装所有 ADB 操作"""

    def __init__(self, device_address: str):
        """
        初始化 ADB 控制器

        Args:
            device_address: 设备地址，格式为 IP:PORT 或设备序列号
        """
        self.device_address = device_address
        self.adb_path = config.ADB_PATH
        self._screen_size: Optional[Tuple[int, int]] = None

    def _run_adb(self, *args, timeout: int = 30) -> subprocess.CompletedProcess:
        """执行 ADB 命令"""
        cmd = [self.adb_path, "-s", self.device_address] + list(args)
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            errors='ignore'
        )

    def connect(self) -> bool:
        """
        连接到远程设备

        Returns:
            是否连接成功
        """
        result = subprocess.run(
            [self.adb_path, "connect", self.device_address],
            capture_output=True,
            text=True,
            timeout=30
        )
        success = "connected" in result.stdout.lower()
        if success:
            # 等待连接稳定
            time.sleep(1)
        return success

    def disconnect(self) -> bool:
        """断开连接"""
        result = subprocess.run(
            [self.adb_path, "disconnect", self.device_address],
            capture_output=True,
            text=True,
            timeout=10
        )
        return "disconnected" in result.stdout.lower()

    def is_connected(self) -> bool:
        """检查设备是否已连接"""
        result = subprocess.run(
            [self.adb_path, "devices"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return self.device_address in result.stdout and "device" in result.stdout

    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕分辨率（优先使用 Override size）"""
        if self._screen_size:
            return self._screen_size

        result = self._run_adb("shell", "wm", "size")
        output = result.stdout

        # 优先匹配 Override size（如果有）
        override_match = re.search(r"Override size:\s*(\d+)x(\d+)", output)
        if override_match:
            self._screen_size = (int(override_match.group(1)), int(override_match.group(2)))
            return self._screen_size

        # 其次匹配 Physical size
        physical_match = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
        if physical_match:
            self._screen_size = (int(physical_match.group(1)), int(physical_match.group(2)))
            return self._screen_size

        # 兜底：匹配任意格式
        match = re.search(r"(\d+)x(\d+)", output)
        if match:
            self._screen_size = (int(match.group(1)), int(match.group(2)))
            return self._screen_size

        raise RuntimeError("无法获取屏幕分辨率")

    def get_screen_insets(self) -> dict:
        """
        动态获取状态栏和导航栏高度

        Returns:
            {"top": 状态栏高度, "bottom": 导航栏高度}
        """
        result = self._run_adb("shell", "dumpsys", "window", "windows", timeout=10)
        output = result.stdout

        screen_width, screen_height = self.get_screen_size()
        top_inset = 0
        bottom_inset = 0

        # 方法1: 从 mAppBounds 获取应用内容区域 (最可靠)
        # 格式: mAppBounds=Rect(0, 92 - 1080, 2276)
        app_bounds_pattern = r"mAppBounds=Rect\((\d+),\s*(\d+)\s*-\s*(\d+),\s*(\d+)\)"
        app_bounds_match = re.search(app_bounds_pattern, output)
        if app_bounds_match:
            top_inset = int(app_bounds_match.group(2))  # y1 = 92
            bottom_y = int(app_bounds_match.group(4))   # y2 = 2276
            bottom_inset = screen_height - bottom_y     # 2400 - 2276 = 124
            return {"top": top_inset, "bottom": bottom_inset}

        # 方法2: 备用 - 从 StatusBar 和 NavigationBar 的 Requested h= 获取
        # 格式: Window{...StatusBar}:
        #       ...
        #       Requested w=1080 h=92
        statusbar_pattern = r"StatusBar\}:.*?Requested w=\d+ h=(\d+)"
        statusbar_match = re.search(statusbar_pattern, output, re.DOTALL)
        if statusbar_match:
            top_inset = int(statusbar_match.group(1))

        navbar_pattern = r"NavigationBar\d*\}:.*?Requested w=\d+ h=(\d+)"
        navbar_match = re.search(navbar_pattern, output, re.DOTALL)
        if navbar_match:
            bottom_inset = int(navbar_match.group(1))

        return {"top": top_inset, "bottom": bottom_inset}

    def tap(self, x: int, y: int) -> bool:
        """
        点击屏幕坐标

        Args:
            x: X 坐标
            y: Y 坐标
        """
        result = self._run_adb("shell", "input", "tap", str(x), str(y))
        time.sleep(config.OPERATION_DELAY)
        return result.returncode == 0

    def long_press(self, x: int, y: int, duration_ms: int = 1000) -> bool:
        """长按"""
        result = self._run_adb(
            "shell", "input", "swipe",
            str(x), str(y), str(x), str(y), str(duration_ms)
        )
        time.sleep(config.OPERATION_DELAY)
        return result.returncode == 0

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """滑动"""
        result = self._run_adb(
            "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration_ms)
        )
        time.sleep(config.OPERATION_DELAY)
        return result.returncode == 0

    def input_text(self, text: str) -> bool:
        """
        输入文本（仅支持ASCII字符）
        对于中文等需要使用 ADBKeyboard
        """
        # 转义特殊字符
        escaped = text.replace(" ", "%s").replace("&", "\\&").replace("<", "\\<").replace(">", "\\>")
        result = self._run_adb("shell", "input", "text", escaped)
        time.sleep(config.OPERATION_DELAY)
        return result.returncode == 0

    def input_keyevent(self, keycode: int) -> bool:
        """
        发送按键事件

        常用键值:
            3: HOME
            4: BACK
            24: VOLUME_UP
            25: VOLUME_DOWN
            26: POWER
            66: ENTER
            67: DEL (退格)
        """
        result = self._run_adb("shell", "input", "keyevent", str(keycode))
        time.sleep(config.OPERATION_DELAY)
        return result.returncode == 0

    def press_home(self) -> bool:
        """按 HOME 键"""
        return self.input_keyevent(3)

    def press_back(self) -> bool:
        """按返回键"""
        return self.input_keyevent(4)

    def press_enter(self) -> bool:
        """按回车键"""
        return self.input_keyevent(66)

    def screenshot(self, local_path: str) -> bool:
        """
        截取屏幕截图并保存到本地

        Args:
            local_path: 本地保存路径
        """
        remote_path = "/sdcard/screenshot_tmp.png"

        # 截图到手机
        result = self._run_adb("shell", "screencap", "-p", remote_path)
        if result.returncode != 0:
            return False

        # 拉取到本地
        result = self._run_adb("pull", remote_path, local_path)
        if result.returncode != 0:
            return False

        # 删除手机上的临时文件
        self._run_adb("shell", "rm", remote_path)
        return True

    def start_app(self, package: str, activity: Optional[str] = None) -> bool:
        """
        启动应用

        Args:
            package: 包名
            activity: Activity 名（可选）
        """
        if activity:
            component = f"{package}/{activity}"
            result = self._run_adb("shell", "am", "start", "-n", component)
        else:
            result = self._run_adb(
                "shell", "monkey", "-p", package,
                "-c", "android.intent.category.LAUNCHER", "1"
            )
        time.sleep(1)  # 等待应用启动
        return result.returncode == 0

    def stop_app(self, package: str) -> bool:
        """停止应用"""
        result = self._run_adb("shell", "am", "force-stop", package)
        return result.returncode == 0

    def get_current_app(self) -> Optional[str]:
        """获取当前前台应用包名"""
        # 方法 1: 使用 dumpsys activity activities
        result = self._run_adb(
            "shell", "dumpsys", "activity", "activities",
            timeout=10
        )
        if result.stdout:
            # 尝试多种匹配模式
            patterns = [
                r"mResumedActivity.*?(\S+)/",
                r"topResumedActivity.*?(\S+)/",
                r"ResumedActivity.*?(\S+)/",
                r"mFocusedApp.*?(\S+)/",
            ]
            for pattern in patterns:
                match = re.search(pattern, result.stdout)
                if match:
                    return match.group(1)

        # 方法 2: 使用 dumpsys window
        result = self._run_adb(
            "shell", "dumpsys", "window", "windows",
            timeout=10
        )
        if result.stdout:
            match = re.search(r"mCurrentFocus.*?(\S+)/", result.stdout)
            if match:
                return match.group(1)
            match = re.search(r"mFocusedApp.*?(\S+)/", result.stdout)
            if match:
                return match.group(1)

        return None

    def dial(self, phone_number: str) -> bool:
        """
        打开拨号界面并输入号码

        Args:
            phone_number: 电话号码
        """
        result = self._run_adb(
            "shell", "am", "start",
            "-a", "android.intent.action.DIAL",
            "-d", f"tel:{phone_number}"
        )
        time.sleep(1)
        return result.returncode == 0

    def call(self, phone_number: str) -> bool:
        """
        直接拨打电话（需要 CALL_PHONE 权限）

        Args:
            phone_number: 电话号码
        """
        result = self._run_adb(
            "shell", "am", "start",
            "-a", "android.intent.action.CALL",
            "-d", f"tel:{phone_number}"
        )
        time.sleep(1)
        return result.returncode == 0

    def get_installed_packages(self) -> List[str]:
        """获取已安装应用列表"""
        result = self._run_adb("shell", "pm", "list", "packages", "-3")
        packages = []
        for line in result.stdout.split("\n"):
            if line.startswith("package:"):
                packages.append(line.replace("package:", "").strip())
        return packages

    def is_screen_on(self) -> bool:
        """检查屏幕是否亮起"""
        result = self._run_adb("shell", "dumpsys", "power")
        return "mHoldingDisplaySuspendBlocker=true" in result.stdout

    def wake_up(self) -> bool:
        """唤醒屏幕"""
        if not self.is_screen_on():
            return self.input_keyevent(26)  # POWER
        return True

    def unlock(self, pin: Optional[str] = None) -> bool:
        """
        解锁屏幕

        Args:
            pin: PIN 码（如果有的话）
        """
        # 唤醒
        self.wake_up()
        time.sleep(0.5)

        # 上滑解锁
        width, height = self.get_screen_size()
        self.swipe(width // 2, height * 3 // 4, width // 2, height // 4, 300)
        time.sleep(0.5)

        # 输入 PIN
        if pin:
            self.input_text(pin)
            self.press_enter()
            time.sleep(0.5)

        return True

    # =========== 中文输入支持 ===========

    def get_current_ime(self) -> Optional[str]:
        """获取当前输入法"""
        result = self._run_adb("shell", "settings", "get", "secure", "default_input_method")
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None

    def list_ime(self) -> List[str]:
        """列出所有可用的输入法"""
        result = self._run_adb("shell", "ime", "list", "-s")
        if result.returncode == 0:
            return [ime.strip() for ime in result.stdout.strip().split('\n') if ime.strip()]
        return []

    def set_ime(self, ime_id: str) -> bool:
        """设置默认输入法"""
        result = self._run_adb("shell", "ime", "set", ime_id)
        return result.returncode == 0

    def is_adbkeyboard_installed(self) -> bool:
        """检查 ADBKeyboard 是否已安装"""
        ime_list = self.list_ime()
        return any("adbkeyboard" in ime.lower() for ime in ime_list)

    def setup_adbkeyboard(self) -> bool:
        """
        设置 ADBKeyboard 为当前输入法

        Returns:
            是否设置成功
        """
        ime_list = self.list_ime()

        # 查找 ADBKeyboard
        adbkeyboard_ime = None
        for ime in ime_list:
            if "adbkeyboard" in ime.lower():
                adbkeyboard_ime = ime
                break

        if not adbkeyboard_ime:
            return False

        # 设置为默认输入法
        return self.set_ime(adbkeyboard_ime)

    def input_text_chinese(self, text: str) -> bool:
        """
        输入中文或特殊字符文本

        使用多种方法尝试输入：
        1. ADBKeyboard Base64 编码方式（首选，避免编码问题）
        2. ADBKeyboard broadcast
        3. 剪贴板粘贴

        Args:
            text: 要输入的文本

        Returns:
            是否输入成功
        """
        import base64

        # 方法1: ADBKeyboard Base64 方式（首选，避免中文编码问题）
        encoded = base64.b64encode(text.encode('utf-8')).decode('ascii')
        print(f"[ADB] 尝试 ADB_INPUT_B64 输入: '{text}' -> base64: {encoded}")
        result = self._run_adb(
            "shell", "am", "broadcast",
            "-a", "ADB_INPUT_B64",
            "--es", "msg", encoded
        )
        print(f"[ADB] broadcast 结果: returncode={result.returncode}, stdout='{result.stdout}'")

        if result.returncode == 0 and "Broadcast completed" in (result.stdout or ""):
            time.sleep(config.OPERATION_DELAY)
            return True

        # 方法2: ADBKeyboard broadcast (标准方式，可能有编码问题)
        print(f"[ADB] Base64 失败，尝试 ADB_INPUT_TEXT 输入: '{text}'")
        result = self._run_adb(
            "shell", "am", "broadcast",
            "-a", "ADB_INPUT_TEXT",
            "--es", "msg", text
        )

        if result.returncode == 0 and "Broadcast completed" in (result.stdout or ""):
            time.sleep(config.OPERATION_DELAY)
            return True

        # 方法3: 使用 input text 的 Unicode 转义方式（部分设备支持）
        # 将中文转换为 Unicode 转义序列
        unicode_text = ""
        for char in text:
            if ord(char) > 127:
                unicode_text += f"\\u{ord(char):04x}"
            else:
                unicode_text += char

        result = self._run_adb("shell", "input", "text", unicode_text)
        if result.returncode == 0:
            time.sleep(config.OPERATION_DELAY)
            return True

        return False

    def clear_text_field(self) -> bool:
        """
        清空当前输入框

        通过全选+删除清空文本
        """
        # 方法1: Ctrl+A 全选，然后删除
        self._run_adb("shell", "input", "keyevent", "--longpress", "29", "29")  # CTRL
        time.sleep(0.05)
        self._run_adb("shell", "input", "keyevent", "29+31")  # CTRL+A (全选)
        time.sleep(0.1)
        self.input_keyevent(67)  # KEYCODE_DEL
        time.sleep(0.1)

        # 方法2: 备用 - 移到末尾然后删除多次
        self._run_adb("shell", "input", "keyevent", "123")  # KEYCODE_MOVE_END
        time.sleep(0.05)
        # 快速删除 20 个字符
        for _ in range(20):
            self._run_adb("shell", "input", "keyevent", "67")

        return True
