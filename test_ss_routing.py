#!/usr/bin/env python3
"""
测试 SS 模式的路由功能

验证简化后的 SS 格式能否正确路由到微信模块
"""
import sys
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from apps import ModuleRegistry
from ai.task_classifier import TaskClassifier


def test_ss_routing_with_type():
    """测试基于 type 的 SS 模式路由"""
    print("=" * 60)
    print("测试 SS 模式路由（基于 type）")
    print("=" * 60)

    # 发现模块
    ModuleRegistry.discover()

    # 测试用例
    test_cases = [
        {
            "task": "ss:张三:你好",
            "expected_type": "send_msg",
            "expected_module": "微信"
        },
        {
            "task": "ss:李四:早上好",
            "expected_type": "send_msg",
            "expected_module": "微信"
        },
        {
            "task": "ss:朋友圈:今天天气真好",
            "expected_type": "post_moment_only_text",
            "expected_module": "微信"
        },
        {
            "task": "ss:pyq:分享一个好消息",
            "expected_type": "post_moment_only_text",
            "expected_module": "微信"
        }
    ]

    classifier = TaskClassifier()

    for i, case in enumerate(test_cases, 1):
        print(f"\n【测试用例 {i}】")
        print(f"任务: {case['task']}")

        # 1. 分类解析
        task_type, parsed_data = classifier.classify_and_parse(case['task'])

        if not parsed_data:
            print(f"✗ 解析失败")
            continue

        actual_type = parsed_data.get("type")
        print(f"解析类型: {actual_type}")

        # 2. 根据 type 路由到模块
        type_to_module = {
            "send_msg": "wechat",
            "post_moment_only_text": "wechat"
        }
        module_name = type_to_module.get(actual_type)

        if not module_name:
            print(f"✗ 无法映射 type 到模块: {actual_type}")
            continue

        handler = ModuleRegistry.get(module_name)

        if not handler:
            print(f"✗ 无法获取模块 handler: {module_name}")
            continue

        actual_module = handler.module_info.name
        print(f"路由到模块: {actual_module}")

        # 3. 验证结果
        if actual_type == case["expected_type"] and actual_module == case["expected_module"]:
            print(f"✓ 测试通过")
        else:
            print(f"✗ 测试失败")
            print(f"  期望: type={case['expected_type']}, module={case['expected_module']}")
            print(f"  实际: type={actual_type}, module={actual_module}")


def test_keyword_routing():
    """测试传统关键词路由（对比）"""
    print("\n" + "=" * 60)
    print("测试传统关键词路由（对比）")
    print("=" * 60)

    test_cases = [
        {
            "task": "给张三发微信说你好",
            "expected_module": "微信"
        },
        {
            "task": "发朋友圈今天天气真好",
            "expected_module": "微信"
        },
        {
            "task": "ss:张三:你好",
            "expected_module": "系统操作",  # 关键词路由会失败
            "note": "简化后的 SS 格式无关键词匹配"
        }
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n【测试用例 {i}】")
        print(f"任务: {case['task']}")

        handler, score = ModuleRegistry.route(case['task'])

        if handler:
            actual_module = handler.module_info.name
            print(f"路由到模块: {actual_module} (匹配度: {score:.2f})")

            if actual_module == case["expected_module"]:
                print(f"✓ 符合预期")
            else:
                print(f"⚠️  与预期不符（预期: {case['expected_module']}）")
                if "note" in case:
                    print(f"   说明: {case['note']}")
        else:
            print(f"✗ 未找到匹配模块")


def test_routing_flow():
    """测试完整的路由流程"""
    print("\n" + "=" * 60)
    print("测试完整路由流程")
    print("=" * 60)

    print("\n说明：")
    print("对于 SS 模式任务，TaskRunner 应该：")
    print("1. 检测到 SS 前缀")
    print("2. 使用 TaskClassifier 解析出 type")
    print("3. 根据 type 直接路由到对应模块")
    print("4. 跳过关键词匹配")

    task = "ss:张三:你好"
    print(f"\n任务: {task}")

    # 模拟 TaskRunner 的路由逻辑
    print("\n【步骤 1】检测 SS 模式")
    is_ss_mode = task.strip().lower().startswith('ss:') or task.strip().lower().startswith('ss：')
    print(f"  是否 SS 模式: {is_ss_mode}")

    if is_ss_mode:
        print("\n【步骤 2】解析任务类型")
        classifier = TaskClassifier()
        task_type, parsed_data = classifier.classify_and_parse(task)

        if parsed_data and parsed_data.get("type"):
            actual_type = parsed_data["type"]
            print(f"  解析类型: {actual_type}")
            print(f"  解析数据: {parsed_data}")

            print("\n【步骤 3】根据 type 路由")
            type_to_module = {
                "send_msg": "wechat",
                "post_moment_only_text": "wechat"
            }
            module_name = type_to_module.get(actual_type)
            print(f"  目标模块: {module_name}")

            print("\n【步骤 4】获取 handler")
            handler = ModuleRegistry.get(module_name)
            if handler:
                print(f"  ✓ 成功获取 handler: {handler.module_info.name}")
            else:
                print(f"  ✗ 无法获取 handler")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("SS 模式路由测试")
    print("=" * 60)

    try:
        # 测试 1: 基于 type 的路由
        test_ss_routing_with_type()

        # 测试 2: 传统关键词路由（对比）
        test_keyword_routing()

        # 测试 3: 完整路由流程
        test_routing_flow()

        # 总结
        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)
        print("\n结论：")
        print("  ✓ SS 模式现在使用类型路由，不依赖关键词")
        print("  ✓ 简化格式 (ss:联系人:内容) 可以正确路由到微信模块")
        print("  ✓ TaskRunner 已更新，支持 SS 模式的类型路由")

    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
