"""
core/opencv_locator.py
OpenCV 元素定位器 - 使用模板匹配和特征点匹配定位元素

特点：
- 免费、快速、离线
- 适用于固定 UI 元素（图标、按钮等）
- 支持多种匹配算法
"""
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from enum import Enum


class MatchMethod(Enum):
    """匹配方法"""
    TEMPLATE = "template"           # 模板匹配
    FEATURE = "feature"             # 特征点匹配
    MULTI_SCALE = "multi_scale"     # 多尺度模板匹配


@dataclass
class MatchResult:
    """匹配结果"""
    success: bool
    center_x: int = 0
    center_y: int = 0
    confidence: float = 0.0
    method: str = ""
    bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, w, h
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class OpenCVLocator:
    """
    OpenCV 元素定位器

    使用模板匹配和特征点匹配来定位屏幕元素。
    """

    # 模板匹配阈值
    TEMPLATE_THRESHOLD = 0.75
    # 特征点匹配阈值（用于 Lowe's ratio test）
    FEATURE_THRESHOLD = 0.9
    # 特征点匹配最终置信度阈值
    FEATURE_CONFIDENCE_THRESHOLD = 0.7
    # 多尺度匹配的缩放范围
    SCALE_RANGE = (0.8, 1.2)
    SCALE_STEPS = 10

    def __init__(self):
        self._logger = None
        # 初始化特征检测器
        self._orb = cv2.ORB_create(nfeatures=1000)
        self._bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    def set_logger(self, logger):
        """设置日志函数"""
        self._logger = logger

    def _log(self, msg: str):
        if self._logger:
            self._logger(f"[OpenCV] {msg}")
        else:
            print(f"[OpenCV] {msg}")

    def load_image(self, path: Path) -> Optional[np.ndarray]:
        """加载图片"""
        if not path.exists():
            self._log(f"图片不存在: {path}")
            return None

        img = cv2.imread(str(path))
        if img is None:
            self._log(f"无法读取图片: {path}")
            return None

        return img

    def locate(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        method: MatchMethod = MatchMethod.TEMPLATE
    ) -> MatchResult:
        """
        在截图中定位模板

        Args:
            screenshot: 屏幕截图 (BGR)
            template: 模板图片 (BGR)
            method: 匹配方法

        Returns:
            MatchResult
        """
        if screenshot is None or template is None:
            return MatchResult(success=False, details={"error": "图片为空"})

        if method == MatchMethod.TEMPLATE:
            return self._template_match(screenshot, template)
        elif method == MatchMethod.FEATURE:
            return self._feature_match(screenshot, template)
        elif method == MatchMethod.MULTI_SCALE:
            return self._multi_scale_match(screenshot, template)
        else:
            return MatchResult(success=False, details={"error": f"未知方法: {method}"})

    def locate_all(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        method: MatchMethod = MatchMethod.TEMPLATE,
        max_count: int = 10
    ) -> List[MatchResult]:
        """
        在截图中定位所有匹配的模板

        Args:
            screenshot: 屏幕截图
            template: 模板图片
            method: 匹配方法
            max_count: 最大返回数量

        Returns:
            MatchResult 列表
        """
        if screenshot is None or template is None:
            return []

        if method == MatchMethod.TEMPLATE:
            return self._template_match_all(screenshot, template, max_count)
        else:
            # 其他方法暂不支持多匹配
            result = self.locate(screenshot, template, method)
            return [result] if result.success else []

    def _template_match(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        template_name: str = ""
    ) -> MatchResult:
        """
        模板匹配

        使用 cv2.matchTemplate 进行匹配
        """
        # 转灰度
        gray_screen = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        h, w = gray_template.shape

        # 检查模板是否比截图大
        if h > gray_screen.shape[0] or w > gray_screen.shape[1]:
            return MatchResult(
                success=False,
                method="template",
                details={"error": "模板比截图大"}
            )

        # 模板匹配
        result = cv2.matchTemplate(gray_screen, gray_template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        name_suffix = f" [{template_name}]" if template_name else ""
        self._log(f"模板匹配置信度: {max_val:.3f} (阈值: {self.TEMPLATE_THRESHOLD}){name_suffix}")

        if max_val >= self.TEMPLATE_THRESHOLD:
            top_left = max_loc
            center_x = top_left[0] + w // 2
            center_y = top_left[1] + h // 2

            return MatchResult(
                success=True,
                center_x=center_x,
                center_y=center_y,
                confidence=float(max_val),
                method="template",
                bbox=(top_left[0], top_left[1], w, h),
                details={"threshold": self.TEMPLATE_THRESHOLD}
            )

        return MatchResult(
            success=False,
            confidence=float(max_val),
            method="template",
            details={"threshold": self.TEMPLATE_THRESHOLD}
        )

    def _template_match_all(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        max_count: int = 10
    ) -> List[MatchResult]:
        """
        模板匹配 - 查找所有匹配
        """
        gray_screen = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        h, w = gray_template.shape

        if h > gray_screen.shape[0] or w > gray_screen.shape[1]:
            return []

        result = cv2.matchTemplate(gray_screen, gray_template, cv2.TM_CCOEFF_NORMED)

        # 找到所有超过阈值的位置
        locations = np.where(result >= self.TEMPLATE_THRESHOLD)
        matches = []

        # 去重（使用非极大值抑制）
        points = list(zip(*locations[::-1]))  # (x, y) 格式

        if not points:
            return []

        # 按置信度排序
        scored_points = [(x, y, result[y, x]) for x, y in points]
        scored_points.sort(key=lambda p: p[2], reverse=True)

        # 非极大值抑制
        selected = []
        for x, y, score in scored_points:
            # 检查是否与已选点太近
            too_close = False
            for sx, sy, _ in selected:
                if abs(x - sx) < w // 2 and abs(y - sy) < h // 2:
                    too_close = True
                    break

            if not too_close:
                selected.append((x, y, score))
                if len(selected) >= max_count:
                    break

        # 构建结果
        for x, y, score in selected:
            matches.append(MatchResult(
                success=True,
                center_x=x + w // 2,
                center_y=y + h // 2,
                confidence=float(score),
                method="template",
                bbox=(x, y, w, h)
            ))

        self._log(f"模板匹配找到 {len(matches)} 个结果")
        return matches

    def _multi_scale_match(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        template_name: str = ""
    ) -> MatchResult:
        """
        多尺度模板匹配

        在不同缩放级别下进行匹配，适应不同分辨率的屏幕。
        """
        gray_screen = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        best_match = None
        best_val = 0
        best_scale = 1.0

        h, w = gray_template.shape

        # 生成缩放比例
        scales = np.linspace(
            self.SCALE_RANGE[0],
            self.SCALE_RANGE[1],
            self.SCALE_STEPS
        )

        for scale in scales:
            # 缩放模板
            new_w = int(w * scale)
            new_h = int(h * scale)

            if new_w < 10 or new_h < 10:
                continue
            if new_w > gray_screen.shape[1] or new_h > gray_screen.shape[0]:
                continue

            resized = cv2.resize(gray_template, (new_w, new_h))

            # 匹配
            result = cv2.matchTemplate(gray_screen, resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > best_val:
                best_val = max_val
                best_match = (max_loc, new_w, new_h)
                best_scale = scale

        name_suffix = f" [{template_name}]" if template_name else ""
        self._log(f"多尺度匹配最佳置信度: {best_val:.3f}, 缩放: {best_scale:.2f}{name_suffix}")

        if best_val >= self.TEMPLATE_THRESHOLD and best_match:
            top_left, matched_w, matched_h = best_match
            center_x = top_left[0] + matched_w // 2
            center_y = top_left[1] + matched_h // 2

            return MatchResult(
                success=True,
                center_x=center_x,
                center_y=center_y,
                confidence=float(best_val),
                method="multi_scale",
                bbox=(top_left[0], top_left[1], matched_w, matched_h),
                details={"scale": best_scale, "threshold": self.TEMPLATE_THRESHOLD}
            )

        return MatchResult(
            success=False,
            confidence=float(best_val),
            method="multi_scale",
            details={"best_scale": best_scale}
        )

    def _feature_match(
        self,
        screenshot: np.ndarray,
        template: np.ndarray
    ) -> MatchResult:
        """
        特征点匹配

        使用 ORB 特征检测器和 BFMatcher 进行匹配。
        对旋转、缩放有一定的鲁棒性。
        """
        # 转灰度
        gray_screen = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        # 检测特征点
        kp1, des1 = self._orb.detectAndCompute(gray_template, None)
        kp2, des2 = self._orb.detectAndCompute(gray_screen, None)

        if des1 is None or des2 is None:
            return MatchResult(
                success=False,
                method="feature",
                details={"error": "无法检测特征点"}
            )

        if len(kp1) < 4 or len(kp2) < 4:
            return MatchResult(
                success=False,
                method="feature",
                details={"error": "特征点不足"}
            )

        # KNN 匹配
        try:
            matches = self._bf.knnMatch(des1, des2, k=2)
        except cv2.error:
            return MatchResult(
                success=False,
                method="feature",
                details={"error": "匹配失败"}
            )

        # 应用 Lowe's ratio test
        good_matches = []
        for m_n in matches:
            if len(m_n) == 2:
                m, n = m_n
                if m.distance < self.FEATURE_THRESHOLD * n.distance:
                    good_matches.append(m)

        self._log(f"特征点匹配: {len(good_matches)}/{len(kp1)} 个好匹配")

        if len(good_matches) < 4:
            return MatchResult(
                success=False,
                method="feature",
                confidence=len(good_matches) / max(len(kp1), 1),
                details={"good_matches": len(good_matches), "total_keypoints": len(kp1)}
            )

        # 计算单应性矩阵
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        try:
            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        except cv2.error:
            return MatchResult(
                success=False,
                method="feature",
                details={"error": "单应性计算失败"}
            )

        if M is None:
            return MatchResult(
                success=False,
                method="feature",
                details={"error": "无法计算单应性矩阵"}
            )

        # 计算模板在截图中的位置
        h, w = gray_template.shape
        corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
        transformed = cv2.perspectiveTransform(corners, M)

        # 计算中心点
        center_x = int(np.mean(transformed[:, 0, 0]))
        center_y = int(np.mean(transformed[:, 0, 1]))

        # 计算边界框
        x_min = int(np.min(transformed[:, 0, 0]))
        y_min = int(np.min(transformed[:, 0, 1]))
        x_max = int(np.max(transformed[:, 0, 0]))
        y_max = int(np.max(transformed[:, 0, 1]))

        # 检查结果是否合理
        if x_min < 0 or y_min < 0 or x_max > screenshot.shape[1] or y_max > screenshot.shape[0]:
            return MatchResult(
                success=False,
                method="feature",
                details={"error": "匹配位置超出屏幕范围"}
            )

        # 计算置信度
        inliers = np.sum(mask) if mask is not None else 0
        confidence = inliers / len(good_matches) if good_matches else 0

        # 检查置信度是否达到阈值
        if confidence < self.FEATURE_CONFIDENCE_THRESHOLD:
            self._log(f"特征点匹配置信度不足: {confidence:.3f} (阈值: {self.FEATURE_CONFIDENCE_THRESHOLD})")
            return MatchResult(
                success=False,
                confidence=float(confidence),
                method="feature",
                details={
                    "good_matches": len(good_matches),
                    "inliers": int(inliers),
                    "total_keypoints": len(kp1),
                    "threshold": self.FEATURE_CONFIDENCE_THRESHOLD
                }
            )

        return MatchResult(
            success=True,
            center_x=center_x,
            center_y=center_y,
            confidence=float(confidence),
            method="feature",
            bbox=(x_min, y_min, x_max - x_min, y_max - y_min),
            details={
                "good_matches": len(good_matches),
                "inliers": int(inliers),
                "total_keypoints": len(kp1)
            }
        )

    def locate_by_path(
        self,
        screenshot_path: Path,
        template_path: Path,
        method: MatchMethod = MatchMethod.TEMPLATE
    ) -> MatchResult:
        """
        通过文件路径进行定位

        Args:
            screenshot_path: 截图路径
            template_path: 模板路径
            method: 匹配方法

        Returns:
            MatchResult
        """
        screenshot = self.load_image(screenshot_path)
        template = self.load_image(template_path)

        if screenshot is None:
            return MatchResult(success=False, details={"error": f"无法加载截图: {screenshot_path}"})
        if template is None:
            return MatchResult(success=False, details={"error": f"无法加载模板: {template_path}"})

        self._log(f"定位: {template_path.name} in {screenshot_path.name}")
        return self.locate(screenshot, template, method)

    def locate_from_bytes(
        self,
        screenshot_bytes: bytes,
        template_path: Path,
        method: MatchMethod = MatchMethod.TEMPLATE
    ) -> MatchResult:
        """
        从字节数据定位

        Args:
            screenshot_bytes: 截图字节数据
            template_path: 模板路径
            method: 匹配方法

        Returns:
            MatchResult
        """
        # 解码截图
        nparr = np.frombuffer(screenshot_bytes, np.uint8)
        screenshot = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        template = self.load_image(template_path)

        if screenshot is None:
            return MatchResult(success=False, details={"error": "无法解码截图"})
        if template is None:
            return MatchResult(success=False, details={"error": f"无法加载模板: {template_path}"})

        self._log(f"定位: {template_path.name} (截图: {screenshot.shape[1]}x{screenshot.shape[0]})")
        return self.locate(screenshot, template, method)
