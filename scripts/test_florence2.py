"""
Florence-2 小模型定位器测试脚本

用法：
    python scripts/test_florence2.py                    # 使用默认测试图片
    python scripts/test_florence2.py path/to/image.png  # 使用指定图片
    python scripts/test_florence2.py --benchmark        # 运行性能基准测试

测试内容：
    1. 模型加载时间
    2. 单次定位速度
    3. 定位准确性
    4. 多次定位平均速度
"""
import sys
import time
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def check_dependencies():
    """检查依赖是否安装"""
    print("=" * 50)
    print("检查依赖...")
    print("=" * 50)

    # 检查 PyTorch
    try:
        import torch
        print(f"✓ PyTorch: {torch.__version__}")

        if torch.cuda.is_available():
            print(f"  GPU: {torch.cuda.get_device_name(0)}")
            print(f"  CUDA: {torch.version.cuda}")
        else:
            print("  GPU: 不可用 (将使用 CPU)")
    except ImportError:
        print("✗ PyTorch 未安装")
        print("  安装命令: pip install torch --index-url https://download.pytorch.org/whl/cpu")
        return False

    # 检查 transformers
    try:
        import transformers
        print(f"✓ Transformers: {transformers.__version__}")
    except ImportError:
        print("✗ Transformers 未安装")
        print("  安装命令: pip install transformers")
        return False

    # 检查 einops (Florence-2 依赖)
    try:
        import einops
        print(f"✓ Einops: {einops.__version__}")
    except ImportError:
        print("✗ Einops 未安装")
        print("  安装命令: pip install einops")
        return False

    # 检查 timm (Florence-2 依赖)
    try:
        import timm
        print(f"✓ Timm: {timm.__version__}")
    except ImportError:
        print("✗ Timm 未安装")
        print("  安装命令: pip install timm")
        return False

    # 检查 PIL
    try:
        from PIL import Image
        print(f"✓ Pillow: 已安装")
    except ImportError:
        print("✗ Pillow 未安装")
        print("  安装命令: pip install pillow")
        return False

    print()
    return True


def test_model_loading():
    """测试模型加载"""
    print("=" * 50)
    print("测试模型加载...")
    print("=" * 50)

    from ai.small_model_locator import SmallModelLocator, SmallModelBackend, check_gpu_available

    # 显示 GPU 信息
    gpu_info = check_gpu_available()
    print(f"推荐设备: {gpu_info['recommended_device']}")
    if gpu_info['device_name']:
        print(f"设备名称: {gpu_info['device_name']}")

    print()
    print("加载 Florence-2 模型...")

    start = time.time()
    locator = SmallModelLocator(SmallModelBackend.FLORENCE2)
    success = locator.initialize()
    elapsed = time.time() - start

    if success:
        print(f"✓ 模型加载成功")
        print(f"  加载时间: {elapsed:.2f} 秒")
        print(f"  使用设备: {locator._device}")
    else:
        print(f"✗ 模型加载失败")
        return None

    print()
    return locator


