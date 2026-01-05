"""
core/hybrid_locator.py
混合定位器 - 优先使用 OpenCV，失败时回退到 AI

策略：
1. 首先尝试 OpenCV 模板匹配（快速、免费）
2. 如果模板匹配失败，尝试多尺度匹配
3. 如果仍失败，尝试特征点匹配
4. 最后回退到 AI 视觉定位（慢、付费）
"""
import cv2
import shutil
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

from .opencv_locator import OpenCVLocator, MatchMethod, MatchResult


class LocateStrategy(Enum):
    """定位策略"""
    OPENCV_ONLY = "opencv_only"         # 仅 OpenCV
    AI_ONLY = "ai_only"                 # 仅 AI
    OPENCV_FIRST = "opencv_first"       # OpenCV 优先，失败回退 AI
    AI_FIRST = "ai_first"               # AI 优先（调试用）


@dataclass
class LocateResult:
    """定位结果"""
    success: bool
    center_x: int = 0
    center_y: int = 0
    confidence: float = 0.0
    method_used: str = ""               # opencv_template / opencv_feature / ai
    fallback_used: bool = False         # 是否使用了回退
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}

    def to_tuple(self) -> Optional[Tuple[int, int]]:
        """转换为坐标元组"""
        if self.success:
            return (self.center_x, self.center_y)
        return None


