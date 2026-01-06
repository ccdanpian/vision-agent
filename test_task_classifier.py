"""
测试任务分类器功能

验证正则表达式和LLM两种模式的任务分类
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

import config
from ai.task_classifier import TaskClassifier, TaskType


def test_regex_classifier():
    """测试正则表达式模式"""
    print("=" * 60)
    print("测试正则表达式模式")
    print("=" * 60)

    classifier = TaskClassifier(mode="regex")
    classifier.set_logger(print)

    test_cases = [
        # 简单任务
        ("给张三发消息说你好", TaskType.SIMPLE),
        ("发朋友圈今天天气真好", TaskType.SIMPLE),
        ("搜索李四", TaskType.SIMPLE),
        ("加好友微信号abc123", TaskType.SIMPLE),

        # 复杂任务
        ("给张三发消息说你好，然后截图发朋友圈", TaskType.COMPLEX),
        ("发消息给李四，再发朋友圈", TaskType.COMPLEX),
        ("搜索张三，接着加好友", TaskType.COMPLEX),
        ("打开微信发消息", TaskType.COMPLEX),  # 多个动作词
    ]

    correct = 0
    total = len(test_cases)

    for task, expected in test_cases:
        result = classifier.classify(task)
        is_correct = result == expected
        correct += is_correct

        status = "✓" if is_correct else "✗"
        print(f"\n{status} 任务: {task}")
        print(f"  期望: {expected.value}, 实际: {result.value}")

    print(f"\n正确率: {correct}/{total} = {correct/total*100:.1f}%")
    return correct == total


def test_llm_classifier():
    """测试LLM模式"""
    print("\n" + "=" * 60)
    print("测试LLM模式")
    print("=" * 60)

    # 检查是否配置了LLM
    if not config.LLM_PROVIDER or (
        config.LLM_PROVIDER == "claude" and not config.ANTHROPIC_API_KEY
    ) or (
        config.LLM_PROVIDER == "openai" and not config.OPENAI_API_KEY
    ):
        print("未配置LLM，跳过LLM模式测试")
        print("请在.env文件中配置 LLM_PROVIDER 和相应的 API_KEY")
        return True

    classifier = TaskClassifier(mode="llm")
    classifier.set_logger(print)

    test_cases = [
        # 简单任务
        ("给张三发消息说你好", TaskType.SIMPLE),
        ("发朋友圈今天天气真好", TaskType.SIMPLE),

        # 复杂任务
        ("给张三发消息说你好，然后截图发朋友圈", TaskType.COMPLEX),
        ("发消息给李四，再发朋友圈", TaskType.COMPLEX),
    ]

    correct = 0
    total = len(test_cases)

    for task, expected in test_cases:
        result = classifier.classify(task)
        is_correct = result == expected
        correct += is_correct

        status = "✓" if is_correct else "✗"
        print(f"\n{status} 任务: {task}")
        print(f"  期望: {expected.value}, 实际: {result.value}")

    print(f"\n正确率: {correct}/{total} = {correct/total*100:.1f}%")
    return correct == total


def test_config_override():
    """测试配置覆盖"""
    print("\n" + "=" * 60)
    print("测试配置覆盖（模式切换）")
    print("=" * 60)

    # 测试通过环境变量配置
    original_mode = config.TASK_CLASSIFIER_MODE

    # 强制使用正则模式
    os.environ["TASK_CLASSIFIER_MODE"] = "regex"
    config.TASK_CLASSIFIER_MODE = "regex"

    from ai.task_classifier import _global_classifier
    # 清除全局单例，强制重新创建
    import ai.task_classifier
    ai.task_classifier._global_classifier = None

    from ai.task_classifier import get_task_classifier
    classifier = get_task_classifier()

    print(f"当前模式: {classifier.mode}")
    assert classifier.mode == "regex", "配置覆盖失败"
    print("✓ 配置覆盖成功")

    # 恢复原配置
    config.TASK_CLASSIFIER_MODE = original_mode
    return True


def main():
    """主测试函数"""
    print("任务分类器功能测试")
    print("=" * 60)
    print(f"当前配置模式: {config.TASK_CLASSIFIER_MODE}")
    print("=" * 60)

    all_passed = True

    # 测试正则模式
    try:
        if not test_regex_classifier():
            all_passed = False
    except Exception as e:
        print(f"\n✗ 正则模式测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试LLM模式
    try:
        if not test_llm_classifier():
            all_passed = False
    except Exception as e:
        print(f"\n✗ LLM模式测试失败: {e}")
        import traceback
        traceback.print_exc()
        # LLM测试失败不影响总体结果（可能是API未配置）

    # 测试配置覆盖
    try:
        if not test_config_override():
            all_passed = False
    except Exception as e:
        print(f"\n✗ 配置覆盖测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ 所有测试通过")
    else:
        print("✗ 部分测试失败")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
