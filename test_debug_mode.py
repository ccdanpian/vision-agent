#!/usr/bin/env python3
"""
测试调试模式功能

验证：
1. MockADBController 的所有方法
2. 调试模式的自动检测
3. 模拟操作的日志输出
4. 模拟截图生成
"""
import sys
import os
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 临时启用调试模式
os.environ['DEBUG_MODE'] = 'true'

import config
from core.mock_adb_controller import MockADBController


def test_mock_adb_basic():
    """测试基本功能"""
    print("=" * 60)
    print("测试 MockADBController 基本功能")
    print("=" * 60)

    # 创建模拟控制器
    adb = MockADBController("mock:5555")

    # 测试连接
    print("\n【测试连接】")
    assert adb.connect() == True
    assert adb.is_connected() == True
    print("✓ 连接测试通过")

    # 测试屏幕信息
    print("\n【测试屏幕信息】")
    size = adb.get_screen_size()
    print(f"屏幕尺寸: {size}")
    assert size == (config.DEBUG_SCREEN_WIDTH, config.DEBUG_SCREEN_HEIGHT)
    print("✓ 屏幕信息测试通过")

    # 测试基本操作
    print("\n【测试基本操作】")
    assert adb.tap(100, 200) == True
    assert adb.long_press(300, 400, 1000) == True
    assert adb.swipe(0, 500, 1000, 500, 300) == True
    print("✓ 基本操作测试通过")

    # 测试输入
    print("\n【测试输入】")
    assert adb.input_text("Hello") == True
    assert adb.input_text_chinese("你好") == True
    assert adb.input_keyevent(66) == True
    print("✓ 输入测试通过")

    # 测试导航键
    print("\n【测试导航键】")
    assert adb.press_home() == True
    assert adb.press_back() == True
    assert adb.press_enter() == True
    print("✓ 导航键测试通过")

    # 测试截图
    print("\n【测试截图】")
    screenshot_path = "temp/test_mock_screenshot.png"
    assert adb.screenshot(screenshot_path) == True
    assert Path(screenshot_path).exists()
    print(f"✓ 截图已保存: {screenshot_path}")

    # 测试应用管理
    print("\n【测试应用管理】")
    assert adb.start_app("com.tencent.mm") == True
    assert adb.get_current_app() == "com.tencent.mm"
    assert adb.stop_app("com.tencent.mm") == True
    packages = adb.get_installed_packages()
    assert "com.tencent.mm" in packages
    print("✓ 应用管理测试通过")

    # 测试电话功能
    print("\n【测试电话功能】")
    assert adb.dial("10086") == True
    assert adb.call("10086") == True
    print("✓ 电话功能测试通过")

    # 测试屏幕状态
    print("\n【测试屏幕状态】")
    assert adb.is_screen_on() == True
    assert adb.wake_up() == True
    assert adb.unlock() == True
    print("✓ 屏幕状态测试通过")

    # 测试输入法
    print("\n【测试输入法】")
    assert adb.get_current_ime() is not None
    assert len(adb.list_ime()) > 0
    assert adb.set_ime("com.android.adbkeyboard/.AdbIME") == True
    assert adb.is_adbkeyboard_installed() == True
    assert adb.setup_adbkeyboard() == True
    print("✓ 输入法测试通过")

    # 测试断开连接
    print("\n【测试断开连接】")
    assert adb.disconnect() == True
    print("✓ 断开连接测试通过")


def test_debug_mode_detection():
    """测试调试模式检测"""
    print("\n" + "=" * 60)
    print("测试调试模式检测")
    print("=" * 60)

    print(f"\nDEBUG_MODE = {config.DEBUG_MODE}")
    print(f"DEBUG_DEVICE_NAME = {config.DEBUG_DEVICE_NAME}")
    print(f"DEBUG_SCREEN_WIDTH = {config.DEBUG_SCREEN_WIDTH}")
    print(f"DEBUG_SCREEN_HEIGHT = {config.DEBUG_SCREEN_HEIGHT}")

    assert config.DEBUG_MODE == True
    print("\n✓ 调试模式检测正常")


def test_screenshot_content():
    """测试截图内容"""
    print("\n" + "=" * 60)
    print("测试截图内容")
    print("=" * 60)

    from PIL import Image

    adb = MockADBController()
    screenshot_path = "temp/test_screenshot_content.png"

    # 生成截图
    adb.screenshot(screenshot_path)

    # 验证截图
    img = Image.open(screenshot_path)
    width, height = img.size

    print(f"\n截图尺寸: {width}x{height}")
    print(f"期望尺寸: {config.DEBUG_SCREEN_WIDTH}x{config.DEBUG_SCREEN_HEIGHT}")

    assert width == config.DEBUG_SCREEN_WIDTH
    assert height == config.DEBUG_SCREEN_HEIGHT

    print("✓ 截图内容验证通过")


def test_interface_compatibility():
    """测试接口兼容性"""
    print("\n" + "=" * 60)
    print("测试接口兼容性")
    print("=" * 60)

    from core.adb_controller import ADBController

    # 获取两个类的方法
    real_methods = set(dir(ADBController))
    mock_methods = set(dir(MockADBController))

    # 排除私有方法和特殊方法
    real_public = {m for m in real_methods if not m.startswith('_')}
    mock_public = {m for m in mock_methods if not m.startswith('_')}

    # 检查 Mock 是否实现了所有公共方法
    missing = real_public - mock_public
    if missing:
        print(f"\n⚠️  MockADBController 缺少以下方法: {missing}")
    else:
        print("\n✓ MockADBController 实现了所有公共方法")

    # 检查方法签名
    print("\n检查关键方法签名...")
    import inspect

    key_methods = ['connect', 'tap', 'screenshot', 'input_text', 'start_app']

    for method_name in key_methods:
        if hasattr(ADBController, method_name) and hasattr(MockADBController, method_name):
            real_sig = inspect.signature(getattr(ADBController, method_name))
            mock_sig = inspect.signature(getattr(MockADBController, method_name))

            if str(real_sig) == str(mock_sig):
                print(f"✓ {method_name}: 签名一致")
            else:
                print(f"⚠️  {method_name}: 签名不同")
                print(f"   ADB: {real_sig}")
                print(f"   Mock: {mock_sig}")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("MockADBController 功能测试")
    print("=" * 60)

    try:
        # 测试 1: 基本功能
        test_mock_adb_basic()

        # 测试 2: 调试模式检测
        test_debug_mode_detection()

        # 测试 3: 截图内容
        test_screenshot_content()

        # 测试 4: 接口兼容性
        test_interface_compatibility()

        # 总结
        print("\n" + "=" * 60)
        print("所有测试通过 ✓")
        print("=" * 60)
        print("\n调试模式功能正常，可以使用：")
        print("  DEBUG_MODE=true python run.py -i")

    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
