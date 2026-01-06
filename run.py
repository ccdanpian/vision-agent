#!/usr/bin/env python3
"""
run.py - VisionAgent 命令行控制工具

使用方法：
---------
1. 查看手机信息（默认任务）：
   python run.py
   python run.py -d emulator-5554
   python run.py --device 192.168.1.100:5555

2. 执行单个任务：
   python run.py -t "打开微信"
   python run.py -d emulator-5554 -t "打开设置"
   python run.py -t "给10086打电话"
   python run.py -t "ss:张三:你好"  # SS 快速模式（发消息）

3. 交互式模式（推荐，支持连续执行多个任务）：
   python run.py -i
   python run.py --interactive
   python run.py -d emulator-5554 -i

   交互式模式特性：
   - 可连续输入多个任务
   - 无效输入自动提示重新输入
   - 输入 'q' 或 'quit' 退出
   - 支持 Ctrl+C 退出

4. 列出已连接设备：
   python run.py --list

5. 截图保存：
   python run.py --screenshot output.png

6. 查看可用模块：
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


def run_interactive_mode(device: str):
    """交互式任务模式（可连续输入多个任务）"""
    from core import TaskRunner, TaskStatus
    import config

    print("\n" + "=" * 50)
    print("           交互式任务模式")
    print("=" * 50)

    # 检查是否为调试模式
    if config.DEBUG_MODE:
        print(f"\n⚠️  调试模式已启用（无需真实设备）")
        print(f"设备: {config.DEBUG_DEVICE_NAME} (模拟)")
        from core.mock_adb_controller import MockADBController
        adb = MockADBController(device)
    else:
        print(f"\n设备: {device}")
        from core import ADBController
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

    # 外层循环：模式选择
    while True:
        # 让用户选择分类模式
        print("\n" + "=" * 50)
        print("           选择任务分类模式")
        print("=" * 50)
        print("\n请选择任务输入模式：")
        print("  1. 快速模式（固定格式，零成本，极速响应）")
        print("  2. 智能模式（自然语言，AI理解）")
        print()

        mode_choice = None
        while mode_choice not in ['1', '2']:
            try:
                mode_choice = input("请输入选项（1 或 2）: ").strip()
                if mode_choice not in ['1', '2']:
                    print("无效选项，请输入 1 或 2")
            except (KeyboardInterrupt, EOFError):
                print("\n\n退出交互式模式")
                return

        # 根据选择显示提示信息
        print("\n" + "=" * 50)
        if mode_choice == '1':
            print("           快速模式（SS格式）")
            print("=" * 50)
            print("\n格式说明：")
            print("  发消息（默认）：联系人:消息内容")
            print("  发朋友圈：朋友圈:朋友圈内容")
            print()
            print("示例：")
            print("  张三:你好")
            print("  李四:早上好，今天开会")
            print("  朋友圈:今天天气真好")
            print()
            print("提示：")
            print("  - 冒号支持中英文（: 或 ：）")
            print("  - 默认发消息，只需输入联系人和内容")
            print("  - 输入 'q' 或 'quit' 退出")
            print("  - 按 Ctrl+C 也可以退出")
        else:
            print("           智能模式（自然语言）")
            print("=" * 50)
            print("\n说明：")
            print("  直接用自然语言描述任务，AI 会自动理解")
            print()
            print("示例：")
            print("  给张三发消息说你好")
            print("  给李四发消息说早上好，今天开会")
            print("  发朋友圈今天天气真好")
            print()
            print("提示：")
            print("  - 无效输入会自动提示重新输入")
            print("  - 输入 'q' 或 'quit' 退出")
            print("  - 按 Ctrl+C 也可以退出")
        print()

        # 内层循环：连续执行任务
        restart_mode_selection = False
        while True:
            try:
                # 获取用户输入
                print("-" * 50)
                if mode_choice == '1':
                    task_input = input("请输入任务（快速格式）: ").strip()
                else:
                    task_input = input("请输入任务（自然语言）: ").strip()

                # 检查退出指令
                if not task_input:
                    print("输入为空，请重新输入")
                    continue

                if task_input.lower() in ['q', 'quit', 'exit']:
                    print("退出交互式模式")
                    return

                # 处理任务输入
                if mode_choice == '1':
                    # 快速模式：自动添加 ss: 前缀（如果用户没有输入）
                    if not task_input.lower().startswith('ss:'):
                        task = f"ss:{task_input}"
                    else:
                        task = task_input
                else:
                    # 智能模式：直接使用用户输入
                    task = task_input

                # 执行任务（带 invalid 重试逻辑）
                # 返回 True 表示继续当前模式，False 表示需要重新选择模式
                should_restart = _execute_task_with_retry(runner, task, mode_choice)
                if should_restart:
                    restart_mode_selection = True
                    break

            except (KeyboardInterrupt, EOFError):
                print("\n\n退出交互式模式")
                return

        # 检查是否需要重新选择模式
        if not restart_mode_selection:
            break


def _execute_task_with_retry(runner, task: str, mode_choice: str = '2', max_retries: int = 5) -> bool:
    """执行任务并支持 invalid 输入后重新输入

    Args:
        runner: TaskRunner 实例
        task: 任务字符串（已经处理过前缀）
        mode_choice: '1' 表示快速模式，'2' 表示智能模式
        max_retries: 最大重试次数

    Returns:
        bool: True 表示需要重新选择模式，False 表示继续当前模式
    """
    from core import TaskStatus

    current_task = task
    retry_count = 0

    while retry_count <= max_retries:
        # 执行任务
        print(f"\n开始执行任务: {current_task}")
        result = runner.run(current_task)

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

        # 检查是否为 LLM 分类失败 - 需要重新选择模式
        if result.status == TaskStatus.FAILED and "LLM分类失败" in result.error_message:
            print("\n" + "=" * 50)
            print("将返回到模式选择界面")
            print("=" * 50)
            return True  # 返回 True 表示需要重新选择模式

        # 检查是否为 invalid 输入（只在智能模式下会出现）
        if result.status == TaskStatus.FAILED and "无效的输入指令" in result.error_message:
            print("\n" + "-" * 40)
            try:
                # 提示用户重新输入
                if mode_choice == '1':
                    new_task_input = input("请重新输入任务（快速格式，输入 'q' 取消）: ").strip()
                else:
                    new_task_input = input("请重新输入任务（自然语言，输入 'q' 取消）: ").strip()

                if not new_task_input:
                    print("输入为空，请重新输入")
                    retry_count += 1
                    continue

                if new_task_input.lower() in ['q', 'quit', 'cancel']:
                    print("取消当前任务")
                    break

                # 处理新任务输入
                if mode_choice == '1':
                    # 快速模式：自动添加 ss: 前缀
                    if not new_task_input.lower().startswith('ss:'):
                        current_task = f"ss:{new_task_input}"
                    else:
                        current_task = new_task_input
                else:
                    # 智能模式：直接使用
                    current_task = new_task_input

                retry_count += 1
                continue

            except (KeyboardInterrupt, EOFError):
                print("\n\n取消当前任务")
                break
        else:
            # 非 invalid 错误或执行成功，退出循环
            break

    if retry_count > max_retries:
        print(f"\n已达到最大重试次数 ({max_retries})，取消当前任务")

    # 返回 False 表示继续当前模式，不需要重新选择
    return False


def run_task(device: str, task: str):
    """执行 AI 任务（支持 invalid 输入后重新输入）"""
    from core import TaskRunner, TaskStatus
    import config

    # 检查是否为调试模式
    if config.DEBUG_MODE:
        print(f"\n⚠️  调试模式已启用（无需真实设备）")
        print(f"设备: {config.DEBUG_DEVICE_NAME} (模拟)")
        print(f"任务: {task}")
        print("-" * 40)
        from core.mock_adb_controller import MockADBController
        adb = MockADBController(device)
    else:
        print(f"\n设备: {device}")
        print(f"任务: {task}")
        print("-" * 40)
        from core import ADBController
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

    # 判断模式：如果任务以 ss: 开头，使用快速模式，否则使用智能模式
    if task.lower().startswith('ss:'):
        mode_choice = '1'
    else:
        mode_choice = '2'

    # 执行任务（支持 invalid 输入后重新输入）
    _execute_task_with_retry(runner, task, mode_choice)


def main():
    parser = argparse.ArgumentParser(
        description="VisionAgent 命令行控制工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run.py                           # 查看默认设备信息
  python run.py -d emulator-5554          # 查看指定设备信息
  python run.py -t "打开微信"              # 执行单个任务
  python run.py -t "给10086打电话"         # 直接拨打电话
  python run.py -i                        # 进入交互式模式（连续执行多个任务）
  python run.py -d 192.168.1.100 -i       # 指定设备的交互式模式
  python run.py --list                    # 列出所有设备
  python run.py --modules                 # 列出可用模块
  python run.py --screenshot screen.png   # 截图保存

交互式模式特性:
  - 无效输入自动提示重新输入
  - 可连续执行多个任务
  - 输入 'q' 或 'quit' 退出
  - 支持 SS 快速模式（如：ss:消息:张三:你好）
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

    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="进入交互式任务模式（可连续输入多个任务）"
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

    # 交互式模式
    if args.interactive:
        run_interactive_mode(device)
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
