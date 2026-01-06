#!/usr/bin/env python3
"""
测试 SS 模式的工作流匹配

验证简化后的 SS 格式能否正确匹配工作流
"""
import sys
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from apps import ModuleRegistry
from ai.task_classifier import TaskClassifier


def test_ss_workflow_matching():
    """测试 SS 模式的工作流匹配"""
    print("=" * 60)
    print("测试 SS 模式工作流匹配")
    print("=" * 60)

    # 发现模块
    ModuleRegistry.discover()

    # 获取微信 handler
    handler = ModuleRegistry.get("wechat")
    if not handler:
        print("✗ 无法获取微信模块")
        return False

    # 测试用例
    test_cases = [
        {
            "task": "ss:张三:你好",
            "expected_workflow": "send_message",
            "expected_params": {
                "contact": "张三",
                "message": "你好"
            }
        },
        {
            "task": "ss:李四:早上好，今天开会",
            "expected_workflow": "send_message",
            "expected_params": {
                "contact": "李四",
                "message": "早上好，今天开会"
            }
        },
        {
            "task": "ss:朋友圈:今天天气真好",
            "expected_workflow": "post_moments",
            "expected_params": {
                "content": "今天天气真好"
            }
        },
        {
            "task": "ss:pyq:分享一个好消息",
            "expected_workflow": "post_moments",
            "expected_params": {
                "content": "分享一个好消息"
            }
        }
    ]

    classifier = TaskClassifier()
    all_passed = True

    for i, case in enumerate(test_cases, 1):
        print(f"\n【测试用例 {i}】")
        print(f"任务: {case['task']}")

        # 1. 分类解析
        task_type, parsed_data = classifier.classify_and_parse(case['task'])

        if not parsed_data or not parsed_data.get("type"):
            print(f"✗ 解析失败")
            all_passed = False
            continue

        print(f"解析结果: {parsed_data}")

        # 2. 类型到工作流映射
        parsed_type = parsed_data["type"]
        workflow_name = handler._map_type_to_workflow(parsed_type)

        if not workflow_name:
            print(f"✗ 无法映射 type 到工作流: {parsed_type}")
            all_passed = False
            continue

        print(f"工作流: {workflow_name}")

        # 3. 参数映射
        params = handler._map_parsed_data_to_workflow_params(parsed_data, workflow_name)
        print(f"参数: {params}")

        # 4. 验证结果
        if workflow_name == case["expected_workflow"]:
            print(f"✓ 工作流匹配正确")
        else:
            print(f"✗ 工作流匹配错误")
            print(f"  期望: {case['expected_workflow']}")
            print(f"  实际: {workflow_name}")
            all_passed = False

        if params == case["expected_params"]:
            print(f"✓ 参数映射正确")
        else:
            print(f"✗ 参数映射错误")
            print(f"  期望: {case['expected_params']}")
            print(f"  实际: {params}")
            all_passed = False

    return all_passed


def test_execute_task_with_workflow():
    """测试完整的 execute_task_with_workflow 流程"""
    print("\n" + "=" * 60)
    print("测试完整工作流执行流程")
    print("=" * 60)

    # 发现模块
    ModuleRegistry.discover()

    # 获取微信 handler
    handler = ModuleRegistry.get("wechat")
    if not handler:
        print("✗ 无法获取微信模块")
        return False

    # 测试用例（只测试到工作流选择和参数提取，不真正执行）
    test_cases = [
        {
            "task": "ss:张三:你好",
            "expected_workflow": "send_message",
        },
        {
            "task": "ss:朋友圈:今天天气真好",
            "expected_workflow": "post_moments",
        }
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n【测试用例 {i}】")
        print(f"任务: {case['task']}")

        # 模拟 execute_task_with_workflow 的逻辑（不真正执行）
        from ai.task_classifier import get_task_classifier
        classifier = get_task_classifier()
        task_type, parsed_data = classifier.classify_and_parse(case['task'])

        print(f"解析数据: {parsed_data}")

        if parsed_data and parsed_data.get("type"):
            task_parsed_type = parsed_data["type"]
            workflow_name = handler._map_type_to_workflow(task_parsed_type)

            if workflow_name:
                params = handler._map_parsed_data_to_workflow_params(parsed_data, workflow_name)
                print(f"选择工作流: {workflow_name} (type={task_parsed_type})")
                print(f"提取参数: {params}")

                if workflow_name == case["expected_workflow"]:
                    print(f"✓ 工作流选择正确")
                else:
                    print(f"✗ 工作流选择错误")
                    print(f"  期望: {case['expected_workflow']}")
                    print(f"  实际: {workflow_name}")
                    return False
            else:
                print(f"✗ 无法映射 type: {task_parsed_type}")
                return False
        else:
            print(f"✗ 解析失败")
            return False

    return True


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("SS 模式工作流测试")
    print("=" * 60)

    try:
        # 测试 1: 工作流匹配
        test1_passed = test_ss_workflow_matching()

        # 测试 2: 完整流程
        test2_passed = test_execute_task_with_workflow()

        # 总结
        print("\n" + "=" * 60)
        if test1_passed and test2_passed:
            print("所有测试通过 ✓")
            print("=" * 60)
            print("\n结论：")
            print("  ✓ SS 模式现在可以直接根据 type 选择工作流")
            print("  ✓ 不依赖关键词匹配")
            print("  ✓ 简化格式完全支持")
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
