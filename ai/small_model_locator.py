"""
ai/small_model_locator.py
小模型定位器 - 使用 Florence-2 等轻量模型进行快速元素定位

特点：
- 本地运行，无需API调用
- 速度快（~200-500ms vs 大模型 2-4s）
- 适合简单的元素定位任务
- 支持多种后端：Florence-2, YOLO, PaddleOCR 等

配置环境变量：
- SMALL_MODEL_DEVICE: 指定设备 (cuda, cpu, mps)
- SMALL_MODEL_CACHE: 模型缓存目录
- HF_HOME: Hugging Face 缓存目录

安装依赖：
- Florence-2: pip install torch transformers
- PaddleOCR: pip install paddlepaddle paddleocr

GPU 加速（推荐）：
- NVIDIA GPU: pip install torch --index-url https://download.pytorch.org/whl/cu118
- 或使用 CUDA 12: pip install torch --index-url https://download.pytorch.org/whl/cu121

预下载模型（避免首次运行慢）：
  python -c "from transformers import AutoProcessor, AutoModelForCausalLM; AutoProcessor.from_pretrained('microsoft/Florence-2-base', trust_remote_code=True); AutoModelForCausalLM.from_pretrained('microsoft/Florence-2-base', trust_remote_code=True)"
"""
import os
import time
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
from PIL import Image
import io


class SmallModelBackend(Enum):
    """小模型后端"""
    FLORENCE2 = "florence2"      # Microsoft Florence-2
    QWEN_VL = "qwen_vl"          # Qwen-VL (本地)
    PADDLE_OCR = "paddle_ocr"    # PaddleOCR (文字定位)
    MOCK = "mock"                # 模拟（测试用）


@dataclass
class SmallModelResult:
    """小模型定位结果"""
    success: bool
    center_x: int = 0
    center_y: int = 0
    confidence: float = 0.0
    bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)  # x1, y1, x2, y2
    matched_text: str = ""
    elapsed_ms: float = 0.0
    backend: str = ""


