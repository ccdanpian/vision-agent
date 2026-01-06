# 调试模式使用指南

## 概述

调试模式允许在**没有真实手机连接**的情况下测试和运行 VisionAgent，使用模拟的设备和操作响应。

---

## 适用场景

### 1. 开发测试

- ✅ 测试代码逻辑
- ✅ 验证工作流程
- ✅ 调试任务分类器
- ✅ 测试错误处理

### 2. 演示展示

- ✅ 产品演示
- ✅ 功能展示
- ✅ 培训教学

### 3. CI/CD 环境

- ✅ 自动化测试
- ✅ 集成测试
- ✅ 持续集成流水线

### 4. 无设备环境

- ✅ 没有 Android 设备
- ✅ 没有 ADB 环境
- ✅ 快速验证想法

---

## 启用调试模式

### 方法 1：修改 .env 文件

```bash
# .env
DEBUG_MODE=true

# 可选：自定义模拟设备信息
DEBUG_DEVICE_NAME=我的测试设备
DEBUG_SCREEN_WIDTH=1080
DEBUG_SCREEN_HEIGHT=2340
```

### 方法 2：临时启用（环境变量）

```bash
# Linux/macOS
export DEBUG_MODE=true
python run.py -i

# Windows
set DEBUG_MODE=true
python run.py -i
```

---

## 使用示例

### 示例 1：交互式模式

```bash
$ python run.py -i

==================================================
           交互式任务模式
==================================================

⚠️  调试模式已启用（无需真实设备）
设备: 模拟设备 (模拟)
[MockADB] 初始化模拟设备: 模拟设备
[MockADB] 屏幕尺寸: 1080x2340
[MockADB] 连接到模拟设备: mock:5555
已连接，屏幕尺寸: (1080, 2340)

==================================================
           选择任务分类模式
==================================================

请选择任务输入模式：
  1. 快速模式（固定格式，零成本，极速响应）
  2. 智能模式（自然语言，AI理解）

请输入选项（1 或 2）: 1

（选择模式后正常使用）

--------------------------------------------------
请输入任务（快速格式）: 消息:张三:你好

[MockADB] 点击: (500, 1000)
[MockADB] 输入文本: 张三
[MockADB] 点击: (800, 1500)
[MockADB] 输入中文: 你好
[MockADB] 点击: (900, 2000)

（任务执行完成）
```

### 示例 2：单任务模式

```bash
$ python run.py -t "ss:消息:张三:你好"

⚠️  调试模式已启用（无需真实设备）
设备: 模拟设备 (模拟)
任务: ss:消息:张三:你好
----------------------------------------
[MockADB] 初始化模拟设备: 模拟设备
[MockADB] 屏幕尺寸: 1080x2340
[MockADB] 连接到模拟设备: mock:5555
已连接，屏幕尺寸: (1080, 2340)

开始执行任务: ss:消息:张三:你好
[TaskClassifier] 检测到 SS 快速模式
[TaskClassifier] SS解析成功
...（执行流程）

========================================
执行结果
========================================
状态: success
耗时: 2.3s
```

---

## 调试模式特性

### 1. 模拟设备连接

```python
[MockADB] 初始化模拟设备: 模拟设备
[MockADB] 屏幕尺寸: 1080x2340
[MockADB] 连接到模拟设备: mock:5555
```

**特点**：
- ✅ 自动成功连接
- ✅ 无延迟
- ✅ 可配置设备信息

### 2. 模拟操作输出

```python
[MockADB] 点击: (500, 1000)
[MockADB] 滑动: (100, 500) -> (900, 500), 持续 300ms
[MockADB] 输入文本: 你好
[MockADB] 按 HOME 键
[MockADB] 启动应用: com.tencent.mm
```

**特点**：
- ✅ 所有操作都有日志输出
- ✅ 模拟真实操作延迟
- ✅ 方便调试和验证

### 3. 模拟截图

```python
[MockADB] 生成模拟截图: temp/screenshot_001.png
```

**生成的截图包含**：
- 设备名称
- 屏幕尺寸
- 时间戳
- 标题："Mock Screenshot"

**示例截图**：
```
┌────────────────────────────────┐
│                                │
│                                │
│        Mock Screenshot         │
│                                │
│    Device: 模拟设备             │
│    Size: 1080x2340             │
│                                │
│    2026-01-06 15:30:45         │
│                                │
│                                │
└────────────────────────────────┘
```

