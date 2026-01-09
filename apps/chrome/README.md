# Chrome 频道工作流实现

本文档描述 Chrome 浏览器频道的工作流架构，该实现参照微信频道的设计模式。

## 文件结构

```
apps/chrome/
├── handler.py           # 任务分类与执行入口
├── workflows.py         # 屏幕定义与工作流定义
├── workflow_executor.py # 工作流执行器
├── config.yaml          # Chrome 配置
├── tasks.yaml           # 任务配置
├── prompts/
│   └── planner.txt      # LLM 规划提示词
└── images/              # OpenCV 模板图片
```

## 架构概述

### 执行流程

```
用户输入 → 频道检测(%) → SS快速模式检测 → 分类执行
                              ↓
                    ┌─────────┴─────────┐
                    ↓                   ↓
               SS模式命中           LLM分类
                    ↓                   ↓
               正则解析            类型识别
                    ↓                   ↓
               本地工作流    →    本地工作流
                    ↓                   ↓
               失败重试(3次)       失败重试(3次)
                    ↓                   ↓
               LLM重分配           LLM重分配
                    ↓                   ↓
               本地重试            本地重试
                    ↓                   ↓
               LLM完全规划         LLM完全规划
```

## 核心模块

### 1. handler.py - 任务处理器

**主要类：** `Handler`（继承自 `DefaultHandler`）

**核心方法：**

- `execute_task_with_workflow(task, parsed_data)` - 主入口，执行完整的分类→执行→回退流程
- `_is_chrome_ss_mode(task)` - 检测 Chrome SS 快速模式
- `_parse_chrome_ss_mode(task)` - 解析 SS 模式指令
- `select_workflow_with_llm(task)` - 使用 LLM 选择合适的工作流

**SS 快速模式格式：**

```
# URL 打开
baidu.com           → open_url_local
https://google.com  → open_url_local

# 搜索
sou 关键词          → search_web_local
s 关键词            → search_web_local
搜 关键词           → search_web_local

# 快捷操作
刷新 / refresh      → refresh
新标签 / newtab     → new_tab
书签 / bookmarks    → view_bookmarks
历史 / history      → view_history
下载 / downloads    → view_downloads
关闭 / close        → close_tab
```

### 2. workflows.py - 工作流定义

**屏幕状态枚举：** `ChromeScreen`

```python
class ChromeScreen(Enum):
    UNKNOWN = "unknown"
    HOME = "home"              # Chrome 首页/新标签页
    ADDRESS_BAR = "address_bar" # 地址栏已激活
    WEB_PAGE = "web_page"      # 普通网页
    SEARCH_RESULTS = "search_results"  # 搜索结果页
    SETTINGS = "settings"      # 设置页面
    BOOKMARKS = "bookmarks"    # 书签页面
    HISTORY = "history"        # 历史记录
    DOWNLOADS = "downloads"    # 下载页面
```

**预定义工作流（12个）：**

| 工作流名称 | 功能 | 需要参数 |
|-----------|------|----------|
| `open_url` | 打开指定 URL（LLM规划） | url |
| `open_url_local` | 打开指定 URL（本地执行） | url |
| `search_web` | 搜索关键词（LLM规划） | keyword |
| `search_web_local` | 搜索关键词（本地执行） | keyword |
| `open_baidu` | 打开百度首页（LLM规划） | - |
| `open_baidu_local` | 打开百度首页（本地执行） | - |
| `new_tab` | 新建标签页 | - |
| `refresh` | 刷新当前页面 | - |
| `view_bookmarks` | 查看书签 | - |
| `view_history` | 查看历史记录 | - |
| `view_downloads` | 查看下载 | - |
| `close_tab` | 关闭当前标签页 | - |

### 3. workflow_executor.py - 执行器

**主要类：** `WorkflowExecutor`

**核心功能：**

1. **预置流程（Preset）**
   - `_ensure_chrome_running()` - 确保 Chrome 应用已启动
   - `_ensure_at_usable_screen()` - 确保处于可操作屏幕

2. **复位流程（Reset）**
   - `navigate_to_home()` - 导航回首页（点击 Home 按钮或地址栏输入 chrome://newtab）

3. **屏幕检测**
   - `detect_screen()` - 使用 OpenCV 模板匹配检测当前屏幕状态

4. **工作流执行**
   - `execute_workflow(workflow_name, params, local_only)` - 执行指定工作流
   - 支持 `local_only=True` 模式，仅使用本地 OpenCV 匹配，不调用 LLM

**动作类型：**

- `tap` - 点击坐标或模板
- `long_press` - 长按
- `input_text` - 输入文本
- `input_url` - 输入 URL（自动处理协议前缀）
- `swipe` - 滑动
- `wait` - 等待
- `keyevent` - 发送按键事件

## 任务分类器更新

`ai/task_classifier.py` 已更新支持 Chrome 类型：

```python
# Chrome 简单任务类型
"open_url"        # 打开指定网址
"search_web"      # 搜索关键词
"open_baidu"      # 打开百度
"new_tab"         # 新建标签页
"refresh"         # 刷新页面
"view_bookmarks"  # 查看书签
"view_history"    # 查看历史
"view_downloads"  # 查看下载
"close_tab"       # 关闭标签页
```

## 使用示例

### 通过频道前缀调用

```
%baidu.com              # 打开百度网站
%s python教程           # 搜索"python教程"
%刷新                   # 刷新当前页面
%书签                   # 打开书签页面
```

### 自然语言调用

```
%打开百度               # LLM 识别为 open_baidu
%搜索今日新闻           # LLM 识别为 search_web
%打开 github.com        # LLM 识别为 open_url
```

## 失败处理机制

1. **本地执行失败（最多3次）** → 触发 LLM 重新分配工作流
2. **LLM 重分配后本地执行失败** → 触发 LLM 完全规划模式
3. **LLM 规划执行失败** → 返回错误给用户

## 依赖的模板图片

工作流执行依赖以下 OpenCV 模板图片（位于 `images/` 目录）：

- `chrome_home_page.png` - 首页识别
- `chrome_address_bar.png` - 地址栏识别
- `chrome_home_button.png` - Home 按钮
- `chrome_search_box.png` - 搜索框
- `chrome_baidu_home_page.png` - 百度首页
- `chrome_baidu_search_input.png` - 百度搜索框

## 扩展指南

### 添加新工作流

1. 在 `workflows.py` 的 `WORKFLOWS` 字典中添加新工作流定义
2. 如需新屏幕状态，在 `ChromeScreen` 枚举中添加
3. 在 `handler.py` 的 `TYPE_TO_WORKFLOW` 中添加类型映射
4. 如需 SS 快速模式支持，更新 `SIMPLE_TASK_PATTERNS`

### 添加新模板图片

1. 将模板图片放入 `images/` 目录
2. 在 `images/aliases.yaml` 中添加别名映射（如需要）
3. 在工作流定义中使用模板名称
