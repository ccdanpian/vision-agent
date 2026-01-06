#!/usr/bin/env python3
"""
测试交互式 invalid 输入处理

模拟场景：
1. 用户输入无效内容（如 "aaa"）
2. 系统识别为 invalid
3. 提示用户重新输入
4. 用户输入有效任务（如 "给张三发消息说你好"）
5. 系统正常执行
"""
import sys
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from ai.task_classifier import get_task_classifier


def test_invalid_detection():
    """测试 invalid 输入识别"""
    print("=" * 60)
    print("测试 invalid 输入识别")
    print("=" * 60)

    classifier = get_task_classifier()
    classifier.set_logger(print)

    # 测试用例
    test_cases = [
        ("aaa", True),           # 无效输入
        ("", True),              # 空输入
        ("   ", True),           # 空白输入
        ("!!!", True),           # 无意义字符
        ("s", True),             # 误触
        ("给张三发消息说你好", False),  # 有效输入
        ("发朋友圈今天天气真好", False),  # 有效输入
        ("ss:消息:张三:你好", False),     # SS 模式，有效输入
    ]

    print("\n【测试用例】")
    for task, should_be_invalid in test_cases:
        task_type, parsed_data = classifier.classify_and_parse(task)

        is_invalid = parsed_data and parsed_data.get("type") == "invalid"

        status = "✓" if is_invalid == should_be_invalid else "✗"
        expected = "invalid" if should_be_invalid else "valid"
        actual = "invalid" if is_invalid else "valid"

        print(f"\n{status} 输入: '{task}'")
        print(f"  预期: {expected}, 实际: {actual}")
        if parsed_data:
            print(f"  解析: {parsed_data}")


def test_interactive_flow_simulation():
    """模拟交互式流程"""
    print("\n" + "=" * 60)
    print("模拟交互式流程")
    print("=" * 60)

    classifier = get_task_classifier()

    # 模拟用户输入序列
    user_inputs = ["aaa", "", "!!!", "给张三发消息说你好"]

    print("\n模拟场景：用户输入 3 次无效内容，第 4 次输入有效任务\n")

    for i, task in enumerate(user_inputs, 1):
        print(f"【第 {i} 次输入】: '{task}'")

        task_type, parsed_data = classifier.classify_and_parse(task)

        if parsed_data and parsed_data.get("type") == "invalid":
            print("  → 系统识别: invalid")
            print("  → 提示用户: 无效的输入指令。请输入有效的任务描述")
            print("  → 等待重新输入...")
        else:
            print("  → 系统识别: valid")
            print(f"  → 解析数据: {parsed_data}")
            print("  → 开始执行任务...")
            break

        print()


def print_usage_guide():
    """打印使用指南"""
    print("\n" + "=" * 60)
    print("交互式模式使用指南")
    print("=" * 60)

    print("""
【使用方法】

1. 运行命令：
   python run.py -t "aaa"

2. 系统识别为无效输入：
   状态: failed
   错误: 无效的输入指令。请输入有效的任务描述，例如：
   - 给张三发消息说你好
   - 发朋友圈今天天气真好
   - SS快速模式：ss:消息:张三:你好

3. 系统提示重新输入：
   请重新输入任务（输入 'q' 退出）:

4. 用户输入有效任务：
   给张三发消息说你好

5. 系统正常执行任务

【退出方式】
- 输入 'q' 退出
- 按 Ctrl+C 取消
- 达到最大重试次数（5次）自动退出

【最大重试次数】
防止无限循环，最多允许重新输入 5 次

【示例对话】
$ python run.py -t "aaa"

设备: emulator-5554
任务: aaa
----------------------------------------
已连接，屏幕尺寸: (1080, 2340)

开始执行任务...
[TaskClassifier] LLM判断：无效输入
[WechatHandler] 检测到无效输入: aaa

========================================
执行结果
========================================
状态: failed
耗时: 0.5s

错误: 无效的输入指令。请输入有效的任务描述，例如：
- 给张三发消息说你好
- 发朋友圈今天天气真好
- SS快速模式：ss:消息:张三:你好

----------------------------------------
请重新输入任务（输入 'q' 退出）: 给张三发消息说你好

开始执行任务...
[TaskClassifier] 检测到非 SS 模式
[TaskClassifier] LLM解析: send_msg
[WechatHandler] 匹配到工作流: send_message
...（正常执行）
""")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("交互式 Invalid 输入处理测试")
    print("=" * 60)

    # 测试 1: invalid 识别
    test_invalid_detection()

    # 测试 2: 模拟交互流程
    test_interactive_flow_simulation()

    # 使用指南
    print_usage_guide()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