### 4. 模拟应用状态

```python
[MockADB] 启动应用: com.tencent.mm/.ui.LauncherUI
[MockADB] 停止应用: com.tencent.mm
```

**支持的操作**：
- 启动应用
- 停止应用
- 获取当前应用
- 检查应用安装状态

---

## 配置选项

### .env 配置项

```bash
# ============================================================
# 调试模式配置
# ============================================================
# 调试模式：无需真实手机连接，使用模拟数据
# - true: 启用调试模式（模拟设备和操作，不需要真实手机）
# - false: 正常模式（需要连接真实设备）
DEBUG_MODE=false

# 调试模式下的模拟设备信息（仅当 DEBUG_MODE=true 时生效）
DEBUG_DEVICE_NAME=模拟设备
DEBUG_SCREEN_WIDTH=1080
DEBUG_SCREEN_HEIGHT=2340
```

### 自定义设备配置

```bash
# 自定义设备名称
DEBUG_DEVICE_NAME=我的测试机

# 自定义屏幕尺寸（模拟不同设备）
# 示例：模拟小屏幕设备
DEBUG_SCREEN_WIDTH=720
DEBUG_SCREEN_HEIGHT=1280

# 示例：模拟大屏幕设备
DEBUG_SCREEN_WIDTH=1440
DEBUG_SCREEN_HEIGHT=3040
```

---

## 调试模式 vs 正常模式

| 特性 | 调试模式 | 正常模式 |
|------|---------|---------|
| **设备连接** | 模拟，自动成功 | 真实设备，需要 ADB |
| **操作执行** | 模拟输出，无实际操作 | 真实操作设备 |
| **截图** | 生成模拟图片 | 真实设备截图 |
| **响应速度** | 快速（无网络/设备延迟） | 取决于设备和网络 |
| **适用场景** | 开发、测试、演示 | 实际使用、生产环境 |
| **依赖** | 无需 ADB、设备 | 需要 ADB 和设备 |
| **成本** | 零成本 | 需要硬件设备 |

---

## 支持的功能

### ✅ 完全支持

- 设备连接/断开
- 点击、滑动、长按
- 文本输入（包括中文）
- 按键事件（HOME、BACK、ENTER）
- 截图生成
- 应用启动/停止
- 拨号/打电话
- 输入法切换
- 屏幕唤醒/解锁

### ⚠️ 部分支持

- **图像识别**：无法识别真实界面元素
- **OCR 文字识别**：无法识别真实文字
- **应用实际响应**：只是模拟日志

### ❌ 不支持

- 真实设备操作
- 真实应用交互
- 真实界面反馈

---

## 调试技巧

### 1. 验证任务分类

```bash
# 启用调试模式
export DEBUG_MODE=true

# 测试任务分类器
python test_task_classifier.py

# 测试 SS 模式解析
python test_ss_mode.py
```

**优势**：
- 无需设备即可测试分类逻辑
- 快速验证正则表达式
- 测试 LLM 解析准确性

### 2. 测试工作流逻辑

```bash
# 启用调试模式
export DEBUG_MODE=true

# 测试工作流
python run.py -t "ss:消息:张三:你好"
```

**查看输出**：
```
[MockADB] 点击: (500, 1000)      ← 确认工作流步骤
[MockADB] 输入文本: 张三          ← 确认参数传递
[MockADB] 输入中文: 你好          ← 确认操作顺序
```

### 3. 演示和培训

```bash
# 启用调试模式
DEBUG_MODE=true python run.py -i

# 演示完整流程
1. 选择模式
2. 输入任务
3. 观察模拟操作日志
4. 查看生成的模拟截图
```

### 4. CI/CD 集成

```yaml
# .github/workflows/test.yml
- name: Run tests in debug mode
  env:
    DEBUG_MODE: true
  run: |
    python test_task_classifier.py
    python test_interactive_invalid.py
```

---

## 实现细节

### MockADBController 类

**位置**：`core/mock_adb_controller.py`

**核心方法**：
```python
class MockADBController:
    def __init__(self, device_address: str = "mock:5555"):
        """初始化模拟设备"""

    def connect(self) -> bool:
        """模拟连接"""

    def tap(self, x: int, y: int) -> bool:
        """模拟点击"""

    def screenshot(self, local_path: str) -> bool:
        """生成模拟截图"""

    # ... 其他方法
```

