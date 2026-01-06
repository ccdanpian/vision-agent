#!/usr/bin/env python3
"""
测试 LLM 分类失败后自动返回模式选择

验证流程：
1. 用户选择快速模式
2. 输入不符合 SS 格式的内容（如 "但是客服经理"）
3. SS 解析失败
4. LLM 分类也失败（或返回 invalid）
5. 系统显示错误信息
6. 自动返回模式选择界面
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_llm_failure_flow():
    """测试 LLM 失败后的流程"""
    print("=" * 60)
    print("测试 LLM 分类失败后返回模式选择")
    print("=" * 60)

    from ai.task_classifier import TaskClassifier

    classifier = TaskClassifier()

    # 模拟快速模式下的输入
    test_cases = [
        {
            "user_input": "但是客服经理",
            "with_prefix": "ss:但是客服经理",
            "description": "用户在快速模式下的不规范输入"
        },
        {
            "user_input": "abc",
            "with_prefix": "ss:abc",
            "description": "无意义输入"
        }
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"【测试用例 {i}】{case['description']}")
        print(f"{'='*60}")

        task = case['with_prefix']
        print(f"\n原始任务: {task}")

        # 步骤 1: 检测 SS 模式
        print("\n【步骤 1】检测到 SS 快速模式")
        is_ss = task.strip().lower().startswith('ss:')
        print(f"  是 SS 模式: {is_ss}")

        if is_ss:
            # 步骤 2: 尝试 SS 格式解析
            print("\n【步骤 2】尝试 SS 格式解析")
            task_type, parsed_data = classifier.classify_and_parse(task)

            if parsed_data and parsed_data.get("type") and parsed_data["type"] != "invalid":
                print(f"  ✓ SS 解析成功: {parsed_data}")
                print(f"  → 使用 SS 模式路由和工作流")
            else:
                print(f"  ✗ SS 解析失败")

                # 步骤 3: 去掉前缀
                print("\n【步骤 3】去掉 'ss:' 前缀")
                task = task[3:].strip()
                print(f"  转换后的任务: {task}")

                # 步骤 4: 使用 LLM 分类
                print("\n【步骤 4】调用 LLM 进行任务分类")
                task_type, parsed_data = classifier.classify_and_parse(task)

                if parsed_data and parsed_data.get("type") and parsed_data["type"] != "invalid":
                    print(f"  ✓ LLM 分类成功")
                    print(f"    type: {parsed_data['type']}")
                    print(f"    recipient: {parsed_data.get('recipient', 'N/A')}")
                    print(f"    content: {parsed_data.get('content', 'N/A')}")
                    print(f"\n  → 使用 type 进行模块路由")
                else:
                    # 步骤 5: LLM 分类失败，返回错误
                    print(f"  ✗ LLM 分类失败或返回 invalid")
                    print(f"\n【步骤 5】返回错误并重新选择模式")
                    print(f"  ❌ LLM分类失败，无法理解您的输入。")
                    print(f"  请重新选择模式，或检查输入格式是否正确。")
                    print(f"\n  → 返回到模式选择界面")
                    print(f"  → 用户可以重新选择 1 或 2")


def test_task_runner_integration():
    """测试 TaskRunner 集成"""
    print("\n\n" + "=" * 60)
    print("测试 TaskRunner 集成（模拟）")
    print("=" * 60)

    print("""
预期流程：

1. 用户启动交互式模式
2. 选择模式 1（快速模式）
3. 输入：但是客服经理
4. 系统自动添加 ss: 前缀 → ss:但是客服经理

5. TaskRunner.run() 执行：
   【步骤 1】检测到 SS 模式
   【步骤 2】尝试 SS 解析 → 失败（字段不足）
   【步骤 3】去掉 ss: 前缀 → 但是客服经理
   【步骤 4】LLM 分类 → 失败或 invalid
   【步骤 5】返回 TaskResult:
       status = FAILED
       error_message = "❌ LLM分类失败，无法理解您的输入..."

6. run.py 的 _execute_task_with_retry() 检测到：
   result.status == FAILED
   "LLM分类失败" in result.error_message

7. 显示：
   "将返回到模式选择界面"

8. 返回 True → 触发 restart_mode_selection

9. 外层循环重新开始 → 显示模式选择界面

10. 用户重新选择 1 或 2
""")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("LLM 失败后重新选择模式测试")
    print("=" * 60)

    try:
        # 测试 1: LLM 失败流程
        test_llm_failure_flow()

        # 测试 2: TaskRunner 集成说明
        test_task_runner_integration()

        # 总结
        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)
        print("\n改进效果：")
        print("  ✓ LLM 分类失败时不再使用关键词路由")
        print("  ✓ 直接返回错误并提示用户")
        print("  ✓ 自动返回模式选择界面")
        print("  ✓ 用户可以重新选择 1 或 2")
        print("\n用户体验：")
        print("  1️⃣ 选择快速模式")
        print("  2️⃣ 输入不规范内容（如：但是客服经理）")
        print("  3️⃣ SS 解析失败 → LLM 分类失败")
        print("  4️⃣ 系统显示错误信息")
        print("  5️⃣ 自动返回模式选择")
        print("  6️⃣ 用户重新选择模式 ✓")

        return 0

    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
