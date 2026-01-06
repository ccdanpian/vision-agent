"""
示例：LLM任务分类器的新提示词格式

展示如何使用新的简洁提示词格式进行任务分类
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))


def show_prompt_format():
    """展示新的提示词格式"""
    print("=" * 60)
    print("LLM任务分类器 - 新提示词格式")
    print("=" * 60)

    print("\n【提示词格式】\n")
    print("messages = [")
    print("    {")
    print('        "role": "system",')
    print('        "content": "你是一个解析器，只输出JSON。字段包含：type(send_msg/post_moment/others), recipient, content"')
    print("    },")
    print("    {")
    print('        "role": "user",')
    print('        "content": "{用户输入的任务}"')
    print("    }")
    print("]")

    print("\n【输出格式】\n")
    print("{")
    print('    "type": "send_msg",      // send_msg / post_moment / others')
    print('    "recipient": "张三",     // 接收者')
    print('    "content": "你好"        // 内容')
    print("}")

    print("\n【分类逻辑】\n")
    print("- type == 'send_msg' 或 'post_moment' → 简单任务")
    print("- type == 'others' → 复杂任务")

    print("\n【示例】\n")

    examples = [
        {
            "input": "给张三发消息说你好",
            "output": '{"type": "send_msg", "recipient": "张三", "content": "你好"}',
            "classification": "简单任务"
        },
        {
            "input": "发朋友圈今天天气真好",
            "output": '{"type": "post_moment", "recipient": "", "content": "今天天气真好"}',
            "classification": "简单任务"
        },
        {
            "input": "给张三发消息说你好，然后截图发朋友圈",
            "output": '{"type": "others", "recipient": "", "content": "..."}',
            "classification": "复杂任务"
        }
    ]

    for i, example in enumerate(examples, 1):
        print(f"示例{i}:")
        print(f"  输入: {example['input']}")
        print(f"  输出: {example['output']}")
        print(f"  分类: {example['classification']}")
        print()


def test_with_regex():
    """测试正则模式（不需要API）"""
    print("=" * 60)
    print("测试正则模式（零成本）")
    print("=" * 60)

    from ai.task_classifier import TaskClassifier

    classifier = TaskClassifier(mode="regex")
    classifier.set_logger(print)

    test_cases = [
        "给张三发消息说你好",
        "发朋友圈今天天气真好",
        "给张三发消息说你好，然后截图发朋友圈"
    ]

    for task in test_cases:
        result = classifier.classify(task)
        print(f"\n任务: {task}")
        print(f"分类: {result.value}")


def test_with_llm():
    """测试LLM模式（需要配置API）"""
    print("\n" + "=" * 60)
    print("测试LLM模式（新提示词格式）")
    print("=" * 60)

    import config

    # 检查是否配置了LLM
    if not config.LLM_PROVIDER or (
        config.LLM_PROVIDER == "claude" and not config.ANTHROPIC_API_KEY
    ) or (
        config.LLM_PROVIDER == "openai" and not config.OPENAI_API_KEY
    ):
        print("\n未配置LLM，跳过LLM模式测试")
        print("请在.env文件中配置 LLM_PROVIDER 和相应的 API_KEY")
        print("\n提示：")
        print("1. 复制 .env.example 为 .env")
        print("2. 配置以下变量：")
        print("   LLM_PROVIDER=openai")
        print("   OPENAI_API_KEY=sk-xxx")
        print("   OPENAI_BASE_URL=https://api.openai.com/v1")
        print("   OPENAI_MODEL=gpt-4o")
        print("\n3. 启用LLM任务分类器：")
        print("   TASK_CLASSIFIER_MODE=llm")
        return

    from ai.task_classifier import TaskClassifier

    # 使用LLM模式
    classifier = TaskClassifier(mode="llm")
    classifier.set_logger(print)

    test_cases = [
        "给张三发消息说你好",
        "发朋友圈今天天气真好",
        "给张三发消息说你好，然后截图发朋友圈"
    ]

    print(f"\n使用LLM: {classifier.llm_config.model}")
    print()

    for task in test_cases:
        print(f"\n任务: {task}")
        result = classifier.classify(task)
        print(f"分类: {result.value}")


def main():
    """主函数"""
    # 展示提示词格式
    show_prompt_format()

    # 测试正则模式
    test_with_regex()

    # 测试LLM模式
    try:
        test_with_llm()
    except Exception as e:
        print(f"\nLLM测试失败: {e}")
        print("这通常是因为未配置LLM API密钥")


if __name__ == "__main__":
    main()
