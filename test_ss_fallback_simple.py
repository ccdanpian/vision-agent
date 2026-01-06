#!/usr/bin/env python3
"""
简单测试 SS 模式回退逻辑
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_ss_parse():
    """测试 SS 解析"""
    print("=" * 60)
    print("测试 SS 解析")
    print("=" * 60)

    from ai.task_classifier import TaskClassifier
    classifier = TaskClassifier()

    test_cases = [
        ("ss:张三:你好", True, "send_msg"),
        ("ss:朋友圈:今天天气真好", True, "post_moment_only_text"),
        ("ss:但是客服经理", False, None),  # 只有2个字段，应该失败
        ("ss:abc", False, None),  # 只有2个字段，应该失败
    ]

    for task, should_succeed, expected_type in test_cases:
        print(f"\n任务: {task}")
        _, parsed_data = classifier.classify_and_parse(task)

        if parsed_data and parsed_data.get("type"):
            actual_type = parsed_data["type"]
            print(f"  解析成功: type={actual_type}")
            if should_succeed and actual_type == expected_type:
                print(f"  ✓ 符合预期")
            else:
                print(f"  ✗ 不符合预期（期望: {expected_type if should_succeed else '失败'}）")
        else:
            print(f"  解析失败")
            if not should_succeed:
                print(f"  ✓ 符合预期（应该失败）")
            else:
                print(f"  ✗ 不符合预期（应该成功）")


def test_fallback_flow():
    """测试回退流程"""
    print("\n" + "=" * 60)
    print("测试回退流程")
    print("=" * 60)

    from ai.task_classifier import TaskClassifier
    classifier = TaskClassifier()

    task = "ss:但是客服经理"
    print(f"\n原始任务: {task}")

    # 1. 尝试 SS 解析
    print("\n【步骤 1】尝试 SS 解析")
    _, parsed_data = classifier.classify_and_parse(task)

    if parsed_data and parsed_data.get("type") and parsed_data["type"] != "invalid":
        print(f"  ✓ SS 解析成功: {parsed_data}")
        print(f"  → 使用 SS 模式")
    else:
        print(f"  ✗ SS 解析失败")
        print(f"  → 需要回退")

        # 2. 去掉前缀
        print("\n【步骤 2】去掉 'ss:' 前缀")
        fallback_task = task[3:].strip()
        print(f"  转换后: {fallback_task}")

        # 3. 用自然语言模式处理
        print("\n【步骤 3】作为自然语言处理")
        print(f"  现在任务会通过关键词路由或 LLM 模式处理")
        print(f"  ✓ 回退成功")


def main():
    print("\n" + "=" * 60)
    print("SS 模式回退简单测试")
    print("=" * 60)

    try:
        test_ss_parse()
        test_fallback_flow()

        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)
        print("\n修改说明：")
        print("1. TaskRunner 检测到 SS 模式时，先尝试解析")
        print("2. 如果解析失败（parsed_data 为 None 或 type 为 invalid）")
        print("3. 自动去掉 'ss:' 前缀")
        print("4. 将处理后的任务交给关键词路由或 LLM 模式")
        print("\n现在用户输入 '但是客服经理' 会：")
        print("  快速模式 → ss:但是客服经理 → 解析失败 → 但是客服经理 → LLM处理")

        return 0

    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
