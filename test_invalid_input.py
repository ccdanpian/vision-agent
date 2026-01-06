"""
测试 invalid 类型处理

测试场景：
1. 空白输入
2. 无意义字符
3. 误触输入
4. 错误格式
"""
import sys
from ai.task_classifier import TaskClassifier


def test_invalid_inputs():
    """测试无效输入的识别"""
    print("=" * 60)
    print("测试 invalid 类型识别（需要 LLM API）")
    print("=" * 60)

    classifier = TaskClassifier(mode="llm")
    classifier.set_logger(print)

    # 无效输入测试用例
    invalid_cases = [
        # 空白输入
        "",
        "   ",
        "\n",
        "\t\t",

        # 无意义字符
        "aaa",
        "123",
        "！！！",
        "???",
        "...",

        # 误触输入
        "s",
        "ss",  # 不完整的 SS 模式
        "、、、",
        "，，",

        # 不清楚的指令
        "帮我",
        "那个",
        "嗯",
        "好的",
        "收到",
    ]

    # 有效输入对比（应该不是 invalid）
    valid_cases = [
        "给张三发消息说你好",
        "发朋友圈今天天气真好",
        "ss:消息:张三:你好",
    ]

    print("\n【无效输入测试】")
    print("以下输入应该被识别为 invalid 类型：\n")

    invalid_count = 0
    for i, task in enumerate(invalid_cases, 1):
        display_task = repr(task) if task.strip() else "<空白>"
        print(f"{i}. 输入: {display_task}")

        task_type, parsed_data = classifier.classify_and_parse(task)

        if parsed_data and parsed_data.get("type") == "invalid":
            print(f"   ✓ 正确识别为 invalid")
            invalid_count += 1
        else:
            print(f"   ✗ 未识别为 invalid (type={parsed_data.get('type') if parsed_data else 'None'})")

        print()

    print(f"无效输入识别率: {invalid_count}/{len(invalid_cases)} ({invalid_count*100//len(invalid_cases)}%)")

    print("\n" + "=" * 60)
    print("【有效输入测试】")
    print("以下输入不应该被识别为 invalid 类型：\n")

    valid_count = 0
    for i, task in enumerate(valid_cases, 1):
        print(f"{i}. 输入: {task}")

        task_type, parsed_data = classifier.classify_and_parse(task)

        if parsed_data and parsed_data.get("type") != "invalid":
            print(f"   ✓ 正确识别为有效输入 (type={parsed_data.get('type')})")
            valid_count += 1
        else:
            print(f"   ✗ 错误识别为 invalid")

        print()

    print(f"有效输入识别率: {valid_count}/{len(valid_cases)} ({valid_count*100//len(valid_cases)}%)")


def test_handler_invalid_handling():
    """测试 Handler 对 invalid 类型的处理"""
    print("\n" + "=" * 60)
    print("测试 Handler 对 invalid 类型的处理")
    print("=" * 60)

    # 这个测试需要完整的环境，这里只演示逻辑
    print("\n模拟测试：")
    print("1. 输入: <空白>")
    print("   → LLM 解析: {type: 'invalid', ...}")
    print("   → Handler 检测到 invalid")
    print("   → 返回: {success: False, message: '无效的输入指令...'}")
    print("   ✓ 提前终止，不继续执行工作流")

    print("\n2. 输入: '给张三发消息说你好'")
    print("   → LLM 解析: {type: 'send_msg', ...}")
    print("   → Handler 正常处理")
    print("   → 执行工作流")
    print("   ✓ 正常执行")


if __name__ == "__main__":
    print("开始测试 invalid 类型处理...\n")

    # 检查是否配置了 LLM
    import config
    if not config.CUSTOM_LLM_API_KEY and not config.OPENAI_API_KEY and not config.ANTHROPIC_API_KEY:
        print("⚠️  警告：未配置 LLM API，无法测试 invalid 类型识别")
        print("请在 .env 中配置以下任一 API：")
        print("- CUSTOM_LLM_API_KEY (自定义 API)")
        print("- OPENAI_API_KEY (OpenAI)")
        print("- ANTHROPIC_API_KEY (Claude)")
        sys.exit(1)

    # 测试无效输入识别
    test_invalid_inputs()

    # 测试 Handler 处理
    test_handler_invalid_handling()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
