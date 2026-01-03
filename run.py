#!/usr/bin/env python3
"""
run.py - VisionAgent 命令行控制工具

使用方法：
---------
1. 查看手机信息（默认任务）：
   python run.py
   python run.py -d emulator-5554
   python run.py --device 192.168.1.100:5555

2. 执行指定任务：
   python run.py -t "打开微信"
   python run.py -d emulator-5554 -t "打开设置"
   python run.py -t "给10086打电话"

3. 列出已连接设备：
   python run.py --list

4. 截图保存：
   python run.py --screenshot output.png

5. 查看可用模块：
   python run.py --modules

环境配置：
---------
在 .env 文件中配置默认设备：
  DEFAULT_DEVICE=emulator-5554
  # 或
  DEFAULT_DEVICE=192.168.1.100:5555
"""
import sys
import argparse
import subprocess
from pathlib import Path

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import config


def get_default_device() -> str:
    """获取默认设备地址"""
    # 优先从环境变量/config 获取
    default = getattr(config, 'DEFAULT_DEVICE', None)
    if default:
        return default

    # 否则尝试获取第一个已连接设备
    result = subprocess.run(
        [config.ADB_PATH, "devices"],
        capture_output=True,
        text=True,
        timeout=10
    )

    lines = result.stdout.strip().split('\n')[1:]  # 跳过 header
    for line in lines:
        if '\tdevice' in line:
            return line.split('\t')[0]

    return "emulator-5554"  # 默认模拟器


def list_devices():
    """列出所有已连接的设备"""
    result = subprocess.run(
        [config.ADB_PATH, "devices", "-l"],
        capture_output=True,
        text=True,
        timeout=10
    )
    print(result.stdout)


def list_modules():
    """列出所有可用的应用模块"""
    from apps import ModuleRegistry

    ModuleRegistry.discover()
    modules = ModuleRegistry.list_modules()

    print("\n" + "=" * 50)
    print("           可用模块")
    print("=" * 50)

    if not modules:
        print("\n  没有发现任何模块")
        print("  请检查 apps/ 目录")
    else:
        for mod in modules:
            print(f"\n【{mod['name']}】")
            print(f"  ID: {mod['id']}")
            if mod.get('package'):
                print(f"  包名: {mod['package']}")
            if mod.get('keywords'):
                keywords = ', '.join(mod['keywords'][:5])
                print(f"  关键词: {keywords}")

    print("\n" + "=" * 50)
    print(f"共 {len(modules)} 个模块")
    print("=" * 50 + "\n")


