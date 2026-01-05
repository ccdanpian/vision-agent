#!/usr/bin/env python3
"""
test_planner.py - 测试任务规划器（不需要连接手机）

使用方法：
---------
1. 基础测试（测试 AssetsManager，不需要 API）：
   python test_planner.py

2. 测试任务规划（需要 API 和截图）：
   python test_planner.py plan screenshot.png "打开微信"

3. 测试元素定位（需要 API 和截图）：
   python test_planner.py locate screenshot.png "微信图标"

4. 测试双图匹配定位（需要 API、参考图和截图）：
   python test_planner.py match icon.png screenshot.png

5. 测试验证器（需要 API 和截图）：
   python test_planner.py verify screenshot.png "已打开微信主界面"

环境配置：
---------
在 .env 文件中配置：
  LLM_PROVIDER=custom
  CUSTOM_LLM_API_KEY=your-api-key
  CUSTOM_LLM_BASE_URL=https://openrouter.ai/api/v1
  CUSTOM_LLM_MODEL=google/gemini-2.5-flash-preview
"""
import sys
import json
from pathlib import Path

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image


def test_assets_manager():
    """测试参考图库管理器（不需要 API）"""
    print("\n" + "=" * 60)
    print("测试: AssetsManager 参考图库管理")
    print("=" * 60)

    from ai.planner import AssetsManager

    assets = AssetsManager()

    print(f"\n资源目录: {assets.assets_dir}")
    print(f"索引版本: {assets.index.get('version', 'N/A')}")

    # 获取可用参考图
    refs = assets.get_available_refs()

    print("\n可用参考图:")
    for category, items in refs.items():
        print(f"\n  [{category}]")
        if items:
            for item in items[:5]:  # 只显示前5个
                print(f"    - {item}")
            if len(items) > 5:
                print(f"    ... 共 {len(items)} 个")
        else:
            print("    (暂无，需要添加图片)")

    # 测试别名解析
    print("\n别名解析测试:")
    test_aliases = ["微信", "WeChat", "wechat", "Chrome", "设置"]
    for alias in test_aliases:
        resolved = assets.resolve_alias(alias)
        print(f"  '{alias}' → {resolved if resolved else '未找到'}")


def test_planner(image_path: str, task: str):
    """测试任务规划器（需要 API）"""
    print("\n" + "=" * 60)
    print("测试: Planner 任务规划")
    print("=" * 60)

    from ai.planner import Planner

    # 加载截图
    img = Image.open(image_path)
    print(f"\n截图: {image_path}")
    print(f"尺寸: {img.size}")
    print(f"任务: {task}")

    # 创建规划器
    planner = Planner()
    print(f"LLM: {planner.vision.config.provider}/{planner.vision.config.model}")

    print("\n调用 API 生成规划...")
    plan = planner.plan(task, img)

    # 显示规划结果
    print("\n" + "-" * 40)
    print("规划结果:")
    print("-" * 40)

    print(f"\n【分析】")
    for key, value in plan.analysis.items():
        print(f"  {key}: {value}")

    print(f"\n【步骤】共 {len(plan.steps)} 步")
    for step in plan.steps:
        print(f"\n  步骤 {step.step}: {step.action.value}")
        print(f"    描述: {step.description}")
        if step.target_ref:
            print(f"    目标: {step.target_ref} ({step.target_type.value if step.target_type else 'N/A'})")
        if step.params:
            print(f"    参数: {step.params}")
        if step.verify_ref:
            print(f"    验证: {step.verify_ref}")
        if step.fallback:
            print(f"    备选: {step.fallback}")

    if plan.success_criteria:
        print(f"\n【成功标准】\n  {plan.success_criteria}")

    if plan.potential_issues:
        print(f"\n【潜在问题】")
        for issue in plan.potential_issues:
            print(f"  - {issue}")