class SmallModelLocator:
    """
    小模型定位器

    使用轻量级视觉模型进行快速元素定位。
    比大模型快 5-10 倍，适合简单定位任务。
    """

    def __init__(self, backend: SmallModelBackend = SmallModelBackend.FLORENCE2):
        """
        初始化小模型定位器

        Args:
            backend: 使用的后端模型
        """
        self.backend = backend
        self._model = None
        self._processor = None
        self._device = None
        self._logger = None
        self._initialized = False

    def set_logger(self, logger):
        """设置日志函数"""
        self._logger = logger

    def _log(self, msg: str):
        if self._logger:
            self._logger(f"[SmallModel] {msg}")
        else:
            print(f"[SmallModel] {msg}")

    def initialize(self) -> bool:
        """
        初始化模型（懒加载）

        Returns:
            是否初始化成功
        """
        if self._initialized:
            return True

        if self.backend == SmallModelBackend.FLORENCE2:
            return self._init_florence2()
        elif self.backend == SmallModelBackend.PADDLE_OCR:
            return self._init_paddle_ocr()
        elif self.backend == SmallModelBackend.MOCK:
            self._initialized = True
            return True
        else:
            self._log(f"不支持的后端: {self.backend}")
            return False

    def _init_florence2(self) -> bool:
        """初始化 Florence-2"""
        try:
            import torch
            from transformers import AutoProcessor, AutoModelForCausalLM

            self._log("加载 Florence-2 模型...")
            start = time.time()

            # 检测设备（支持环境变量覆盖）
            env_device = os.environ.get("SMALL_MODEL_DEVICE", "").lower()
            if env_device in ["cuda", "cpu", "mps"]:
                self._device = env_device
            elif torch.cuda.is_available():
                self._device = "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                self._device = "mps"
            else:
                self._device = "cpu"

            self._log(f"使用设备: {self._device}")

            # 加载模型 (使用较小的 base 版本)
            model_name = "microsoft/Florence-2-base"

            # 配置缓存目录
            cache_dir = os.environ.get("SMALL_MODEL_CACHE")

            self._processor = AutoProcessor.from_pretrained(
                model_name,
                trust_remote_code=True,
                cache_dir=cache_dir
            )

            # 加载模型，禁用 SDPA 以兼容新版 transformers
            # attn_implementation="eager" 避免 _supports_sdpa 错误
            model_kwargs = {
                "trust_remote_code": True,
                "cache_dir": cache_dir,
                "attn_implementation": "eager",  # 兼容性修复
            }

            # GPU 使用 float16 加速
            if self._device == "cuda":
                self._log("使用 float16 加速")
                model_kwargs["torch_dtype"] = torch.float16

            self._model = AutoModelForCausalLM.from_pretrained(
                model_name,
                **model_kwargs
            ).to(self._device)

            # 设置为评估模式
            self._model.eval()

            elapsed = (time.time() - start) * 1000
            self._log(f"Florence-2 加载完成: {elapsed:.0f}ms")
            self._initialized = True
            return True

        except ImportError as e:
            self._log(f"缺少依赖: {e}")
            self._log("请安装: pip install torch transformers")
            return False
        except Exception as e:
            self._log(f"初始化 Florence-2 失败: {e}")
            import traceback
            self._log(traceback.format_exc())
            return False

    def _init_paddle_ocr(self) -> bool:
        """初始化 PaddleOCR"""
        try:
            from paddleocr import PaddleOCR

            self._log("加载 PaddleOCR...")
            start = time.time()

            self._model = PaddleOCR(
                use_angle_cls=True,
                lang='ch',
                show_log=False
            )

            elapsed = (time.time() - start) * 1000
            self._log(f"PaddleOCR 加载完成: {elapsed:.0f}ms")
            self._initialized = True
            return True

        except ImportError:
            self._log("缺少依赖，请安装: pip install paddlepaddle paddleocr")
            return False
        except Exception as e:
            self._log(f"初始化 PaddleOCR 失败: {e}")
            return False

    def locate(
        self,
        screenshot: Image.Image,
        description: str
    ) -> SmallModelResult:
        """
        定位元素

        Args:
            screenshot: 屏幕截图
            description: 元素描述（如 "搜索按钮", "输入框"）

        Returns:
            SmallModelResult
        """
        if not self._initialized:
            if not self.initialize():
                return SmallModelResult(
                    success=False,
                    backend=self.backend.value
                )

        start = time.time()

        if self.backend == SmallModelBackend.FLORENCE2:
            result = self._locate_florence2(screenshot, description)
        elif self.backend == SmallModelBackend.PADDLE_OCR:
            result = self._locate_paddle_ocr(screenshot, description)
        elif self.backend == SmallModelBackend.MOCK:
            result = self._locate_mock(screenshot, description)
        else:
            result = SmallModelResult(success=False)

        result.elapsed_ms = (time.time() - start) * 1000
        result.backend = self.backend.value

        return result

    def _locate_florence2(
        self,
        screenshot: Image.Image,
        description: str
    ) -> SmallModelResult:
        """使用 Florence-2 定位"""
        import torch
        import numpy as np

        try:
            # 确保图片是 RGB 格式
            if screenshot.mode != "RGB":
                screenshot = screenshot.convert("RGB")

            # 验证图片有效性
            img_array = np.array(screenshot)
            if img_array is None or img_array.size == 0:
                self._log("图片数据无效")
                return SmallModelResult(success=False)

            self._log(f"图片尺寸: {screenshot.size}, 模式: {screenshot.mode}, 数组形状: {img_array.shape}")

            # Florence-2 使用特定的 prompt 格式进行 grounding
            # <CAPTION_TO_PHRASE_GROUNDING> 任务
            prompt = f"<CAPTION_TO_PHRASE_GROUNDING>{description}"

            # 处理输入 - 使用正确的 API
            try:
                # 新版 API
                inputs = self._processor(
                    text=prompt,
                    images=screenshot,
                    return_tensors="pt"
                )
            except Exception as proc_err:
                self._log(f"处理器调用失败: {proc_err}")
                # 尝试备用方式：分开处理文本和图片
                try:
                    inputs = self._processor(
                        text=[prompt],
                        images=[screenshot],
                        return_tensors="pt",
                        padding=True
                    )
                except Exception as proc_err2:
                    self._log(f"备用处理也失败: {proc_err2}")
                    return SmallModelResult(success=False)

            # 检查 inputs 是否有效
            if inputs is None:
                self._log("处理器返回 None")
                return SmallModelResult(success=False)

            self._log(f"inputs keys: {inputs.keys() if hasattr(inputs, 'keys') else type(inputs)}")

            # 移动到设备
            inputs = inputs.to(self._device)

            # 推理
            try:
                with torch.no_grad():
                    # 使用更简单的生成配置，避免兼容性问题
                    generated_ids = self._model.generate(
                        input_ids=inputs["input_ids"],
                        pixel_values=inputs["pixel_values"],
                        attention_mask=inputs.get("attention_mask"),
                        max_new_tokens=1024,
                        do_sample=False,
                        num_beams=1,  # 使用贪婪解码
                        use_cache=False,  # 禁用 cache 避免 past_key_values 问题
                    )
            except Exception as gen_err:
                self._log(f"generate 失败: {gen_err}")
                import traceback
                self._log(traceback.format_exc())
                return SmallModelResult(success=False)

            self._log(f"generated_ids shape: {generated_ids.shape}")

            # 解码结果
            generated_text = self._processor.batch_decode(
                generated_ids,
                skip_special_tokens=False
            )[0]
            self._log(f"generated_text: {generated_text[:200]}...")

            # 解析 Florence-2 的输出格式
            # 格式类似: <CAPTION_TO_PHRASE_GROUNDING>description<loc_123><loc_456><loc_789><loc_012>
            result = self._processor.post_process_generation(
                generated_text,
                task="<CAPTION_TO_PHRASE_GROUNDING>",
                image_size=(screenshot.width, screenshot.height)
            )

            # 提取边界框
            if result and "bboxes" in result and len(result["bboxes"]) > 0:
                bbox = result["bboxes"][0]  # 取第一个匹配
                x1, y1, x2, y2 = [int(v) for v in bbox]
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2

                self._log(f"Florence-2 找到: bbox={bbox}, center=({center_x}, {center_y})")

                return SmallModelResult(
                    success=True,
                    center_x=center_x,
                    center_y=center_y,
                    confidence=0.9,  # Florence-2 不直接返回置信度
                    bbox=(x1, y1, x2, y2),
                    matched_text=description
                )

            self._log(f"Florence-2 未找到: {description}")
            return SmallModelResult(success=False)

        except Exception as e:
            self._log(f"Florence-2 定位失败: {e}")
            return SmallModelResult(success=False)

    def _locate_paddle_ocr(
        self,
        screenshot: Image.Image,
        text_to_find: str
    ) -> SmallModelResult:
        """使用 PaddleOCR 定位文字"""
        import numpy as np

        try:
            # 转换为 numpy 数组
            img_array = np.array(screenshot)

            # OCR 识别
            result = self._model.ocr(img_array, cls=True)

            if not result or not result[0]:
                return SmallModelResult(success=False)

            # 查找匹配的文字
            best_match = None
            best_score = 0

            for line in result[0]:
                bbox_points, (text, confidence) = line

                # 简单的文字匹配
                if text_to_find.lower() in text.lower():
                    if confidence > best_score:
                        best_score = confidence
                        # bbox_points 是四个角点，转换为 x1,y1,x2,y2
                        xs = [p[0] for p in bbox_points]
                        ys = [p[1] for p in bbox_points]
                        best_match = {
                            "bbox": (min(xs), min(ys), max(xs), max(ys)),
                            "text": text,
                            "confidence": confidence
                        }

            if best_match:
                x1, y1, x2, y2 = best_match["bbox"]
                center_x = int((x1 + x2) / 2)
                center_y = int((y1 + y2) / 2)

                self._log(f"OCR 找到: '{best_match['text']}' at ({center_x}, {center_y})")

                return SmallModelResult(
                    success=True,
                    center_x=center_x,
                    center_y=center_y,
                    confidence=best_match["confidence"],
                    bbox=(int(x1), int(y1), int(x2), int(y2)),
                    matched_text=best_match["text"]
                )

            self._log(f"OCR 未找到: {text_to_find}")
            return SmallModelResult(success=False)

        except Exception as e:
            self._log(f"PaddleOCR 定位失败: {e}")
            return SmallModelResult(success=False)

    def _locate_mock(
        self,
        screenshot: Image.Image,
        description: str
    ) -> SmallModelResult:
        """模拟定位（测试用）"""
        import random

        # 模拟延迟
        time.sleep(0.1)

        # 随机返回一个位置
        return SmallModelResult(
            success=True,
            center_x=random.randint(100, screenshot.width - 100),
            center_y=random.randint(100, screenshot.height - 100),
            confidence=0.85,
            matched_text=description
        )

    def locate_text(
        self,
        screenshot: Image.Image,
        text: str
    ) -> SmallModelResult:
        """
        专门用于定位文字的方法

        优先使用 OCR，比视觉 grounding 更准确
        """
        # 如果当前不是 OCR 后端，临时使用 OCR
        if self.backend != SmallModelBackend.PADDLE_OCR:
            try:
                from paddleocr import PaddleOCR

                if not hasattr(self, '_ocr_model'):
                    self._ocr_model = PaddleOCR(
                        use_angle_cls=True,
                        lang='ch',
                        show_log=False
                    )

                import numpy as np
                img_array = np.array(screenshot)
                result = self._ocr_model.ocr(img_array, cls=True)

                if result and result[0]:
                    for line in result[0]:
                        bbox_points, (ocr_text, confidence) = line
                        if text.lower() in ocr_text.lower():
                            xs = [p[0] for p in bbox_points]
                            ys = [p[1] for p in bbox_points]
                            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)

                            return SmallModelResult(
                                success=True,
                                center_x=int((x1 + x2) / 2),
                                center_y=int((y1 + y2) / 2),
                                confidence=confidence,
                                bbox=(int(x1), int(y1), int(x2), int(y2)),
                                matched_text=ocr_text,
                                backend="paddle_ocr"
                            )
            except:
                pass

        # 回退到通用定位
        return self.locate(screenshot, text)

    def is_available(self) -> bool:
        """检查小模型是否可用"""
        if self.backend == SmallModelBackend.FLORENCE2:
            try:
                import torch
                from transformers import AutoProcessor
                return True
            except ImportError:
                return False
        elif self.backend == SmallModelBackend.PADDLE_OCR:
            try:
                from paddleocr import PaddleOCR
                return True
            except ImportError:
                return False
        elif self.backend == SmallModelBackend.MOCK:
            return True
        return False


