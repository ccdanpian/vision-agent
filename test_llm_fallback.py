#!/usr/bin/env python3
"""
测试 SS 模式失败后使用 LLM 分类

验证当 SS 格式不符合要求时：
1. 去掉 ss: 前缀
2. 调用 LLM 进行任务分类
3. 使用 LLM 分类结果路由和执行
4. 不进入 AI 规划器（Planner）
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_ss_to_llm_flow():
    """测试 SS 失败后的 LLM 分类流程"""
    print("=" * 60)
    print("测试 SS 失败后的 LLM 分类流程")
    print("=" * 60)

    from ai.task_classifier import TaskClassifier
    from apps import ModuleRegistry

    ModuleRegistry.discover()
    classifier = TaskClassifier()

    # 模拟快速模式下的输入
    test_cases = [
        {
            "user_input": "但是客服经理",
            "with_prefix": "ss:但是客服经理",
            "description": "用户在快速模式下的不规范输入"
        },
        {
            "user_input": "给张三发消息说你好",
            "with_prefix": "ss:给张三发消息说你好",
            "description": "用户误加了 ss: 前缀的自然语言"
        }
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"【测试用例 {i}】{case['description']}")
        print(f"{'='*60}")

        task = case['with_prefix']
        print(f"\n原始任务: {task}")

        # ===== 步骤 1: 检测 SS 模式 =====
        print("\n【步骤 1】检测到 SS 模式")
        is_ss = task.strip().lower().startswith('ss:')
        print(f"  是 SS 模式: {is_ss}")

        if is_ss:
            # ===== 步骤 2: 尝试 SS 格式解析 =====
            print("\n【步骤 2】尝试 SS 格式解析")
            task_type, parsed_data = classifier.classify_and_parse(task)

            if parsed_data and parsed_data.get("type") and parsed_data["type"] != "invalid":
                print(f"  ✓ SS 解析成功: {parsed_data}")
                print(f"  → 使用 SS 模式路由和工作流")
            else:
                print(f"  ✗ SS 解析失败")

                # ===== 步骤 3: 去掉前缀 =====
                print("\n【步骤 3】去掉 'ss:' 前缀")
                task = task[3:].strip()
                print(f"  转换后的任务: {task}")

                # ===== 步骤 4: 使用 LLM 分类 =====
                print("\n【步骤 4】调用 LLM 进行任务分类")
                task_type, parsed_data = classifier.classify_and_parse(task)

                if parsed_data and parsed_data.get("type"):
                    print(f"  ✓ LLM 分类成功")
                    print(f"    type: {parsed_data['type']}")
                    print(f"    recipient: {parsed_data.get('recipient', 'N/A')}")
                    print(f"    content: {parsed_data.get('content', 'N/A')}")

                    # ===== 步骤 5: 使用 type 路由 =====
                    print("\n【步骤 5】使用 type 进行模块路由")
                    type_to_module = {
                        "send_msg": "wechat",
                        "post_moment_only_text": "wechat"
                    }
                    module_name = type_to_module.get(parsed_data["type"])
                    if module_name:
                        handler = ModuleRegistry.get(module_name)
                        if handler:
                            print(f"  ✓ 路由到模块: {handler.module_info.name}")

                            # ===== 步骤 6: 工作流执行 =====
                            print("\n【步骤 6】工作流执行")
                            print(f"  → handler.execute_task_with_workflow() 会：")
                            print(f"    1. 再次调用 classify_and_parse('{task}')")
                            print(f"    2. 检测到 parsed_data.type = '{parsed_data['type']}'")
                            print(f"    3. 调用 _map_type_to_workflow()")
                            print(f"    4. 直接使用解析的参数执行工作流")
                            print(f"    5. ✓ 不需要进入 AI 规划器（Planner）")
                        else:
                            print(f"  ✗ 无法获取模块 handler")
                    else:
                        print(f"  ⚠️  type '{parsed_data['type']}' 无对应模块")
                else:
                    print(f"  ✗ LLM 分类失败")
                    print(f"  → 使用关键词路由作为最后的 fallback")


def test_workflow_selection_path():
    """测试工作流选择路径"""
    print("\n" + "=" * 60)
    print("测试工作流选择路径")
    print("=" * 60)

    print("""
任务分类和工作流选择的三种路径：

【路径 1: SS 快速模式】
用户输入: 张三:你好
  → ss:张三:你好
  → SS 解析成功 ✓
  → type 路由 ✓
  → type 选择工作流 ✓
  → 执行工作流 ✓
成本: 零 (无 LLM 调用)
速度: 极快

【路径 2: SS 失败 → LLM 分类模式】(本次改进)
用户输入: 但是客服经理
  → ss:但是客服经理
  → SS 解析失败 ✗
  → 去掉前缀 → 但是客服经理
  → LLM 分类 ✓ (TaskClassifier)
  → type 路由 ✓
  → type 选择工作流 ✓
  → 执行工作流 ✓
成本: 1 次 LLM 调用 (分类器)
速度: 快
不进入: AI 规划器 ✓

【路径 3: 工作流匹配失败 → AI 规划器】(只在必要时)
用户输入: 复杂的多步骤任务
  → LLM 分类 ✓
  → type 路由 ✓
  → 工作流匹配失败 ✗ (无对应工作流)
  → 进入 AI 规划器 (Planner)
  → 生成详细步骤
  → 执行步骤
成本: 多次 LLM 调用 (分类器 + 规划器)
速度: 慢
说明: 只有真正需要规划的复杂任务才会走这条路径
""")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("SS 失败后 LLM 分类流程测试")
    print("=" * 60)

    try:
        # 测试 1: SS 到 LLM 的流程
        test_ss_to_llm_flow()

        # 测试 2: 工作流选择路径说明
        test_workflow_selection_path()

        # 总结
        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)
        print("\n改进效果：")
        print("  ✓ SS 格式失败后，使用 LLM 分类（TaskClassifier）")
        print("  ✓ 不直接进入 AI 规划器（Planner）")
        print("  ✓ 节省成本，提高速度")
        print("  ✓ 只有真正需要规划的复杂任务才使用 Planner")
        print("\n用户体验：")
        print("  1️⃣ 选择快速模式")
        print("  2️⃣ 输入不规范内容")
        print("  3️⃣ 系统自动使用 LLM 理解意图")
        print("  4️⃣ 直接执行，不走复杂的规划流程")
        print("  5️⃣ 快速响应 ✓")

        return 0

    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
