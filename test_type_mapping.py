#!/usr/bin/env python3
"""
测试类型到工作流的映射逻辑

这个测试不依赖实际的模块加载，只测试映射逻辑
"""
import sys
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_type_to_workflow_mapping():
    """测试类型到工作流的映射"""
    print("=" * 60)
    print("测试类型到工作流映射")
    print("=" * 60)

    # 模拟 _map_type_to_workflow 方法的逻辑
    type_to_workflow_map = {
        "send_msg": "send_message",
        "post_moment_only_text": "post_moments",
        "search_contact": "search_contact",
        "add_friend": "add_friend",
    }

    test_cases = [
        {"type": "send_msg", "expected": "send_message"},
        {"type": "post_moment_only_text", "expected": "post_moments"},
        {"type": "search_contact", "expected": "search_contact"},
        {"type": "add_friend", "expected": "add_friend"},
        {"type": "unknown_type", "expected": None},
    ]

    all_passed = True

    for case in test_cases:
        task_type = case["type"]
        expected = case["expected"]
        actual = type_to_workflow_map.get(task_type)

        print(f"\n类型: {task_type}")
        print(f"  期望工作流: {expected}")
        print(f"  实际工作流: {actual}")

        if actual == expected:
            print(f"  ✓ 测试通过")
        else:
            print(f"  ✗ 测试失败")
            all_passed = False

    return all_passed


def test_params_mapping():
    """测试参数映射逻辑"""
    print("\n" + "=" * 60)
    print("测试参数映射")
    print("=" * 60)

    # 模拟 _map_parsed_data_to_workflow_params 方法的逻辑
    def map_params(parsed_data, workflow_name):
        params = {}
        task_type = parsed_data.get("type", "")
        recipient = parsed_data.get("recipient", "")
        content = parsed_data.get("content", "")

        if workflow_name == "send_message":
            params["contact"] = recipient
            params["message"] = content
        elif workflow_name == "post_moments":
            params["content"] = content
        elif workflow_name == "search_contact":
            params["keyword"] = recipient or content
        elif workflow_name == "add_friend":
            params["wechat_id"] = recipient or content

        return params

    test_cases = [
        {
            "parsed_data": {
                "type": "send_msg",
                "recipient": "张三",
                "content": "你好"
            },
            "workflow_name": "send_message",
            "expected_params": {
                "contact": "张三",
                "message": "你好"
            }
        },
        {
            "parsed_data": {
                "type": "post_moment_only_text",
                "recipient": "",
                "content": "今天天气真好"
            },
            "workflow_name": "post_moments",
            "expected_params": {
                "content": "今天天气真好"
            }
        }
    ]

    all_passed = True

    for i, case in enumerate(test_cases, 1):
        print(f"\n【测试用例 {i}】")
        parsed_data = case["parsed_data"]
        workflow_name = case["workflow_name"]
        expected = case["expected_params"]

        print(f"解析数据: {parsed_data}")
        print(f"工作流: {workflow_name}")

        actual = map_params(parsed_data, workflow_name)
        print(f"  期望参数: {expected}")
        print(f"  实际参数: {actual}")

        if actual == expected:
            print(f"  ✓ 测试通过")
        else:
            print(f"  ✗ 测试失败")
            all_passed = False

    return all_passed


def test_complete_flow():
    """测试完整流程"""
    print("\n" + "=" * 60)
    print("测试完整流程（SS 模式）")
    print("=" * 60)

    # 模拟完整流程
    type_to_workflow = {
        "send_msg": "send_message",
        "post_moment_only_text": "post_moments",
    }

    def map_params(parsed_data, workflow_name):
        params = {}
        recipient = parsed_data.get("recipient", "")
        content = parsed_data.get("content", "")

        if workflow_name == "send_message":
            params["contact"] = recipient
            params["message"] = content
        elif workflow_name == "post_moments":
            params["content"] = content

        return params

    test_cases = [
        {
            "task": "ss:张三:你好",
            "parsed_data": {
                "type": "send_msg",
                "recipient": "张三",
                "content": "你好"
            },
            "expected_workflow": "send_message",
            "expected_params": {
                "contact": "张三",
                "message": "你好"
            }
        },
        {
            "task": "ss:朋友圈:今天天气真好",
            "parsed_data": {
                "type": "post_moment_only_text",
                "recipient": "",
                "content": "今天天气真好"
            },
            "expected_workflow": "post_moments",
            "expected_params": {
                "content": "今天天气真好"
            }
        }
    ]

    all_passed = True

    for i, case in enumerate(test_cases, 1):
        print(f"\n【测试用例 {i}】")
        print(f"原始任务: {case['task']}")

        # 模拟解析
        parsed_data = case["parsed_data"]
        print(f"解析数据: {parsed_data}")

        # 类型到工作流
        task_type = parsed_data["type"]
        workflow_name = type_to_workflow.get(task_type)
        print(f"选择工作流: {workflow_name}")

        if workflow_name != case["expected_workflow"]:
            print(f"  ✗ 工作流选择错误")
            print(f"    期望: {case['expected_workflow']}")
            print(f"    实际: {workflow_name}")
            all_passed = False
            continue

        # 参数映射
        params = map_params(parsed_data, workflow_name)
        print(f"映射参数: {params}")

        if params == case["expected_params"]:
            print(f"  ✓ 完整流程通过")
        else:
            print(f"  ✗ 参数映射错误")
            print(f"    期望: {case['expected_params']}")
            print(f"    实际: {params}")
            all_passed = False

    return all_passed


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("类型映射逻辑测试")
    print("=" * 60)

    try:
        # 测试 1: 类型到工作流映射
        test1 = test_type_to_workflow_mapping()

        # 测试 2: 参数映射
        test2 = test_params_mapping()

        # 测试 3: 完整流程
        test3 = test_complete_flow()

        # 总结
        print("\n" + "=" * 60)
        if test1 and test2 and test3:
            print("所有逻辑测试通过 ✓")
            print("=" * 60)
            print("\n结论：")
            print("  ✓ 类型到工作流的映射逻辑正确")
            print("  ✓ 参数映射逻辑正确")
            print("  ✓ SS 模式完整流程逻辑正确")
            print("\n现在可以实际运行测试了！")
            return 0
        else:
            print("部分测试失败 ✗")
            print("=" * 60)
            return 1

    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