# 便捷函数
def create_small_model_locator(
    backend: str = "florence2"
) -> Optional[SmallModelLocator]:
    """
    创建小模型定位器

    Args:
        backend: 后端名称 (florence2, paddle_ocr, mock)

    Returns:
        SmallModelLocator 实例，如果不可用则返回 None
    """
    backend_map = {
        "florence2": SmallModelBackend.FLORENCE2,
        "florence-2": SmallModelBackend.FLORENCE2,
        "paddle_ocr": SmallModelBackend.PADDLE_OCR,
        "paddleocr": SmallModelBackend.PADDLE_OCR,
        "ocr": SmallModelBackend.PADDLE_OCR,
        "mock": SmallModelBackend.MOCK,
    }

    backend_enum = backend_map.get(backend.lower())
    if backend_enum is None:
        print(f"未知后端: {backend}")
        return None

    locator = SmallModelLocator(backend_enum)
    if locator.is_available():
        return locator
    else:
        print(f"后端不可用: {backend}")
        return None


def preload_florence2(device: str = None) -> bool:
    """
    预加载 Florence-2 模型

    在程序启动时调用，避免首次定位时的延迟。

    Args:
        device: 指定设备 (cuda, cpu, mps)，None 则自动检测

    Returns:
        是否加载成功

    Usage:
        # 在程序启动时调用
        from ai.small_model_locator import preload_florence2
        preload_florence2()  # 自动检测 GPU
        preload_florence2("cuda")  # 强制使用 GPU
    """
    if device:
        os.environ["SMALL_MODEL_DEVICE"] = device

    locator = SmallModelLocator(SmallModelBackend.FLORENCE2)
    return locator.initialize()


def check_gpu_available() -> dict:
    """
    检查 GPU 是否可用

    Returns:
        包含 GPU 信息的字典

    Usage:
        from ai.small_model_locator import check_gpu_available
        info = check_gpu_available()
        print(info)
    """
    result = {
        "cuda_available": False,
        "mps_available": False,
        "device_name": None,
        "recommended_device": "cpu"
    }

    try:
        import torch

        if torch.cuda.is_available():
            result["cuda_available"] = True
            result["device_name"] = torch.cuda.get_device_name(0)
            result["recommended_device"] = "cuda"
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            result["mps_available"] = True
            result["device_name"] = "Apple Silicon GPU"
            result["recommended_device"] = "mps"
    except ImportError:
        pass

    return result