def test_locate(image_path: str, description: str):
    """测试元素定位（需要 API）- 优先使用参考图双图匹配"""
    print("\n" + "=" * 60)
    print("测试: Locator 元素定位")
    print("=" * 60)

    from ai.vision_agent import VisionAgent
    from ai.planner import AssetsManager

    img = Image.open(image_path)
    print(f"\n截图: {image_path}")
    print(f"尺寸: {img.size}")
    print(f"查找: {description}")

    agent = VisionAgent()
    assets = AssetsManager()
    print(f"LLM: {agent.config.provider}/{agent.config.model}")

    # 1. 尝试解析为参考图名称
    ref_name = assets.resolve_alias(description)
    ref_image = None

    if ref_name:
        ref_image = assets.get_image(ref_name)
        if ref_image:
            print(f"\n找到参考图: {ref_name} ({ref_image.size})")

    # 2. 如果有参考图，使用双图匹配
    if ref_image:
        print("使用模式: 双图匹配 (参考图 + 截图)")
        print("\n调用 API...")
        result = agent.find_element_by_image(ref_image, img)
    else:
        # 3. 否则使用文字描述
        print("使用模式: 文字描述定位")
        print(f"  (未找到 '{description}' 对应的参考图，使用描述匹配)")
        print("\n调用 API...")
        result = agent.find_element(img, description)

    if result:
        x, y = result
        print(f"\n✓ 找到元素")
        print(f"  中心坐标: ({x}, {y})")
        print(f"  相对位置: ({x/img.size[0]*100:.1f}%, {y/img.size[1]*100:.1f}%)")
    else:
        print("\n✗ 未找到元素")


def test_match(ref_path: str, screenshot_path: str):
    """测试双图匹配定位（需要 API）"""
    print("\n" + "=" * 60)
    print("测试: Locator 双图匹配定位")
    print("=" * 60)

    from ai.vision_agent import VisionAgent

    ref_img = Image.open(ref_path)
    screenshot = Image.open(screenshot_path)

    print(f"\n参考图: {ref_path} ({ref_img.size})")
    print(f"截图: {screenshot_path} ({screenshot.size})")

    agent = VisionAgent()
    print(f"LLM: {agent.config.provider}/{agent.config.model}")

    print("\n调用 API...")
    result = agent.find_element_by_image(ref_img, screenshot)

    if result:
        x, y = result
        print(f"\n✓ 找到匹配元素")
        print(f"  中心坐标: ({x}, {y})")
        print(f"  相对位置: ({x/screenshot.size[0]*100:.1f}%, {y/screenshot.size[1]*100:.1f}%)")
    else:
        print("\n✗ 未找到匹配元素")


def test_opencv(ref_path: str, screenshot_path: str):
    """测试 OpenCV 模板匹配（不需要 API）"""
    print("\n" + "=" * 60)
    print("测试: OpenCV 模板匹配（离线）")
    print("=" * 60)

    import cv2
    from core.opencv_locator import OpenCVLocator

    ref_img = Image.open(ref_path)
    screenshot = Image.open(screenshot_path)

    print(f"\n参考图: {ref_path} ({ref_img.size})")
    print(f"截图: {screenshot_path} ({screenshot.size})")

    # 转换为 OpenCV 格式
    import numpy as np
    ref_cv = cv2.cvtColor(np.array(ref_img), cv2.COLOR_RGB2BGR)
    screen_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    locator = OpenCVLocator()
    ref_name = Path(ref_path).name

    print("\n--- 1. 标准模板匹配 ---")
    result1 = locator._template_match(screen_cv, ref_cv, ref_name)
    print(f"  成功: {result1.success}")
    print(f"  置信度: {result1.confidence:.3f}")
    if result1.success:
        print(f"  中心坐标: ({result1.center_x}, {result1.center_y})")

    print("\n--- 2. 多尺度模板匹配 ---")
    result2 = locator._multi_scale_match(screen_cv, ref_cv, ref_name)
    print(f"  成功: {result2.success}")
    print(f"  置信度: {result2.confidence:.3f}")
    if result2.success:
        print(f"  中心坐标: ({result2.center_x}, {result2.center_y})")
        if result2.bbox:
            scale = result2.bbox[2] / ref_cv.shape[1]
            print(f"  匹配尺度: {scale:.2f}x")

    print("\n--- 3. 特征点匹配 (ORB) ---")
    result3 = locator._feature_match(screen_cv, ref_cv)
    print(f"  成功: {result3.success}")
    print(f"  置信度: {result3.confidence:.3f}")
    if result3.success:
        print(f"  中心坐标: ({result3.center_x}, {result3.center_y})")

    print("\n" + "-" * 40)
    print("总结:")
    print("-" * 40)
    methods = [
        ("标准模板", result1),
        ("多尺度", result2),
        ("特征点", result3)
    ]
    for name, r in methods:
        status = "✓" if r.success else "✗"
        print(f"  {name}: {status} (置信度: {r.confidence:.3f})")


