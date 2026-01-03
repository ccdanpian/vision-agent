#!/usr/bin/env python3
"""
test_input.py
测试中文文本输入功能

用于诊断和测试 ADBKeyboard 是否正常工作
"""
import sys
from core.adb_controller import ADBController
import config


def main():
    device = config.DEVICE_ADDRESS
    print(f"连接设备: {device}")

    adb = ADBController(device)

    if not adb.connect():
        print("❌ 连接设备失败")
        return 1

    print("✓ 设备已连接")

    # 1. 检查可用的输入法
    print("\n=== 检查输入法 ===")
    ime_list = adb.list_ime()
    print(f"可用输入法 ({len(ime_list)} 个):")
    for ime in ime_list:
        print(f"  - {ime}")

    # 2. 检查当前输入法
    current_ime = adb.get_current_ime()
    print(f"\n当前输入法: {current_ime}")

    # 3. 检查 ADBKeyboard
    has_adbkeyboard = adb.is_adbkeyboard_installed()
    if has_adbkeyboard:
        print("✓ ADBKeyboard 已安装")
    else:
        print("❌ ADBKeyboard 未安装")
        print("\n请下载并安装 ADBKeyboard:")
        print("  https://github.com/nickchan0/ADBKeyBoard/releases")
        print("\n安装方法:")
        print("  adb install ADBKeyboard.apk")
        return 1

    # 4. 尝试设置 ADBKeyboard
    print("\n=== 设置 ADBKeyboard ===")
    if adb.setup_adbkeyboard():
        print("✓ 已设置 ADBKeyboard 为默认输入法")
        new_ime = adb.get_current_ime()
        print(f"  当前: {new_ime}")
    else:
        print("❌ 设置失败")

    # 5. 测试文本输入
    if len(sys.argv) > 1:
        test_text = sys.argv[1]
    else:
        test_text = "测试中文输入"

    print(f"\n=== 测试输入文本 ===")
    print(f"测试文本: {test_text}")
    print("请确保设备上有一个激活的输入框...")

    input("按 Enter 开始测试...")

    if adb.input_text_chinese(test_text):
        print("✓ 文本输入成功")
    else:
        print("❌ 文本输入失败")
        print("\n可能的原因:")
        print("  1. 设备上没有激活的输入框")
        print("  2. ADBKeyboard 未启用")
        print("  3. ADBKeyboard 版本不兼容")

    return 0


if __name__ == "__main__":
    sys.exit(main())
