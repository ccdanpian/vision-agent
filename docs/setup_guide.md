# VisionAgent 配置与运行指南

## 目录

1. [系统架构说明](#系统架构说明)
2. [电脑端环境配置](#电脑端环境配置)
3. [手机端配置（小米/MIUI）](#手机端配置小米miui)
4. [连接手机](#连接手机)
5. [使用模拟器测试](#使用模拟器测试)
6. [中文输入支持](#中文输入支持)
7. [运行项目](#运行项目)
8. [远程访问配置](#远程访问配置)
9. [常见问题](#常见问题)

---

## 系统架构说明

### 核心概念

**VisionAgent 程序完全在电脑上运行，手机上不需要安装或运行任何程序。**

```
┌─────────────────────────────────────────────────────────────┐
│                      电脑（运行端）                          │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Python 环境 + VisionAgent 程序                         │ │
│  │                                                         │ │
│  │  1. 通过 ADB 发送截图命令给手机                         │ │
│  │  2. 通过 ADB 把截图传回电脑                             │ │
│  │  3. 调用 LLM API 分析截图，识别 UI 元素位置             │ │
│  │  4. 通过 ADB 发送点击/滑动/输入命令给手机               │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              │ ADB 协议（USB 数据线 或 WiFi）
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      手机（被控端）                          │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  只需要：                                               │ │
│  │    ✓ 开启 USB 调试                                      │ │
│  │    ✓ 开启 USB 调试（安全设置）← 小米手机必须            │ │
│  │    ✓ 安装 ADBKeyboard（可选，用于中文输入）             │ │
│  │                                                         │ │
│  │  不需要：                                               │ │
│  │    ✗ 安装任何程序                                       │ │
│  │    ✗ 运行任何服务                                       │ │
│  │    ✗ Python 或其他运行环境                              │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 工作流程

```
电脑                                    手机
  │                                       │
  │──── adb shell screencap ─────────────►│ 执行截图
  │◄─── adb pull screenshot.png ──────────│ 传回截图
  │                                       │
  │──── 调用 LLM API 分析截图 ────►        │
  │◄─── 返回元素坐标 (x, y) ──────         │
  │                                       │
  │──── adb shell input tap x y ─────────►│ 执行点击
  │                                       │
```

### 系统要求

| 组件 | 要求 |
|------|------|
| 电脑系统 | Windows 10/11、macOS、Linux |
| Python | 3.8 或更高版本 |
| 手机系统 | Android 7.0+（推荐 Android 11+ 支持无线调试）|
| 连接方式 | USB 数据线 或 同一局域网 WiFi |

---

## 电脑端环境配置

### 1. 安装 ADB

ADB (Android Debug Bridge) 是电脑与手机通信的工具。

#### Windows

**方法 1：使用 Android Studio（推荐）**

如果已安装 Android Studio，ADB 已经包含在内：
```
路径：C:\Users\<用户名>\AppData\Local\Android\Sdk\platform-tools\adb.exe
```

将此路径添加到系统 PATH，或直接使用完整路径。

**方法 2：单独下载 Platform Tools**

1. 下载 [Platform Tools](https://developer.android.com/studio/releases/platform-tools)
2. 解压到 `C:\platform-tools`
3. 添加到系统 PATH：
   - 右键「此电脑」→ 属性 → 高级系统设置
   - 环境变量 → 系统变量 → Path → 编辑
   - 新建 → 输入 `C:\platform-tools`
   - 确定保存

**验证安装：**
```powershell
adb version
# Android Debug Bridge version 1.0.41
```

#### macOS

```bash
brew install android-platform-tools
adb version
```

#### Linux

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install adb

# Fedora
sudo dnf install android-tools

# Arch
sudo pacman -S android-tools

adb version
```

#### WSL (Windows Subsystem for Linux)

**WSL 无法直接访问 Windows 的 USB 设备和模拟器**，需要使用 Windows 的 ADB：

```bash
# 在 ~/.bashrc 中添加别名（替换 <用户名> 为你的 Windows 用户名）
echo 'alias adb="/mnt/c/Users/<用户名>/AppData/Local/Android/Sdk/platform-tools/adb.exe"' >> ~/.bashrc
source ~/.bashrc

# 验证
adb devices
```

如果 Android Studio 不在默认位置，先在 Windows 中找到 adb.exe 的实际路径。

---

### 2. 安装 Python 依赖

```bash
# 克隆项目
git clone <repository-url>
cd remote

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows PowerShell
.\venv\Scripts\Activate.ps1
# Windows CMD
venv\Scripts\activate.bat
# Linux/macOS/WSL
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

---

### 3. 配置 LLM API

复制环境变量模板：
```bash
cp .env.example .env
```

编辑 `.env` 文件：
```bash
# 推荐：OpenRouter + Gemini（支持双图匹配，效果好）
LLM_PROVIDER=custom
CUSTOM_LLM_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx
CUSTOM_LLM_BASE_URL=https://openrouter.ai/api/v1
CUSTOM_LLM_MODEL=google/gemini-2.5-flash-preview

# 或使用 OpenAI
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
# OPENAI_MODEL=gpt-4o

# 通用设置
LLM_MAX_TOKENS=1024
LLM_TEMPERATURE=0.0
LLM_TIMEOUT=60
OPERATION_DELAY=0.5

# ============================================================
# 应用截图等待时间配置（秒）
# ============================================================
# 不同应用的页面加载速度不同，需要等待足够时间才能截取到完整画面
# 如果截图时页面尚未加载完成，会导致 AI 定位失败

# 默认截图等待时间
SCREENSHOT_WAIT_DEFAULT=0.3

# 微信（原生应用，加载快）
SCREENSHOT_WAIT_WECHAT=0.3

# Chrome 浏览器（网页加载慢，建议至少 1 秒）
SCREENSHOT_WAIT_CHROME=1.0

# 系统应用
SCREENSHOT_WAIT_SYSTEM=0.3
```

**重要提示**：
- 浏览器等需要网络加载的应用，等待时间应设置为 1 秒或更长
- 原生应用（微信、系统设置）通常 0.3 秒即可
- 如果发现 AI 定位经常失败，尝试增加对应应用的等待时间

---

## 手机端配置（小米/MIUI）

**手机上不需要安装任何程序**，只需开启调试选项。

### 第一步：开启开发者选项

开发者选项默认隐藏，需要激活：

```
设置 → 我的设备 → 全部参数与信息 → 连续点击「MIUI版本」7 次
```

系统会提示「您已处于开发者模式」。

**开发者选项位置**：
```
设置 → 更多设置 → 开发者选项
```

---

### 第二步：开启 USB 调试

进入「开发者选项」，开启以下设置：

| 选项 | 必须 | 说明 |
|------|------|------|
| **USB 调试** | ✓ 必须 | 允许电脑通过 ADB 控制手机 |
| **USB 调试（安全设置）** | ✓ 必须 | 允许模拟点击和输入，小米特有 |

#### 开启「USB 调试（安全设置）」

这是小米/MIUI 的特殊安全设置，**必须开启**，否则无法模拟点击：

1. 点击「USB 调试（安全设置）」
2. 系统提示需要登录小米账号
3. 登录后，需满足以下条件之一：
   - 手机已插入 SIM 卡并联网 → 可立即开启
   - 无 SIM 卡 → 需等待约 24 小时审核

**如果无法开启**：
- 确保已登录小米账号
- 确保手机已插入 SIM 卡
- 确保手机已联网

---

### 第三步：开启无线调试（可选，Android 11+）

如果不想用 USB 线，可以开启无线调试：

```
开发者选项 → 无线调试 → 开启
```

首次需要配对，见后文「WiFi 无线连接」部分。

---

## 连接手机

### 方式一：USB 有线连接（推荐新手）

1. **用数据线连接手机和电脑**
   - 使用原装或质量好的数据线（避免仅充电线）

2. **授权连接**
   - 手机弹出「允许 USB 调试吗？」
   - 勾选「始终允许使用这台计算机进行调试」
   - 点击「允许」

3. **验证连接**
   ```bash
   adb devices
   ```

   正常输出：
   ```
   List of devices attached
   abc123def456    device
   ```

| 状态 | 含义 | 解决方法 |
|------|------|----------|
| `device` | 正常连接 | - |
| `unauthorized` | 未授权 | 在手机上点击「允许」 |
| `offline` | 连接异常 | 重新插拔，或 `adb kill-server && adb devices` |
| 无显示 | 驱动问题 | 安装小米驱动或换数据线 |

---

### 方式二：WiFi 无线连接

#### Android 11+ （无线调试，推荐）

不需要 USB 线，直接无线配对：

1. **手机开启无线调试**（见上文）

2. **获取配对信息**
   ```
   无线调试 → 使用配对码配对设备
   ```
   记下显示的：
   - 配对码（6位数字）
   - IP 地址和端口（如 `192.168.1.100:37215`）

3. **电脑上配对**
   ```bash
   adb pair 192.168.1.100:37215
   # 输入配对码：123456
   ```

4. **配对成功后，连接**
   ```
   返回「无线调试」主界面，记下「IP 地址和端口」（如 192.168.1.100:41235）
   注意：连接端口和配对端口不同！
   ```
   ```bash
   adb connect 192.168.1.100:41235
   ```

5. **验证**
   ```bash
   adb devices
   # 192.168.1.100:41235    device
   ```

#### Android 7-10（需先 USB 连接一次）

```bash
# 1. 先用 USB 连接
adb devices

# 2. 开启 TCP/IP 模式
adb tcpip 5555

# 3. 获取手机 IP
adb shell ip addr show wlan0 | grep "inet "
# 或在手机上查看：设置 → WLAN → 点击当前网络 → IP地址

# 4. 断开 USB，WiFi 连接
adb connect 192.168.1.100:5555

# 5. 验证
adb devices
```

---

## 使用模拟器测试

Android Studio 模拟器非常适合开发测试，不需要真实手机。

### 创建模拟器

```
Android Studio → Tools → Device Manager → Create Device
```

**推荐配置**：

| 设置 | 推荐值 |
|------|--------|
| 设备 | Pixel 6 或类似 |
| System Image | 选择 **Google APIs**（不要选 Google Play） |
| API Level | 30+ (Android 11+) |
| ABI | x86_64（速度快） |

**为什么选 Google APIs 而不是 Google Play**：
- Google APIs：可以 `adb root`，调试更方便
- Google Play：有应用商店，但无法 root

### 启动并连接

启动模拟器后，自动连接 ADB：

```bash
adb devices
# emulator-5554    device
```

### 模拟器联网问题

如果模拟器显示无网络：

**方法 1：冷启动**
```
Device Manager → 模拟器右边 ▼ → Cold Boot Now
```

**方法 2：检查代理**

如果电脑开了代理（VPN/Clash 等），可能影响模拟器。尝试关闭代理。

**方法 3：手动设置 DNS**
```bash
adb root
adb shell "echo 'nameserver 8.8.8.8' > /etc/resolv.conf"
```

### WSL 连接模拟器

WSL 必须使用 Windows 的 ADB：

```bash
# 确保已配置别名（见上文 WSL 部分）
adb devices
# emulator-5554    device
```

### 模拟器 vs 真机

| 对比 | 模拟器 | 真机 |
|------|--------|------|
| 方便性 | ✓ 无需手机 | 需要手机+数据线 |
| 速度 | 较慢 | ✓ 快 |
| 微信等应用 | ✗ 可能无法登录 | ✓ 正常 |
| 适合场景 | 开发调试、测试基础功能 | 完整流程测试 |

---

## 中文输入支持

ADB 原生只支持 ASCII 字符，中文输入需要安装 ADBKeyboard。

### 安装

```bash
# 下载
# https://github.com/nicholasngai/ADBKeyboard/releases

# 安装到手机/模拟器
adb install ADBKeyboard.apk
```

### 配置为默认输入法

```bash
# 启用
adb shell ime enable com.android.adbkeyboard/.AdbIME

# 设为默认
adb shell ime set com.android.adbkeyboard/.AdbIME

# 验证
adb shell ime list -s
# 显示 com.android.adbkeyboard/.AdbIME
```

### 测试中文输入

```bash
# 先点击一个输入框，然后：
adb shell am broadcast -a ADB_INPUT_TEXT --es msg "你好世界"
```

### 恢复原输入法

```bash
# 查看所有输入法
adb shell ime list -s

# 切换回搜狗/百度等
adb shell ime set com.sohu.inputmethod.sogou/.SogouIME
adb shell ime set com.baidu.input/.ImeService
```

---

## 运行项目

### 基础测试（不需要 API）

```bash
# 激活虚拟环境
source venv/bin/activate  # Linux/macOS/WSL
# 或
.\venv\Scripts\Activate.ps1  # Windows PowerShell

# 运行基础测试
python test_planner.py
```

这会测试 AssetsManager（参考图库管理），不需要 API 和手机连接。

### 测试各模块（需要 API 和截图）

```bash
# 先获取一张截图
adb shell screencap -p /sdcard/screen.png
adb pull /sdcard/screen.png ./screen.png

# 测试任务规划
python test_planner.py plan screen.png "打开设置"

# 测试元素定位（使用参考图匹配）
python test_planner.py locate screen.png "微信"

# 测试双图匹配
python test_planner.py match assets/icons/wechat.png screen.png

# 测试状态验证
python test_planner.py verify screen.png "微信主界面"

# 完整流程测试（规划 + 定位）
python test_planner.py flow screen.png "打开微信"
```

### 运行完整任务

```python
# run_task.py
from core import TaskRunner, ADBController

# 连接手机（替换为你的设备地址）
# USB 连接用序列号，WiFi 连接用 IP:端口
adb = ADBController('192.168.1.100:5555')

if not adb.connect():
    print("连接失败！")
    exit(1)

print(f"已连接，屏幕尺寸: {adb.get_screen_size()}")

# 创建任务执行器
runner = TaskRunner(adb)

# 执行任务
result = runner.run("打开微信，给张三发消息说你好")

# 查看结果
print(f"状态: {result.status}")
print(f"耗时: {result.total_time:.1f}s")
```

```bash
python run_task.py
```

---

## 远程访问配置

如果手机和电脑不在同一网络，需要配置远程访问。

### 方案一：Tailscale（推荐，最简单）

Tailscale 提供自动组网，无需公网服务器。

1. 在电脑和手机所在网络的一台设备上安装 Tailscale
2. 登录同一 Tailscale 账号
3. 获取 Tailscale 分配的 IP
4. 连接：
   ```bash
   adb connect 100.x.x.x:5555
   ```

### 方案二：FRP 内网穿透

需要一台公网服务器。

**服务端（公网服务器）**：
```ini
# frps.ini
[common]
bind_port = 7000
```

**客户端（手机所在网络的电脑）**：
```ini
# frpc.ini
[common]
server_addr = your-server.com
server_port = 7000

[adb]
type = tcp
local_ip = 192.168.1.100  # 手机局域网 IP
local_port = 5555
remote_port = 5555
```

**远程连接**：
```bash
adb connect your-server.com:5555
```

### 方案三：SSH 端口转发

```bash
# 在远程电脑上
ssh -L 5555:192.168.1.100:5555 user@jump-server

# 连接本地转发端口
adb connect 127.0.0.1:5555
```

---

## 常见问题

### Q1: `adb devices` 显示 `unauthorized`

手机未授权此电脑。

**解决**：
1. 查看手机屏幕，应有授权弹窗
2. 勾选「始终允许」并点击「允许」
3. 如果没有弹窗：
   ```bash
   adb kill-server
   adb devices
   ```

### Q2: 点击没有反应

**解决**：
1. 确认已开启「USB 调试（安全设置）」（小米手机必须）
2. 测试手动点击：
   ```bash
   adb shell wm size  # 获取屏幕尺寸
   adb shell input tap 540 1200  # 点击屏幕中心
   ```

### Q3: WSL 中 `adb devices` 为空

WSL 无法直接访问 Windows 设备。

**解决**：使用 Windows 的 ADB（见上文 WSL 部分）。

### Q4: 模拟器无网络

**解决**：
1. 冷启动模拟器
2. 关闭电脑代理软件
3. 手动设置 DNS

### Q5: 中文输入失败

**解决**：
1. 确认 ADBKeyboard 已安装并设为默认
2. 测试：
   ```bash
   adb shell am broadcast -a ADB_INPUT_TEXT --es msg "测试"
   ```

### Q6: LLM API 调用失败

**解决**：
1. 检查 `.env` 配置
2. 验证 API Key：
   ```bash
   curl https://openrouter.ai/api/v1/models \
     -H "Authorization: Bearer sk-or-v1-xxx"
   ```

---

## ADB 常用命令速查

```bash
# 设备管理
adb devices                    # 列出设备
adb connect <ip>:<port>        # 连接设备
adb disconnect                 # 断开所有
adb kill-server                # 重启 ADB 服务

# 截图
adb shell screencap -p /sdcard/screen.png
adb pull /sdcard/screen.png ./

# 操作
adb shell input tap <x> <y>                      # 点击
adb shell input swipe <x1> <y1> <x2> <y2> <ms>   # 滑动
adb shell input text "hello"                     # 输入英文
adb shell input keyevent 3                       # HOME 键
adb shell input keyevent 4                       # 返回键

# 应用
adb install app.apk                              # 安装应用
adb shell pm list packages                       # 列出所有包名
adb shell am start -n com.example/.MainActivity  # 启动应用

# 系统信息
adb shell wm size              # 屏幕尺寸
adb shell getprop ro.product.model  # 设备型号
```
