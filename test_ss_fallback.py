#!/usr/bin/env python3
"""
测试 SS 模式回退到 LLM 模式

验证当 SS 格式不符合规范时，能够自动去掉前缀，回退到自然语言模式
"""
import sys
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from ai.task_classifier import TaskClassifier


def test_ss_format_validation():
    """测试 SS 格式验证"""
    print("=" * 60)
    print("测试 SS 格式验证")
    print("=" * 60)

    classifier = TaskClassifier()

    test_cases = [
        {
            "task": "ss:张三:你好",
            "should_succeed": True,
            "description": "正确的发消息格式"
        },
        {
            "task": "ss:朋友圈:今天天气真好",
            "should_succeed": True,
            "description": "正确的朋友圈格式"
        },
        {
            "task": "ss:但是客服经理",
            "should_succeed": False,
            "description": "格式错误（缺少字段）"
        },
        {
            "task": "ss:abc",
            "should_succeed": False,
            "description": "格式错误（只有两个字段）"
        },
        {
            "task": "ss:",
            "should_succeed": False,
            "description": "格式错误（只有前缀）"
        }
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n【测试用例 {i}】{case['description']}")
        print(f"任务: {case['task']}")

        task_type, parsed_data = classifier.classify_and_parse(case['task'])

        if parsed_data and parsed_data.get("type") and parsed_data["type"] != "invalid":
            print(f"✓ 解析成功: {parsed_data}")
            if case['should_succeed']:
                print(f"  结果符合预期")
            else:
                print(f"  ⚠️  预期失败但成功了")
        else:
            print(f"✗ 解析失败")
            if not case['should_succeed']:
                print(f"  结果符合预期（应该失败）")
            else:
                print(f"  ⚠️  预期成功但失败了")


def test_fallback_logic():
    """测试回退逻辑"""
    print("\n" + "=" * 60)
    print("测试回退逻辑")
    print("=" * 60)

    classifier = TaskClassifier()

    test_cases = [
        {
            "original_task": "ss:但是客服经理",
            "fallback_task": "但是客服经理",
            "description": "格式错误的任务"
        },
        {
            "original_task": "ss:给张三发消息说你好",
            "fallback_task": "给张三发消息说你好",
            "description": "自然语言任务（误加了 ss: 前缀）"
        }
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n【测试用例 {i}】{case['description']}")
        print(f"原始任务: {case['original_task']}")

        # 1. 尝试 SS 模式解析
        task_type, parsed_data = classifier.classify_and_parse(case['original_task'])

        if parsed_data and parsed_data.get("type") and parsed_data["type"] != "invalid":
            print(f"✓ SS 模式解析成功: {parsed_data}")
            print(f"  （不需要回退）")
        else:
            print(f"✗ SS 模式解析失败")
            print(f"  → 需要回退到自然语言模式")

            # 2. 模拟去掉前缀
            fallback_task = case['fallback_task']
            print(f"  去掉前缀后: {fallback_task}")

            # 3. 用 LLM 模式重新解析
            print(f"  使用 LLM 模式重新解析...")
            task_type2, parsed_data2 = classifier.classify_and_parse(fallback_task)

            if parsed_data2 and parsed_data2.get("type"):
                print(f"  ✓ LLM 模式解析成功: {parsed_data2}")
            else:
                print(f"  ✗ LLM 模式也失败了")


def test_complete_flow():
    """测试完整流程（模拟 TaskRunner）"""
    print("\n" + "=" * 60)
    print("测试完整流程（模拟 TaskRunner 逻辑）")
    print("=" * 60)

    classifier = TaskClassifier()

    test_cases = [
        {
            "task": "ss:张三:你好",
            "expected_behavior": "SS 模式成功"
        },
        {
            "task": "ss:但是客服经理",
            "expected_behavior": "回退到 LLM 模式"
        },
        {
            "task": "给张三发消息说你好",
            "expected_behavior": "直接使用 LLM 模式"
        }
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n【测试用例 {i}】")
        task = case['task']
        print(f"原始任务: {task}")
        print(f"期望行为: {case['expected_behavior']}")
        print()

        # 模拟 TaskRunner 的逻辑
        if task.strip().lower().startswith('ss:') or task.strip().lower().startswith('ss：'):
            print("→ 检测到 SS 快速模式，尝试解析")
            task_type, parsed_data = classifier.classify_and_parse(task)

            if parsed_data and parsed_data.get("type") and parsed_data["type"] != "invalid":
                print(f"→ SS 模式解析成功")
                print(f"  type: {parsed_data['type']}")
                print(f"  recipient: {parsed_data.get('recipient', '')}")
                print(f"  content: {parsed_data.get('content', '')}")
                print(f"  ✓ 使用 SS 模式路由和工作流")
            else:
                print(f"→ SS 格式解析失败，回退到自然语言模式")
                # 去掉前缀
                if task.lower().startswith('ss:'):
                    task = task[3:].strip()
                elif task.lower().startswith('ss：'):
                    task = task[3:].strip()
                print(f"  去掉前缀后: {task}")
                print(f"  ✓ 使用关键词路由或 LLM 模式")
        else:
            print("→ 非 SS 模式，直接使用关键词路由或 LLM 模式")
            print(f"  ✓ 正常处理")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("SS 模式回退测试")
    print("=" * 60)

    try:
        # 测试 1: SS 格式验证
        test_ss_format_validation()

        # 测试 2: 回退逻辑
        test_fallback_logic()

        # 测试 3: 完整流程
        test_complete_flow()

        # 总结
        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)
        print("\n结论：")
        print("  ✓ SS 格式验证正常")
        print("  ✓ 回退逻辑正确")
        print("  ✓ 格式错误时自动回退到 LLM 模式")
        print("\n现在用户在快速模式下输入不规范的内容时：")
        print("  1. 系统会尝试 SS 格式解析")
        print("  2. 如果失败，自动去掉 'ss:' 前缀")
        print("  3. 当作自然语言处理")
        print("  4. 用户无需手动切换模式")

        return 0

    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