def get_device_info(device: str) -> dict:
    """获取设备详细信息"""

    def run_adb(*args) -> str:
        result = subprocess.run(
            [config.ADB_PATH, "-s", device] + list(args),
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip()

    def get_prop(prop: str) -> str:
        return run_adb("shell", "getprop", prop)

    info = {}

    # 基本信息
    info['device_address'] = device
    info['brand'] = get_prop("ro.product.brand")
    info['model'] = get_prop("ro.product.model")
    info['device_name'] = get_prop("ro.product.device")
    info['android_version'] = get_prop("ro.build.version.release")
    info['sdk_version'] = get_prop("ro.build.version.sdk")

    # 屏幕信息
    wm_size = run_adb("shell", "wm", "size")
    if "Physical size:" in wm_size:
        info['screen_size'] = wm_size.split(":")[-1].strip()
    else:
        info['screen_size'] = wm_size.replace("Physical size:", "").strip()

    wm_density = run_adb("shell", "wm", "density")
    if "Physical density:" in wm_density:
        info['screen_density'] = wm_density.split(":")[-1].strip()
    else:
        info['screen_density'] = wm_density.replace("Physical density:", "").strip()

    # 电池信息
    battery = run_adb("shell", "dumpsys", "battery")
    for line in battery.split('\n'):
        line = line.strip()
        if line.startswith("level:"):
            info['battery_level'] = line.split(":")[-1].strip() + "%"
        elif line.startswith("status:"):
            status_code = line.split(":")[-1].strip()
            status_map = {"1": "未知", "2": "充电中", "3": "放电中", "4": "未充电", "5": "已充满"}
            info['battery_status'] = status_map.get(status_code, status_code)

    # 当前应用
    current_focus = run_adb("shell", "dumpsys", "window", "displays")
    for line in current_focus.split('\n'):
        if 'mCurrentFocus' in line or 'mFocusedApp' in line:
            # 提取包名
            if '/' in line:
                parts = line.split()
                for part in parts:
                    if '/' in part:
                        info['current_app'] = part.rstrip('}').strip()
                        break
            break

    # 网络状态
    wifi = run_adb("shell", "dumpsys", "wifi")
    if "Wi-Fi is enabled" in wifi:
        info['wifi_enabled'] = "是"
        # 获取 SSID
        for line in wifi.split('\n'):
            if 'mWifiInfo' in line and 'SSID' in line:
                import re
                ssid_match = re.search(r'SSID: ([^,]+)', line)
                if ssid_match:
                    info['wifi_ssid'] = ssid_match.group(1)
                break
    else:
        info['wifi_enabled'] = "否"

    return info


def print_device_info(info: dict):
    """格式化打印设备信息"""
    print("\n" + "=" * 50)
    print("           设备信息")
    print("=" * 50)

    sections = [
        ("基本信息", ['device_address', 'brand', 'model', 'device_name']),
        ("系统信息", ['android_version', 'sdk_version']),
        ("屏幕信息", ['screen_size', 'screen_density']),
        ("电池信息", ['battery_level', 'battery_status']),
        ("网络信息", ['wifi_enabled', 'wifi_ssid']),
        ("当前状态", ['current_app']),
    ]

    labels = {
        'device_address': '设备地址',
        'brand': '品牌',
        'model': '型号',
        'device_name': '设备名',
        'android_version': 'Android 版本',
        'sdk_version': 'SDK 版本',
        'screen_size': '屏幕尺寸',
        'screen_density': '屏幕密度',
        'battery_level': '电量',
        'battery_status': '充电状态',
        'wifi_enabled': 'WiFi',
        'wifi_ssid': 'WiFi 名称',
        'current_app': '当前应用',
    }

    for section_name, keys in sections:
        has_content = any(key in info for key in keys)
        if has_content:
            print(f"\n【{section_name}】")
            for key in keys:
                if key in info and info[key]:
                    label = labels.get(key, key)
                    print(f"  {label}: {info[key]}")

    print("\n" + "=" * 50)


def take_screenshot(device: str, output_path: str):
    """截图并保存"""
    remote_path = "/sdcard/screenshot_tmp.png"

    # 截图
    subprocess.run(
        [config.ADB_PATH, "-s", device, "shell", "screencap", "-p", remote_path],
        capture_output=True,
        timeout=30
    )

    # 拉取
    result = subprocess.run(
        [config.ADB_PATH, "-s", device, "pull", remote_path, output_path],
        capture_output=True,
        text=True,
        timeout=30
    )

    if result.returncode == 0:
        print(f"截图已保存到: {output_path}")
    else:
        print(f"截图失败: {result.stderr}")


def run_task(device: str, task: str):
    """执行 AI 任务"""
    from core import TaskRunner, ADBController

    print(f"\n设备: {device}")
    print(f"任务: {task}")
    print("-" * 40)

    # 连接设备
    adb = ADBController(device)

    # 检查连接
    if not adb.is_connected():
        print("设备未连接，尝试连接...")
        if not adb.connect():
            print("连接失败！请检查设备地址和网络。")
            return

    print(f"已连接，屏幕尺寸: {adb.get_screen_size()}")

    # 创建任务执行器
    runner = TaskRunner(adb)

    # 执行任务
    print("\n开始执行任务...")
    result = runner.run(task)

    # 显示结果
    print("\n" + "=" * 40)
    print("执行结果")
    print("=" * 40)
    print(f"状态: {result.status.value}")
    print(f"耗时: {result.total_time:.1f}s")

    if result.step_results:
        print(f"\n执行步骤 ({len(result.step_results)} 步):")
        for i, step_result in enumerate(result.step_results, 1):
            status_icon = "✓" if step_result.status.value == "success" else "✗"
            print(f"  {i}. {status_icon} {step_result.step.description}")

    if result.error_message:
        print(f"\n错误: {result.error_message}")


def main():
    parser = argparse.ArgumentParser(
        description="VisionAgent 命令行控制工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run.py                           # 查看默认设备信息
  python run.py -d emulator-5554          # 查看指定设备信息
  python run.py -t "打开微信"              # 执行任务
  python run.py -t "给10086打电话"         # 直接拨打电话
  python run.py --list                    # 列出所有设备
  python run.py --modules                 # 列出可用模块
  python run.py --screenshot screen.png   # 截图保存
        """
    )

    parser.add_argument(
        "-d", "--device",
        help="设备地址 (如 emulator-5554 或 192.168.1.100:5555)"
    )

    parser.add_argument(
        "-t", "--task",
        help="要执行的任务 (如 '打开微信')"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有已连接的设备"
    )

    parser.add_argument(
        "--modules",
        action="store_true",
        help="列出所有可用的应用模块"
    )

    parser.add_argument(
        "--screenshot",
        metavar="FILE",
        help="截图并保存到指定文件"
    )

    args = parser.parse_args()

    # 列出设备
    if args.list:
        list_devices()
        return

    # 列出模块
    if args.modules:
        list_modules()
        return

    # 获取设备地址
    device = args.device or get_default_device()

    # 截图
    if args.screenshot:
        take_screenshot(device, args.screenshot)
        return

    # 执行任务
    if args.task:
        run_task(device, args.task)
        return

    # 默认：显示设备信息
    try:
        info = get_device_info(device)
        print_device_info(info)
    except Exception as e:
        print(f"获取设备信息失败: {e}")
        print("\n提示：")
        print("  1. 确保设备已连接: adb devices")
        print("  2. 指定正确的设备: python run.py -d <设备地址>")
        print("  3. 列出所有设备: python run.py --list")


if __name__ == "__main__":
    main()
