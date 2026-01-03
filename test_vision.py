#!/usr/bin/env python3
"""
test_vision.py - 测试 VisionAgent 的 bbox 解析功能

使用方法：
---------
1. 基础测试（测试坐标转换逻辑，不需要 API）：
   python test_vision.py

2. 测试文字描述查找元素（需要 API 和截图）：
   python test_vision.py find screenshot.png "Chrome 图标"

3. 测试双图片匹配（需要 API、参考图和截图）：
   python test_vision.py match icon.png screenshot.png

4. 测试屏幕分析（需要 API 和截图）：
   python test_vision.py analyze screenshot.png "打开微信"

环境配置：
---------
在 .env 文件中配置：
  LLM_PROVIDER=custom
  CUSTOM_LLM_API_KEY=your-api-key
  CUSTOM_LLM_BASE_URL=https://openrouter.ai/api/v1
  CUSTOM_LLM_MODEL=google/gemini-2.5-flash-preview
"""
import sys
from pathlib import Path

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image
from ai.vision_agent import VisionAgent, ActionType


def test_bbox_to_center():
    """测试 bbox 转换为中心坐标（不需要 API）"""
    print("\n" + "=" * 50)
    print("测试: _bbox_to_center 坐标转换")
    print("=" * 50)

    agent = VisionAgent()

    # 模拟 1080x2400 的屏幕
    width, height = 1080, 2400
    print(f"模拟屏幕尺寸: {width}x{height}")

    # 测试用例
    test_cases = [
        {"xmin": 0, "ymin": 0, "xmax": 100, "ymax": 100},
        {"xmin": 450, "ymin": 450, "xmax": 550, "ymax": 550},
        {"xmin": 900, "ymin": 900, "xmax": 1000, "ymax": 1000},
    ]

    print("\nbbox (0-1000) → 像素坐标:")
    for bbox in test_cases:
        x, y = agent._bbox_to_center(bbox, width, height)
        print(f"  {bbox} → ({x}, {y})")


def test_parse_action():
    """测试 _parse_action 解析 LLM 返回（不需要 API）"""
    print("\n" + "=" * 50)
    print("测试: _parse_action 解析 LLM 返回")
    print("=" * 50)

    agent = VisionAgent()
    image_size = (1080, 2400)
    print(f"模拟屏幕尺寸: {image_size[0]}x{image_size[1]}")

    # 模拟 LLM 返回
    test_responses = [
        '{"action": "tap", "xmin": 400, "ymin": 500, "xmax": 600, "ymax": 600, "reason": "点击按钮"}',
        '{"action": "swipe", "xmin": 700, "ymin": 500, "xmax": 300, "ymax": 500, "reason": "左滑"}',
        '{"action": "press_key", "keycode": 3, "reason": "按HOME键"}',
        '{"action": "success", "reason": "任务完成"}',
    ]

    print("\n解析结果:")
    for response in test_responses:
        action = agent._parse_action(response, image_size)
        print(f"\n  输入: {response}")
        print(f"  解析: action={action.action_type.value}, x={action.x}, y={action.y}", end="")
        if action.x2 is not None:
            print(f", x2={action.x2}, y2={action.y2}", end="")
        print(f", reason={action.reason}")


def test_find_element(image_path: str, element: str):
    """测试 find_element（需要 API）"""
    print("\n" + "=" * 50)
    print("测试: find_element (文字描述查找)")
    print("=" * 50)

    img = Image.open(image_path)
    print(f"截图: {image_path}")
    print(f"尺寸: {img.size}")
    print(f"查找: {element}")

    agent = VisionAgent()
    print(f"LLM: {agent.config.provider}/{agent.config.model}")

    print("\n调用 API...")
    result = agent.find_element(img, element)

    if result:
        print(f"✓ 找到元素，中心坐标: {result}")
    else:
        print("✗ 未找到元素")


def test_find_by_image(ref_path: str, screenshot_path: str):
    """测试 find_element_by_image（需要 API）"""
    print("\n" + "=" * 50)
    print("测试: find_element_by_image (双图匹配)")
    print("=" * 50)

    ref_img = Image.open(ref_path)
    screenshot = Image.open(screenshot_path)
    print(f"参考图: {ref_path} ({ref_img.size})")
    print(f"截图: {screenshot_path} ({screenshot.size})")

    agent = VisionAgent()
    print(f"LLM: {agent.config.provider}/{agent.config.model}")

    print("\n调用 API...")
    result = agent.find_element_by_image(ref_img, screenshot)

    if result:
        print(f"✓ 找到元素，中心坐标: {result}")
    else:
        print("✗ 未找到元素")


def test_analyze_screen(image_path: str, task: str):
    """测试 analyze_screen（需要 API）"""
    print("\n" + "=" * 50)
    print("测试: analyze_screen (屏幕分析)")
    print("=" * 50)

    img = Image.open(image_path)
    print(f"截图: {image_path}")
    print(f"尺寸: {img.size}")
    print(f"任务: {task}")

    agent = VisionAgent()
    print(f"LLM: {agent.config.provider}/{agent.config.model}")

    print("\n调用 API...")
    action = agent.analyze_screen(img, task)

    print(f"\n返回动作:")
    print(f"  类型: {action.action_type.value}")
    print(f"  坐标: x={action.x}, y={action.y}")
    if action.x2 is not None:
        print(f"  终点: x2={action.x2}, y2={action.y2}")
    if action.text:
        print(f"  文本: {action.text}")
    if action.keycode:
        print(f"  按键: {action.keycode}")
    print(f"  原因: {action.reason}")


def print_usage():
    print(__doc__)


def main():
    args = sys.argv[1:]

    if not args:
        # 无参数：运行基础测试
        print("\n运行基础测试（不需要 API）...\n")
        test_bbox_to_center()
        test_parse_action()
        print("\n" + "=" * 50)
        print("基础测试完成！")
        print("=" * 50)
        print("\n如需测试真实 API，请使用以下命令：")
        print("  python test_vision.py find <截图> <元素描述>")
        print("  python test_vision.py match <参考图> <截图>")
        print("  python test_vision.py analyze <截图> <任务描述>")
        return

    cmd = args[0]

    if cmd == "find" and len(args) >= 3:
        # python test_vision.py find screenshot.png "Chrome 图标"
        test_find_element(args[1], args[2])

    elif cmd == "match" and len(args) >= 3:
        # python test_vision.py match icon.png screenshot.png
        test_find_by_image(args[1], args[2])

    elif cmd == "analyze" and len(args) >= 3:
        # python test_vision.py analyze screenshot.png "打开微信"
        test_analyze_screen(args[1], args[2])

    else:
        print_usage()


if __name__ == "__main__":
    main()
