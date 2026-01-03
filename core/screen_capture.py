"""
core/screen_capture.py
截屏模块 - 支持多种截屏方式
"""
import subprocess
import time
import io
import tempfile
from pathlib import Path
from typing import Optional, Union
from PIL import Image
import numpy as np

import config
from core.adb_controller import ADBController


class ScreenCapture:
    """屏幕截图管理器"""

    def __init__(self, adb: ADBController):
        self.adb = adb
        # 使用 tempfile 获取系统兼容的临时目录，解决 Termux 权限问题
        self._temp_dir = Path(tempfile.gettempdir()) / "android_remote"
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._capture_count = 0
        self._use_fast_mode = True  # 默认使用快速模式

    def capture(self, save_path: Optional[str] = None) -> Image.Image:
        """
        截取屏幕

        Args:
            save_path: 可选的保存路径

        Returns:
            PIL Image 对象
        """
        self._capture_count += 1

        # 优先使用快速模式
        if self._use_fast_mode:
            try:
                return self._capture_optimized()
            except Exception as e:
                print(f"[截图] 快速模式失败，切换到标准模式: {e}")
                self._use_fast_mode = False

        if save_path is None:
            save_path = str(self._temp_dir / f"capture_{self._capture_count}.png")

        if self.adb.screenshot(save_path):
            return Image.open(save_path)
        raise RuntimeError("截图失败")

    def _capture_optimized(self) -> Image.Image:
        """
        优化的截图方式 - 多种策略尝试减少传输数据量
        """
        start = time.time()

        # 方案1: 使用 gzip 压缩 PNG (减少约 30-50% 数据量)
        try:
            cmd = [
                config.ADB_PATH, "-s", self.adb.device_address,
                "exec-out", "sh", "-c", "screencap -p | gzip -1"
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=60
            )

            if result.returncode == 0 and result.stdout:
                import gzip
                png_data = gzip.decompress(result.stdout)
                img = Image.open(io.BytesIO(png_data))
                elapsed = time.time() - start
                data_kb = len(result.stdout) / 1024
                print(f"[截图] gzip模式: {elapsed:.2f}s, 传输 {data_kb:.0f}KB")
                return img
        except Exception as e:
            print(f"[截图] gzip模式失败: {e}")

        # 方案2: 直接获取 PNG（备用）
        try:
            result = subprocess.run(
                [config.ADB_PATH, "-s", self.adb.device_address,
                 "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=120
            )

            if result.returncode == 0 and result.stdout:
                img = Image.open(io.BytesIO(result.stdout))
                elapsed = time.time() - start
                data_kb = len(result.stdout) / 1024
                print(f"[截图] 标准模式: {elapsed:.2f}s, 传输 {data_kb:.0f}KB")
                return img
        except Exception as e:
            print(f"[截图] 标准模式失败: {e}")

        raise RuntimeError("截图失败")

    def capture_to_numpy(self) -> np.ndarray:
        """截取屏幕并返回 numpy 数组（用于 OpenCV）"""
        img = self.capture()
        return np.array(img)

    def capture_to_bytes(self) -> bytes:
        """截取屏幕并返回 bytes（用于 LLM API）"""
        img = self.capture()
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def capture_fast(self) -> bytes:
        """
        快速截图方式（直接通过 adb exec-out）
        延迟更低，但可能不如标准方式稳定
        """
        result = subprocess.run(
            [config.ADB_PATH, "-s", self.adb.device_address,
             "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout
        raise RuntimeError("快速截图失败")

    def wait_for_element(
        self,
        template_path: str,
        timeout: float = 10.0,
        threshold: float = 0.8
    ) -> Optional[tuple]:
        """
        等待某个元素出现在屏幕上（基于模板匹配）

        Args:
            template_path: 模板图片路径
            timeout: 超时时间（秒）
            threshold: 匹配阈值

        Returns:
            元素中心坐标 (x, y) 或 None
        """
        import cv2

        template = cv2.imread(template_path)
        if template is None:
            raise ValueError(f"无法读取模板图片: {template_path}")

        start_time = time.time()
        while time.time() - start_time < timeout:
            screen = self.capture_to_numpy()
            screen_bgr = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)

            result = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= threshold:
                h, w = template.shape[:2]
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2
                return (center_x, center_y)

            time.sleep(0.5)

        return None

    def find_element(
        self,
        template_path: str,
        threshold: float = 0.8
    ) -> Optional[tuple]:
        """
        在当前屏幕查找元素

        Args:
            template_path: 模板图片路径
            threshold: 匹配阈值

        Returns:
            元素中心坐标 (x, y) 或 None
        """
        import cv2

        template = cv2.imread(template_path)
        if template is None:
            raise ValueError(f"无法读取模板图片: {template_path}")

        screen = self.capture_to_numpy()
        screen_bgr = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)

        result = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            h, w = template.shape[:2]
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return (center_x, center_y)

        return None

    def cleanup(self):
        """清理临时文件"""
        import shutil
        if self._temp_dir.exists():
            shutil.rmtree(self._temp_dir)
