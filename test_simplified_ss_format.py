#!/usr/bin/env python3
"""
测试简化后的 SS 快速模式格式

验证：
1. 默认发消息：ss:联系人:内容
2. 发朋友圈：ss:朋友圈:内容
"""
import sys
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from ai.task_classifier import TaskClassifier


def test_simplified_message_format():
    """测试简化的发消息格式"""
    print("=" * 60)
    print("测试简化的发消息格式")
    print("=" * 60)

    classifier = TaskClassifier()

    test_cases = [
        {
            "input": "ss:张三:你好",
            "expected_type": "send_msg",
            "expected_recipient": "张三",
            "expected_content": "你好"
        },
        {
            "input": "ss:李四:早上好，今天开会",
            "expected_type": "send_msg",
            "expected_recipient": "李四",
            "expected_content": "早上好，今天开会"
        },
        {
            "input": "ss：王五：时间是明天3:30",
            "expected_type": "send_msg",
            "expected_recipient": "王五",
            "expected_content": "时间是明天3:30"
        },
        {
            "input": "SS:客户A:会议通知",
            "expected_type": "send_msg",
            "expected_recipient": "客户A",
            "expected_content": "会议通知"
        }
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n【测试用例 {i}】")
        print(f"输入: {case['input']}")

        task_type, parsed_data = classifier.classify_and_parse(case['input'])

        if not parsed_data:
            print(f"✗ 解析失败")
            continue

        success = (
            parsed_data.get("type") == case["expected_type"] and
            parsed_data.get("recipient") == case["expected_recipient"] and
            parsed_data.get("content") == case["expected_content"]
        )

        if success:
            print(f"✓ 测试通过")
            print(f"  type: {parsed_data['type']}")
            print(f"  recipient: {parsed_data['recipient']}")
            print(f"  content: {parsed_data['content']}")
        else:
            print(f"✗ 测试失败")
            print(f"  期望: type={case['expected_type']}, recipient={case['expected_recipient']}, content={case['expected_content']}")
            print(f"  实际: type={parsed_data.get('type')}, recipient={parsed_data.get('recipient')}, content={parsed_data.get('content')}")


def test_moments_format():
    """测试朋友圈格式（保持不变）"""
    print("\n" + "=" * 60)
    print("测试朋友圈格式")
    print("=" * 60)

    classifier = TaskClassifier()

    test_cases = [
        {
            "input": "ss:朋友圈:今天天气真好",
            "expected_type": "post_moment_only_text",
            "expected_content": "今天天气真好"
        },
        {
            "input": "ss:pyq:分享一个好消息",
            "expected_type": "post_moment_only_text",
            "expected_content": "分享一个好消息"
        },
        {
            "input": "ss：朋友圈：今日名言：人生苦短",
            "expected_type": "post_moment_only_text",
            "expected_content": "今日名言：人生苦短"
        }
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n【测试用例 {i}】")
        print(f"输入: {case['input']}")

        task_type, parsed_data = classifier.classify_and_parse(case['input'])

        if not parsed_data:
            print(f"✗ 解析失败")
            continue

        success = (
            parsed_data.get("type") == case["expected_type"] and
            parsed_data.get("content") == case["expected_content"]
        )

        if success:
            print(f"✓ 测试通过")
            print(f"  type: {parsed_data['type']}")
            print(f"  content: {parsed_data['content']}")
        else:
            print(f"✗ 测试失败")
            print(f"  期望: type={case['expected_type']}, content={case['expected_content']}")
            print(f"  实际: type={parsed_data.get('type')}, content={parsed_data.get('content')}")


def test_edge_cases():
    """测试边界情况"""
    print("\n" + "=" * 60)
    print("测试边界情况")
    print("=" * 60)

    classifier = TaskClassifier()

    # 测试 1: 联系人名称恰好是"朋友圈"（应该被识别为朋友圈，而不是给名为"朋友圈"的人发消息）
    print("\n【边界测试 1】联系人名叫'朋友圈'")
    print("输入: ss:朋友圈:你好")
    task_type, parsed_data = classifier.classify_and_parse("ss:朋友圈:你好")
    if parsed_data and parsed_data.get("type") == "post_moment_only_text":
        print("✓ 正确识别为发朋友圈（预期行为）")
        print(f"  type: {parsed_data['type']}")
        print(f"  content: {parsed_data['content']}")
    else:
        print("⚠️  识别为发消息（如果你真有联系人叫'朋友圈'，需要用智能模式）")

    # 测试 2: 内容中包含多个冒号
    print("\n【边界测试 2】内容包含多个冒号")
    print("输入: ss:张三:时间:明天:下午3:30")
    task_type, parsed_data = classifier.classify_and_parse("ss:张三:时间:明天:下午3:30")
    if parsed_data and parsed_data.get("content") == "时间:明天:下午3:30":
        print("✓ 正确处理多个冒号")
        print(f"  recipient: {parsed_data['recipient']}")
        print(f"  content: {parsed_data['content']}")
    else:
        print("✗ 处理失败")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("简化后的 SS 快速模式格式测试")
    print("=" * 60)

    try:
        # 测试 1: 简化的发消息格式
        test_simplified_message_format()

        # 测试 2: 朋友圈格式
        test_moments_format()

        # 测试 3: 边界情况
        test_edge_cases()

        # 总结
        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)
        print("\n新的 SS 格式：")
        print("  发消息（默认）: ss:联系人:消息内容")
        print("  发朋友圈:       ss:朋友圈:朋友圈内容")
        print("\n特点：")
        print("  ✓ 更简洁：不需要 '消息:' 前缀")
        print("  ✓ 更直观：直接输入联系人和内容")
        print("  ✓ 向后兼容：朋友圈格式保持不变")

    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