def test_single_locate(locator, image_path: str = None):
    """测试单次定位"""
    print("=" * 50)
    print("测试单次定位...")
    print("=" * 50)

    from PIL import Image, ImageDraw, ImageFont

    # 加载测试图片
    if image_path:
        img_path = Path(image_path)
        if not img_path.exists():
            print(f"✗ 图片不存在: {image_path}")
            return False
        img = Image.open(img_path)
    else:
        # 尝试使用 temp 目录下的截图
        img_path = project_root / "temp" / "current_screenshot.png"
        if img_path.exists():
            img = Image.open(img_path)
        else:
            # 创建一个带有元素的测试图片
            print("未找到测试图片，创建模拟图片...")
            img = Image.new('RGB', (1080, 2400), color=(240, 240, 240))
            draw = ImageDraw.Draw(img)

            # 绘制模拟的搜索按钮
            draw.rectangle([900, 50, 1030, 120], fill=(200, 200, 200), outline=(100, 100, 100))
            draw.text((920, 70), "搜索", fill=(50, 50, 50))

            # 绘制模拟的+号按钮
            draw.rectangle([800, 50, 870, 120], fill=(200, 200, 200), outline=(100, 100, 100))
            draw.text((820, 60), "+", fill=(50, 50, 50))

            # 绘制模拟的输入框
            draw.rectangle([50, 2200, 900, 2280], fill=(255, 255, 255), outline=(150, 150, 150))
            draw.text((70, 2220), "输入消息...", fill=(180, 180, 180))

            # 绘制模拟的发送按钮
            draw.rectangle([920, 2200, 1030, 2280], fill=(0, 200, 0), outline=(0, 150, 0))
            draw.text((950, 2220), "发送", fill=(255, 255, 255))

            img_path = project_root / "temp" / "test_image.png"
            img_path.parent.mkdir(exist_ok=True)
            img.save(img_path)
            print(f"  已创建测试图片: {img_path}")

    # 确保 RGB 格式
    if img.mode != "RGB":
        img = img.convert("RGB")

    print(f"测试图片: {img_path}")
    print(f"图片尺寸: {img.size}")
    print(f"图片模式: {img.mode}")

    # 测试定位
    test_descriptions = [
        "搜索按钮",
        "search button",
        "+号按钮",
        "发送按钮",
        "输入框",
    ]

    print()
    for desc in test_descriptions:
        print(f"定位: '{desc}'")
        start = time.time()
        result = locator.locate(img, desc)
        elapsed = (time.time() - start) * 1000

        if result.success:
            print(f"  ✓ 找到: ({result.center_x}, {result.center_y})")
            print(f"    置信度: {result.confidence:.3f}")
            print(f"    边界框: {result.bbox}")
        else:
            print(f"  ✗ 未找到")
        print(f"    耗时: {elapsed:.0f}ms")
        print()

    return True


def test_benchmark(locator, image_path: str = None, iterations: int = 10):
    """性能基准测试"""
    print("=" * 50)
    print(f"性能基准测试 ({iterations} 次迭代)...")
    print("=" * 50)

    from PIL import Image

    # 加载测试图片
    if image_path:
        img = Image.open(image_path)
    else:
        img_path = project_root / "temp" / "current_screenshot.png"
        if img_path.exists():
            img = Image.open(img_path)
        else:
            img = Image.new('RGB', (1080, 2400), color='white')

    print(f"图片尺寸: {img.size}")

    test_desc = "搜索按钮"
    times = []

    print(f"测试描述: '{test_desc}'")
    print()

    # 预热
    print("预热中...")
    locator.locate(img, test_desc)

    # 基准测试
    print("运行基准测试...")
    for i in range(iterations):
        start = time.time()
        result = locator.locate(img, test_desc)
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)
        status = "✓" if result.success else "✗"
        print(f"  [{i+1:2d}/{iterations}] {status} {elapsed:.0f}ms")

    # 统计
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    print()
    print("=" * 50)
    print("统计结果:")
    print("=" * 50)
    print(f"  平均耗时: {avg_time:.0f}ms")
    print(f"  最小耗时: {min_time:.0f}ms")
    print(f"  最大耗时: {max_time:.0f}ms")
    print(f"  设备: {locator._device}")

    # 性能评估
    print()
    if avg_time < 500:
        print("✓ 性能优秀 (< 500ms)")
    elif avg_time < 1000:
        print("○ 性能良好 (500-1000ms)")
    elif avg_time < 2000:
        print("△ 性能一般 (1-2s)，建议使用 GPU")
    else:
        print("✗ 性能较差 (> 2s)，强烈建议使用 GPU 或禁用小模型")

    return times


def main():
    parser = argparse.ArgumentParser(description='Florence-2 小模型定位器测试')
    parser.add_argument('image', nargs='?', help='测试图片路径')
    parser.add_argument('--benchmark', action='store_true', help='运行性能基准测试')
    parser.add_argument('--iterations', type=int, default=10, help='基准测试迭代次数')
    args = parser.parse_args()

    print()
    print("╔════════════════════════════════════════════════╗")
    print("║       Florence-2 小模型定位器测试脚本          ║")
    print("╚════════════════════════════════════════════════╝")
    print()

    # 检查依赖
    if not check_dependencies():
        print("请先安装缺失的依赖！")
        sys.exit(1)

    # 加载模型
    locator = test_model_loading()
    if locator is None:
        print("模型加载失败！")
        sys.exit(1)

    # 单次定位测试
    test_single_locate(locator, args.image)

    # 基准测试
    if args.benchmark:
        test_benchmark(locator, args.image, args.iterations)

    print()
    print("测试完成！")


if __name__ == "__main__":
    main()