**特点**：
- 与 ADBController 完全兼容
- 所有方法返回成功
- 输出详细的操作日志
- 生成可视化的模拟截图

### 自动检测和切换

**代码实现**（run.py）：
```python
import config

if config.DEBUG_MODE:
    print(f"\n⚠️  调试模式已启用（无需真实设备）")
    from core.mock_adb_controller import MockADBController
    adb = MockADBController(device)
else:
    from core import ADBController
    adb = ADBController(device)
```

**特点**：
- 运行时自动检测
- 无需修改业务代码
- 透明切换

---

## 常见问题

### Q1: 调试模式下可以测试所有功能吗？

**A**: 可以测试**代码逻辑**和**流程控制**，但不能测试**真实设备交互**。

**可以测试**：
- 任务分类
- 工作流选择
- 参数解析
- 错误处理
- 流程控制

**不能测试**：
- 图像识别准确性
- OCR 识别效果
- 真实应用响应
- 实际操作结果

### Q2: 调试模式下的截图有什么用？

**A**: 模拟截图用于：
- 验证截图功能是否被正确调用
- 检查文件路径是否正确
- 确认截图时间点
- 测试截图保存逻辑

### Q3: 可以混用调试模式和真实设备吗？

**A**: 不能。调试模式是全局设置，要么全部使用模拟设备，要么全部使用真实设备。

### Q4: 如何在调试模式下模拟不同屏幕尺寸？

**A**: 修改 .env 配置：
```bash
# 模拟小屏幕设备
DEBUG_SCREEN_WIDTH=720
DEBUG_SCREEN_HEIGHT=1280

# 模拟大屏幕设备
DEBUG_SCREEN_WIDTH=1440
DEBUG_SCREEN_HEIGHT=3040
```

### Q5: 调试模式会影响性能吗？

**A**: 不会。调试模式下的操作更快，因为：
- 无网络延迟
- 无设备通信延迟
- 只输出日志

---

## 最佳实践

### 1. 开发阶段

```bash
# 启用调试模式
DEBUG_MODE=true

# 快速迭代测试
python run.py -t "测试任务"
```

**优势**：
- 快速验证代码
- 无需设备
- 专注逻辑开发

### 2. 提交前测试

```bash
# 在调试模式下运行所有测试
DEBUG_MODE=true python -m pytest tests/

# 确保测试通过
```

### 3. 真实设备验证

```bash
# 关闭调试模式
DEBUG_MODE=false

# 在真实设备上测试
python run.py -t "真实任务"
```

**流程**：
1. 调试模式开发和测试
2. 真实设备验证
3. 调试模式回归测试

### 4. 文档和演示

```bash
# 启用调试模式
DEBUG_MODE=true

# 录制操作过程
python run.py -i

# 查看模拟操作日志
# 展示模拟截图
```

---

## 切换模式

### 临时启用调试模式

```bash
# 单次命令
DEBUG_MODE=true python run.py -i

# 当前会话
export DEBUG_MODE=true
python run.py -i
python run.py -t "任务"
```

### 临时禁用调试模式

```bash
# 单次命令
DEBUG_MODE=false python run.py -i

# 当前会话
export DEBUG_MODE=false
python run.py -i
```

### 永久设置

编辑 `.env` 文件：
```bash
# 启用
DEBUG_MODE=true

# 禁用
DEBUG_MODE=false
```

---

## 总结

### 核心价值

| 价值 | 说明 |
|------|------|
| **降低门槛** | 无需设备即可开发和测试 |
| **提升效率** | 快速验证代码逻辑 |
| **方便演示** | 随时随地展示功能 |
| **支持 CI/CD** | 自动化测试环境 |

### 使用场景

| 场景 | 调试模式 | 真实模式 |
|------|---------|---------|
| **代码开发** | ✅ 推荐 | ❌ 不需要 |
| **逻辑测试** | ✅ 推荐 | ⚠️ 可选 |
| **功能演示** | ✅ 推荐 | ⚠️ 可选 |
| **真实验证** | ❌ 不行 | ✅ 必须 |
| **生产使用** | ❌ 不行 | ✅ 必须 |
| **CI/CD** | ✅ 推荐 | ⚠️ 复杂 |

### 快速开始

```bash
# 1. 编辑 .env
DEBUG_MODE=true

# 2. 运行程序
python run.py -i

# 3. 正常使用，无需设备

# 4. 查看操作日志
[MockADB] ...
```

开始使用调试模式，无需设备即可开发和测试！