def test_verify(image_path: str, expected_state: str):
    """测试验证器（需要 API）"""
    print("\n" + "=" * 60)
    print("测试: Verifier 状态验证")
    print("=" * 60)

    from ai.verifier import Verifier

    img = Image.open(image_path)
    print(f"\n截图: {image_path}")
    print(f"尺寸: {img.size}")
    print(f"期望状态: {expected_state}")

    verifier = Verifier()
    print(f"LLM: {verifier.vision.config.provider}/{verifier.vision.config.model}")

    print("\n调用 API...")
    result = verifier.verify_with_description(img, expected_state)

    print("\n" + "-" * 40)
    print("验证结果:")
    print("-" * 40)
    print(f"  验证通过: {'✓' if result.verified else '✗'}")
    print(f"  置信度: {result.confidence:.2f}")
    print(f"  当前状态: {result.current_state}")
    print(f"  匹配期望: {'是' if result.matches_expected else '否'}")
    print(f"  建议动作: {result.suggestion.value}")
    if result.suggestion_detail:
        print(f"  建议详情: {result.suggestion_detail}")

    if result.blocker:
        print(f"\n检测到阻挡物:")
        print(f"  类型: {result.blocker.type.value}")
        print(f"  描述: {result.blocker.description}")
        if result.blocker.dismiss_suggestion:
            ds = result.blocker.dismiss_suggestion
            print(f"  关闭方式: {ds.action} - {ds.description}")


def test_full_flow(image_path: str, task: str):
    """完整流程测试（规划 + 定位第一步）"""
    print("\n" + "=" * 60)
    print("测试: 完整流程（规划 → 定位）")
    print("=" * 60)

    from ai.planner import Planner
    from ai.vision_agent import VisionAgent

    img = Image.open(image_path)
    print(f"\n截图: {image_path}")
    print(f"任务: {task}")

    # 1. 规划
    print("\n[1/2] 生成任务规划...")
    planner = Planner()
    plan = planner.plan(task, img)

    print(f"  生成 {len(plan.steps)} 个步骤")

    if not plan.steps:
        print("  ✗ 规划失败，无步骤生成")
        return

    # 显示第一步
    step1 = plan.steps[0]
    print(f"\n  第1步: {step1.action.value} - {step1.description}")
    if step1.target_ref:
        print(f"  目标: {step1.target_ref}")

    # 2. 定位第一步的目标
    if step1.target_ref:
        print("\n[2/2] 定位第一步目标...")
        agent = VisionAgent()

        if step1.target_ref.startswith("dynamic:"):
            desc = step1.target_ref[8:]
            result = agent.find_element(img, desc)
        else:
            # 尝试从 assets 获取参考图
            from ai.planner import AssetsManager
            assets = AssetsManager()
            ref_img = assets.get_image(step1.target_ref)

            if ref_img:
                result = agent.find_element_by_image(ref_img, img)
            else:
                # 回退到描述定位
                result = agent.find_element(img, step1.description)

        if result:
            x, y = result
            print(f"  ✓ 定位成功: ({x}, {y})")
        else:
            print(f"  ✗ 定位失败")
    else:
        print("\n[2/2] 第一步不需要定位（如 press_key）")

    print("\n" + "=" * 60)
    print("完整流程测试完成")
    print("=" * 60)


def print_usage():
    """打印使用说明"""
    print(__doc__)
    print("\n示例任务:")
    print("  - 打开微信")
    print("  - 给张三发微信消息说你好")
    print("  - 打开设置，进入WiFi设置")
    print("  - 返回桌面首页")
    print("  - 打开淘宝搜索蓝牙耳机")


def main():
    args = sys.argv[1:]

    if not args:
        # 无参数：运行基础测试
        print("\n运行基础测试（不需要 API）...\n")
        test_assets_manager()
        print("\n" + "=" * 60)
        print("基础测试完成！")
        print("=" * 60)
        print("\n如需测试真实 API，请使用以下命令：")
        print("  python test_planner.py plan <截图> <任务>")
        print("  python test_planner.py locate <截图> <元素描述>")
        print("  python test_planner.py match <参考图> <截图>      # AI匹配")
        print("  python test_planner.py opencv <参考图> <截图>     # OpenCV匹配(离线)")
        print("  python test_planner.py verify <截图> <期望状态>")
        print("  python test_planner.py flow <截图> <任务>")
        return

    cmd = args[0]

    if cmd == "plan" and len(args) >= 3:
        test_planner(args[1], args[2])

    elif cmd == "locate" and len(args) >= 3:
        test_locate(args[1], args[2])

    elif cmd == "match" and len(args) >= 3:
        test_match(args[1], args[2])

    elif cmd == "opencv" and len(args) >= 3:
        test_opencv(args[1], args[2])

    elif cmd == "verify" and len(args) >= 3:
        test_verify(args[1], args[2])

    elif cmd == "flow" and len(args) >= 3:
        test_full_flow(args[1], args[2])

    else:
        print_usage()


if __name__ == "__main__":
    main()
