"""
测试 SS 快速模式的任务分类和参数解析

SS 快速模式支持的格式：
1. 发消息：ss:消息:好友:消息内容
2. 发朋友圈：ss:朋友圈:消息内容
"""
import sys
from ai.task_classifier import TaskClassifier, TaskType


def test_ss_mode():
    """测试 SS 快速模式"""
    print("=" * 60)
    print("测试 SS 快速模式")
    print("=" * 60)

    # 创建分类器（不指定模式，由 SS 检测自动处理）
    classifier = TaskClassifier()
    classifier.set_logger(print)

    test_cases = [
        # SS 模式 - 发消息（中文冒号）
        ("ss：消息：张三：你好", TaskType.SIMPLE, "send_msg", "张三", "你好"),

        # SS 模式 - 发消息（英文冒号）
        ("ss:消息:李四:周末一起吃饭吧", TaskType.SIMPLE, "send_msg", "李四", "周末一起吃饭吧"),

        # SS 模式 - 发消息（大写SS）
        ("SS:发消息:王五:测试消息", TaskType.SIMPLE, "send_msg", "王五", "测试消息"),

        # SS 模式 - 发消息（混合大小写）
        ("Ss:xx:赵六:Hello World", TaskType.SIMPLE, "send_msg", "赵六", "Hello World"),

        # SS 模式 - 发消息（msg关键词）
        ("ss:msg:小明:这是一条测试消息", TaskType.SIMPLE, "send_msg", "小明", "这是一条测试消息"),

        # SS 模式 - 发朋友圈（中文关键词）
        ("ss:朋友圈:今天天气真好", TaskType.SIMPLE, "post_moment_only_text", "", "今天天气真好"),

        # SS 模式 - 发朋友圈（pyq关键词）
        ("ss:pyq:分享一个好消息", TaskType.SIMPLE, "post_moment_only_text", "", "分享一个好消息"),

        # SS 模式 - 发朋友圈（PYQ大写）
        ("SS:PYQ:测试朋友圈内容", TaskType.SIMPLE, "post_moment_only_text", "", "测试朋友圈内容"),

        # SS 模式 - 消息内容包含冒号
        ("ss:消息:张三:时间是明天下午3:30", TaskType.SIMPLE, "send_msg", "张三", "时间是明天下午3:30"),

        # SS 模式 - 朋友圈内容包含冒号
        ("ss:朋友圈:今日名言：人生苦短，及时行乐", TaskType.SIMPLE, "post_moment_only_text", "", "今日名言：人生苦短，及时行乐"),
    ]

    passed = 0
    failed = 0

    for i, (task, expected_type, expected_task_type, expected_recipient, expected_content) in enumerate(test_cases, 1):
        print(f"\n【测试用例 {i}】")
        print(f"输入: {task}")

        task_type, parsed_data = classifier.classify_and_parse(task)

        # 验证任务类型
        if task_type != expected_type:
            print(f"✗ 任务类型错误: 期望 {expected_type}, 实际 {task_type}")
            failed += 1
            continue

        # 验证解析数据
        if not parsed_data:
            print(f"✗ 解析失败: 无解析数据")
            failed += 1
            continue

        actual_task_type = parsed_data.get("type", "")
        actual_recipient = parsed_data.get("recipient", "")
        actual_content = parsed_data.get("content", "")

        if (actual_task_type == expected_task_type and
            actual_recipient == expected_recipient and
            actual_content == expected_content):
            print(f"✓ 测试通过")
            print(f"  type: {actual_task_type}")
            print(f"  recipient: {actual_recipient}")
            print(f"  content: {actual_content}")
            passed += 1
        else:
            print(f"✗ 解析错误:")
            print(f"  期望 type: {expected_task_type}, 实际: {actual_task_type}")
            print(f"  期望 recipient: {expected_recipient}, 实际: {actual_recipient}")
            print(f"  期望 content: {expected_content}, 实际: {actual_content}")
            failed += 1

    # 汇总结果
    print("\n" + "=" * 60)
    print(f"测试结果: 通过 {passed}/{len(test_cases)}, 失败 {failed}/{len(test_cases)}")
    print("=" * 60)

    return failed == 0


def test_normal_mode():
    """测试非 SS 模式（LLM 模式）"""
    print("\n" + "=" * 60)
    print("测试普通模式（应该走 LLM 路径）")
    print("=" * 60)

    classifier = TaskClassifier(mode="llm")
    classifier.set_logger(print)

    test_cases = [
        "给张三发消息说你好",
        "发朋友圈今天天气真好",
    ]

    print("\n注意：以下测试需要配置 LLM API 才能运行")
    print("如果未配置，将自动降级到正则模式\n")

    for task in test_cases:
        print(f"\n输入: {task}")
        task_type, parsed_data = classifier.classify_and_parse(task)
        print(f"任务类型: {task_type}")
        if parsed_data:
            print(f"解析数据: {parsed_data}")
        else:
            print("解析数据: None (可能降级到正则模式)")


def test_error_cases():
    """测试错误格式"""
    print("\n" + "=" * 60)
    print("测试错误格式（应该降级到 LLM 模式）")
    print("=" * 60)

    classifier = TaskClassifier()
    classifier.set_logger(print)

    error_cases = [
        "ss:消息:张三",  # 缺少消息内容
        "ss:朋友圈",  # 缺少朋友圈内容
        "ss:未知类型:参数",  # 未知任务类型
        "ss:",  # 空格式
    ]

    for task in error_cases:
        print(f"\n输入: {task}")
        task_type, parsed_data = classifier.classify_and_parse(task)
        print(f"任务类型: {task_type}")
        print(f"解析数据: {parsed_data}")
        print("（应该降级处理）")


if __name__ == "__main__":
    print("开始测试 SS 快速模式...\n")

    # 测试 SS 快速模式
    success = test_ss_mode()

    # 测试普通模式
    test_normal_mode()

    # 测试错误情况
    test_error_cases()

    # 退出码
    sys.exit(0 if success else 1)
