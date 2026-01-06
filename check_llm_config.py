"""
诊断脚本：检查 LLM 配置是否正确加载
"""
import config
from ai.task_classifier import get_task_classifier

print("=" * 60)
print("LLM 配置诊断")
print("=" * 60)

# 1. 检查任务分类器模式
print(f"\n【1. 任务分类器模式】")
print(f"TASK_CLASSIFIER_MODE = {config.TASK_CLASSIFIER_MODE}")

if config.TASK_CLASSIFIER_MODE == "regex":
    print("⚠️  当前使用正则模式，不会调用 LLM")
    print("提示：如果要使用 LLM，请在 .env 中设置：")
    print("     TASK_CLASSIFIER_MODE=llm")
elif config.TASK_CLASSIFIER_MODE == "llm":
    print("✓ 当前使用 LLM 模式")
else:
    print(f"⚠️  未知模式: {config.TASK_CLASSIFIER_MODE}")

# 2. 检查主 LLM 配置
print(f"\n【2. 主 LLM 配置】")
print(f"LLM_PROVIDER = {config.LLM_PROVIDER}")

if config.LLM_PROVIDER == "custom":
    print(f"CUSTOM_LLM_API_KEY = {config.CUSTOM_LLM_API_KEY[:20]}..." if config.CUSTOM_LLM_API_KEY else "未设置")
    print(f"CUSTOM_LLM_BASE_URL = {config.CUSTOM_LLM_BASE_URL}")
    print(f"CUSTOM_LLM_MODEL = {config.CUSTOM_LLM_MODEL}")
elif config.LLM_PROVIDER == "openai":
    print(f"OPENAI_API_KEY = {config.OPENAI_API_KEY[:20]}..." if config.OPENAI_API_KEY else "未设置")
    print(f"OPENAI_MODEL = {config.OPENAI_MODEL}")
elif config.LLM_PROVIDER == "claude":
    print(f"ANTHROPIC_API_KEY = {config.ANTHROPIC_API_KEY[:20]}..." if config.ANTHROPIC_API_KEY else "未设置")
    print(f"CLAUDE_MODEL = {config.CLAUDE_MODEL}")

# 3. 检查任务分类器专用 LLM 配置
print(f"\n【3. 任务分类器专用 LLM 配置】")
has_classifier_llm = False

if config.TASK_CLASSIFIER_LLM_PROVIDER:
    print(f"TASK_CLASSIFIER_LLM_PROVIDER = {config.TASK_CLASSIFIER_LLM_PROVIDER}")
    has_classifier_llm = True
elif config.TASK_CLASSIFIER_LLM_BASE_URL and config.TASK_CLASSIFIER_LLM_MODEL:
    print(f"TASK_CLASSIFIER_LLM_API_KEY = {config.TASK_CLASSIFIER_LLM_API_KEY[:20]}..." if config.TASK_CLASSIFIER_LLM_API_KEY else "未设置")
    print(f"TASK_CLASSIFIER_LLM_BASE_URL = {config.TASK_CLASSIFIER_LLM_BASE_URL}")
    print(f"TASK_CLASSIFIER_LLM_MODEL = {config.TASK_CLASSIFIER_LLM_MODEL}")
    has_classifier_llm = True
else:
    print("未设置（将使用主 LLM 配置）")

# 4. 实际使用的配置
print(f"\n【4. 任务分类器实际使用的 LLM】")
if config.TASK_CLASSIFIER_MODE == "llm":
    classifier = get_task_classifier()
    if hasattr(classifier, 'llm_config'):
        llm_config = classifier.llm_config
        print(f"✓ LLM 配置已加载")
        print(f"  - API Base URL: {llm_config.base_url}")
        print(f"  - Model: {llm_config.model}")
        print(f"  - Max Tokens: {llm_config.max_tokens}")
        print(f"  - Temperature: {llm_config.temperature}")

        if has_classifier_llm:
            print("\n说明：使用分类器专用 LLM 配置")
        else:
            print("\n说明：使用主 LLM 配置（.env 中的 LLM_PROVIDER 配置）")
    else:
        print("✗ LLM 配置未加载")
else:
    print("⚠️  当前使用正则模式，不需要 LLM 配置")

# 5. 测试 LLM 调用
print(f"\n【5. 测试 LLM 调用】")
if config.TASK_CLASSIFIER_MODE == "llm":
    print("测试任务：给张三发消息说你好")

    try:
        classifier = get_task_classifier()
        classifier.set_logger(print)

        task_type, parsed_data = classifier.classify_and_parse("给张三发消息说你好")

        print(f"\n✓ LLM 调用成功")
        print(f"  任务类型: {task_type}")
        print(f"  解析数据: {parsed_data}")

    except Exception as e:
        print(f"\n✗ LLM 调用失败: {e}")
        print("\n可能的原因：")
        print("  1. API Key 无效")
        print("  2. Base URL 错误")
        print("  3. 网络连接问题")
        print("  4. 模型名称错误")
else:
    print("⚠️  当前使用正则模式，跳过测试")

# 6. 总结和建议
print(f"\n{'=' * 60}")
print("总结和建议")
print("=" * 60)

if config.TASK_CLASSIFIER_MODE == "regex":
    print("\n当前配置：正则表达式模式（零成本，快速）")
    print("\n如果要使用 LLM 模式，请在 .env 中添加：")
    print("  TASK_CLASSIFIER_MODE=llm")
    print("\n然后重新运行程序")

elif config.TASK_CLASSIFIER_MODE == "llm":
    if has_classifier_llm:
        print("\n当前配置：LLM 模式（分类器专用配置）")
        print("✓ 分类器将使用独立的 LLM（可节省成本）")
    else:
        print("\n当前配置：LLM 模式（使用主 LLM 配置）")
        print("✓ 分类器将使用 .env 中配置的主 LLM")
        print("\n如果想节省成本，可以为分类器配置更便宜的 LLM：")
        print("  TASK_CLASSIFIER_LLM_API_KEY=sk-xxx")
        print("  TASK_CLASSIFIER_LLM_BASE_URL=https://api.deepseek.com/v1")
        print("  TASK_CLASSIFIER_LLM_MODEL=deepseek-chat")

print("\n" + "=" * 60)