class HybridLocator:
    """
    混合元素定位器

    定位流程：OpenCV → 大模型 AI
    - OpenCV: 最快，免费，适合固定UI
    - 大模型: 准确，但慢(2-4s)，作为回退手段
    """

    def __init__(
        self,
        ai_locator: Callable = None,
        strategy: LocateStrategy = LocateStrategy.OPENCV_FIRST,
        debug_save: bool = True  # 默认开启调试保存
    ):
        """
        初始化混合定位器

        Args:
            ai_locator: AI 定位函数
            strategy: 定位策略
            debug_save: 是否保存调试图片到 temp 目录
        """
        self.opencv = OpenCVLocator()
        self.ai_locator = ai_locator
        self.strategy = strategy
        self._logger = None
        self._debug_save = debug_save
        self._debug_dir = Path("temp/locator_debug")

        # 确保调试目录存在
        if self._debug_save:
            self._debug_dir.mkdir(parents=True, exist_ok=True)

        # 统计信息
        self._stats = {
            "opencv_success": 0,
            "opencv_fail": 0,
            "ai_success": 0,
            "ai_fail": 0,
            "total_calls": 0,
        }

    def set_logger(self, logger):
        """设置日志函数"""
        self._logger = logger
        self.opencv.set_logger(logger)

    def _log(self, msg: str):
        if self._logger:
            self._logger(f"[Hybrid] {msg}")
        else:
            print(f"[Hybrid] {msg}")

    def set_ai_locator(self, ai_locator: Callable):
        """设置 AI 定位器"""
        self.ai_locator = ai_locator

    def set_strategy(self, strategy: LocateStrategy):
        """设置定位策略"""
        self.strategy = strategy

    def set_debug_save(self, enabled: bool):
        """开启/关闭调试图片保存"""
        self._debug_save = enabled
        if enabled:
            self._debug_dir.mkdir(parents=True, exist_ok=True)

    def _save_debug_images(self, screenshot: bytes, template_path: Path):
        """
        保存调试图片

        Args:
            screenshot: 截图字节数据
            template_path: 模板图片路径
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            template_name = template_path.stem

            # 保存截图
            screenshot_path = self._debug_dir / f"screenshot_{template_name}_{timestamp}.png"
            with open(screenshot_path, 'wb') as f:
                f.write(screenshot)

            # 复制参考图
            ref_path = self._debug_dir / f"reference_{template_name}_{timestamp}.png"
            shutil.copy(template_path, ref_path)

            self._log(f"调试图片已保存: {template_name}_{timestamp}")

        except Exception as e:
            self._log(f"保存调试图片失败: {e}")

    def locate(
        self,
        screenshot: bytes,
        template_path: Path,
        strategy: LocateStrategy = None
    ) -> LocateResult:
        """
        定位元素（单个模板）

        Args:
            screenshot: 截图字节数据
            template_path: 模板图片路径
            strategy: 本次使用的策略（覆盖默认策略）

        Returns:
            LocateResult
        """
        strategy = strategy or self.strategy
        self._stats["total_calls"] += 1

        self._log(f"定位目标: {template_path.name}, 策略: {strategy.value}")
        return self._locate_single(screenshot, template_path, strategy)

    def locate_with_variants(
        self,
        screenshot: bytes,
        template_paths: list,
        strategy: LocateStrategy = None
    ) -> LocateResult:
        """
        使用多个变体图片定位元素（用于多设备适配）

        依次尝试每个变体图片，返回第一个成功的结果。

        Args:
            screenshot: 截图字节数据
            template_paths: 模板图片路径列表（按优先级排序）
            strategy: 本次使用的策略

        Returns:
            LocateResult
        """
        if not template_paths:
            return LocateResult(success=False, details={"error": "无模板图片"})

        strategy = strategy or self.strategy
        self._stats["total_calls"] += 1

        self._log(f"定位目标 (含 {len(template_paths)} 个变体), 策略: {strategy.value}")

        # 依次尝试每个变体
        for i, template_path in enumerate(template_paths):
            variant_name = template_path.name
            if i > 0:
                self._log(f"  尝试变体 {i + 1}: {variant_name}")

            result = self._locate_single(screenshot, template_path, strategy)
            if result.success:
                result.details["matched_variant"] = variant_name
                return result

        # 所有变体都失败
        self._log(f"所有 {len(template_paths)} 个变体均未匹配")
        return LocateResult(
            success=False,
            details={"tried_variants": [p.name for p in template_paths]}
        )

    def locate_multiple_parallel(
        self,
        screenshot: bytes,
        targets: Dict[str, list],
    ) -> Dict[str, LocateResult]:
        """
        并行检测多个目标（仅 OpenCV，用于预置流程加速）

        Args:
            screenshot: 截图字节数据
            targets: 目标字典，格式为 {"目标名": [模板路径列表], ...}
                     例如: {"home_button": [path1, path2], "back": [path3]}

        Returns:
            结果字典，格式为 {"目标名": LocateResult, ...}
        """
        import concurrent.futures

        results = {}

        # 解码截图
        nparr = np.frombuffer(screenshot, np.uint8)
        screenshot_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if screenshot_cv is None:
            for name in targets:
                results[name] = LocateResult(success=False, details={"error": "截图解码失败"})
            return results

        def detect_single_variant(target_name: str, template_path: Path) -> Tuple[str, Path, LocateResult]:
            """检测单个变体"""
            try:
                template = cv2.imread(str(template_path))
                if template is None:
                    self._log(f"  [检测] {target_name}/{template_path.name}: 无法读取图片")
                    return target_name, template_path, LocateResult(success=False)

                # 尝试模板匹配
                variant_name = template_path.name
                match_result = self.opencv._template_match(screenshot_cv, template, variant_name)
                if match_result.success:
                    self._log(f"  [匹配成功] {target_name}/{variant_name}: 模板匹配 置信度={match_result.confidence:.3f}")
                    return target_name, template_path, LocateResult(
                        success=True,
                        center_x=match_result.center_x,
                        center_y=match_result.center_y,
                        confidence=match_result.confidence,
                        method_used="opencv_template",
                        details={"matched_variant": variant_name}
                    )

                # 尝试多尺度匹配
                match_result = self.opencv._multi_scale_match(screenshot_cv, template, variant_name)
                if match_result.success:
                    self._log(f"  [匹配成功] {target_name}/{variant_name}: 多尺度匹配 置信度={match_result.confidence:.3f}")
                    return target_name, template_path, LocateResult(
                        success=True,
                        center_x=match_result.center_x,
                        center_y=match_result.center_y,
                        confidence=match_result.confidence,
                        method_used="opencv_multi_scale",
                        details={"matched_variant": template_path.name}
                    )
            except Exception as e:
                self._log(f"  [检测异常] {target_name}/{template_path.name}: {e}")

            return target_name, template_path, LocateResult(success=False)

        # 构建所有检测任务（目标+变体的笛卡尔积）
        all_tasks = []
        for name, paths in targets.items():
            for path in paths:
                all_tasks.append((name, path))

        self._log(f"并行检测任务: {[(n, p.name) for n, p in all_tasks]}")

        # 并行检测所有目标的所有变体
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(all_tasks)) as executor:
            futures = {
                executor.submit(detect_single_variant, name, path): (name, path)
                for name, path in all_tasks
            }

            # 收集结果，选择置信度最高的成功匹配
            for future in concurrent.futures.as_completed(futures):
                try:
                    target_name, template_path, result = future.result()
                    # 决定是否更新结果
                    should_update = False
                    if target_name not in results:
                        # 第一个结果
                        should_update = True
                    elif result.success:
                        if not results[target_name].success:
                            # 新结果成功，旧结果失败
                            should_update = True
                        elif result.confidence > results[target_name].confidence:
                            # 新结果置信度更高
                            should_update = True
                            self._log(f"  [更优匹配] {target_name}: {template_path.name} ({result.confidence:.3f}) > 之前 ({results[target_name].confidence:.3f})")

                    if should_update:
                        results[target_name] = result
                        if result.success:
                            self._log(f"  [结果] {target_name}: 成功 (变体={template_path.name})")
                except Exception as e:
                    target_name, _ = futures[future]
                    self._log(f"  [结果异常] {target_name}: {e}")
                    if target_name not in results:
                        results[target_name] = LocateResult(success=False, details={"error": str(e)})

        # 确保所有目标都有结果
        for name in targets:
            if name not in results:
                results[name] = LocateResult(success=False, details={"tried": [p.name for p in targets[name]]})

        # 汇总日志
        self._log(f"  [汇总] 检测结果: {[(k, v.success) for k, v in results.items()]}")

        return results

    def _locate_single(
        self,
        screenshot: bytes,
        template_path: Path,
        strategy: LocateStrategy
    ) -> LocateResult:
        """定位单个模板"""

        if strategy == LocateStrategy.OPENCV_ONLY:
            result = self._locate_opencv(screenshot, template_path)
            # 只在失败时保存调试图片
            if not result.success and self._debug_save:
                self._save_debug_images(screenshot, template_path)
            return result

        elif strategy == LocateStrategy.AI_ONLY:
            return self._locate_ai(screenshot, template_path)

        elif strategy == LocateStrategy.OPENCV_FIRST:
            # 1. 先尝试 OpenCV
            result = self._locate_opencv(screenshot, template_path)
            if result.success:
                return result

            # OpenCV 失败，保存调试图片
            if self._debug_save:
                self._save_debug_images(screenshot, template_path)

            # 2. 回退到 AI
            self._log("OpenCV 失败，回退到 AI")
            ai_result = self._locate_ai(screenshot, template_path)
            ai_result.fallback_used = True
            return ai_result

        elif strategy == LocateStrategy.AI_FIRST:
            # 先尝试 AI
            result = self._locate_ai(screenshot, template_path)
            if result.success:
                return result

            # 回退到 OpenCV
            self._log("AI 定位失败，回退到 OpenCV")
            opencv_result = self._locate_opencv(screenshot, template_path)
            opencv_result.fallback_used = True
            return opencv_result

        return LocateResult(success=False, details={"error": f"未知策略: {strategy}"})

    def _locate_opencv(self, screenshot: bytes, template_path: Path) -> LocateResult:
        """
        使用 OpenCV 定位

        尝试顺序：
        1. 模板匹配（快速）
        2. 多尺度匹配（处理缩放）
        3. 特征点匹配（处理旋转/变形）
        """
        methods = [
            (MatchMethod.TEMPLATE, "opencv_template"),
            (MatchMethod.MULTI_SCALE, "opencv_multi_scale"),
            (MatchMethod.FEATURE, "opencv_feature"),
        ]

        for method, method_name in methods:
            self._log(f"尝试 {method_name}")

            result = self.opencv.locate_from_bytes(screenshot, template_path, method)

            if result.success:
                self._stats["opencv_success"] += 1
                self._log(f"{method_name} 成功: ({result.center_x}, {result.center_y}), 置信度: {result.confidence:.3f}")

                return LocateResult(
                    success=True,
                    center_x=result.center_x,
                    center_y=result.center_y,
                    confidence=result.confidence,
                    method_used=method_name,
                    details=result.details
                )

        self._stats["opencv_fail"] += 1
        self._log("所有 OpenCV 方法均失败")

        return LocateResult(
            success=False,
            method_used="opencv",
            details={"tried_methods": [m[1] for m in methods]}
        )

    def _locate_ai(self, screenshot: bytes, template_path: Path) -> LocateResult:
        """使用 AI 定位"""
        if self.ai_locator is None:
            self._log("AI 定位器未设置")
            return LocateResult(
                success=False,
                method_used="ai",
                details={"error": "AI 定位器未设置"}
            )

        try:
            self._log(f"调用 AI 定位: {template_path.name}")
            coords = self.ai_locator(screenshot, template_path)

            if coords:
                self._stats["ai_success"] += 1
                self._log(f"AI 定位成功: {coords}")

                return LocateResult(
                    success=True,
                    center_x=coords[0],
                    center_y=coords[1],
                    confidence=1.0,  # AI 不提供置信度，假设成功就是高置信
                    method_used="ai",
                    details={"template": template_path.name}
                )
            else:
                self._stats["ai_fail"] += 1
                self._log("AI 定位失败: 未找到目标")

                return LocateResult(
                    success=False,
                    method_used="ai",
                    details={"template": template_path.name}
                )

        except Exception as e:
            self._stats["ai_fail"] += 1
            self._log(f"AI 定位异常: {e}")

            return LocateResult(
                success=False,
                method_used="ai",
                details={"error": str(e)}
            )

    def locate_by_text(
        self,
        screenshot: bytes,
        text: str,
        ocr_engine: Callable = None
    ) -> LocateResult:
        """
        通过文字定位元素

        Args:
            screenshot: 截图字节数据
            text: 要查找的文字
            ocr_engine: OCR 引擎函数，签名: (screenshot_bytes) -> List[Dict]

        Returns:
            LocateResult
        """
        if ocr_engine is None:
            # 如果没有 OCR 引擎，尝试使用 AI
            if self.ai_locator:
                self._log(f"通过 AI 定位文字: {text}")
                # 这里需要特殊处理，因为是文字而不是图片
                # 暂时返回失败，让调用者使用其他方法
                return LocateResult(
                    success=False,
                    method_used="text",
                    details={"error": "文字定位需要 OCR 引擎或专门的 AI 接口"}
                )

            return LocateResult(
                success=False,
                method_used="text",
                details={"error": "OCR 引擎未设置"}
            )

        try:
            self._log(f"OCR 定位文字: {text}")
            # 调用 OCR
            results = ocr_engine(screenshot)

            # 查找匹配的文字
            for item in results:
                if text in item.get('text', ''):
                    bbox = item.get('bbox', [])
                    if len(bbox) >= 4:
                        # 计算中心点
                        center_x = int((bbox[0] + bbox[2]) / 2)
                        center_y = int((bbox[1] + bbox[3]) / 2)

                        return LocateResult(
                            success=True,
                            center_x=center_x,
                            center_y=center_y,
                            confidence=item.get('confidence', 0.9),
                            method_used="ocr",
                            details={"matched_text": item.get('text')}
                        )

            return LocateResult(
                success=False,
                method_used="ocr",
                details={"error": f"未找到文字: {text}"}
            )

        except Exception as e:
            return LocateResult(
                success=False,
                method_used="ocr",
                details={"error": str(e)}
            )

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self._stats.copy()

        # 计算成功率
        total_opencv = stats["opencv_success"] + stats["opencv_fail"]
        total_ai = stats["ai_success"] + stats["ai_fail"]

        if total_opencv > 0:
            stats["opencv_success_rate"] = stats["opencv_success"] / total_opencv
        else:
            stats["opencv_success_rate"] = 0

        if total_ai > 0:
            stats["ai_success_rate"] = stats["ai_success"] / total_ai
        else:
            stats["ai_success_rate"] = 0

        return stats

    def reset_stats(self):
        """重置统计信息"""
        self._stats = {
            "opencv_success": 0,
            "opencv_fail": 0,
            "ai_success": 0,
            "ai_fail": 0,
            "total_calls": 0,
        }


# 便捷函数
def create_hybrid_locator(vision_agent=None) -> HybridLocator:
    """
    创建混合定位器

    Args:
        vision_agent: VisionAgent 实例（可选）

    Returns:
        HybridLocator 实例
    """
    locator = HybridLocator()

    if vision_agent:
        # 包装 VisionAgent 的定位方法
        def ai_locate(screenshot_bytes: bytes, template_path: Path):
            from PIL import Image
            import io
            # 将 bytes 转换为 PIL Image
            screenshot_image = Image.open(io.BytesIO(screenshot_bytes))
            template_image = Image.open(template_path)
            return vision_agent.find_element_by_image(template_image, screenshot_image)

        locator.set_ai_locator(ai_locate)

    return locator
