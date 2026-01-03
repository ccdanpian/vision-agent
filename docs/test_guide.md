# VisionAgent 测试指南

本文档说明如何验证 VisionAgent 的 bbox 坐标解析功能。

## 环境准备

### 1. 创建虚拟环境

**WSL / Linux / macOS:**
```bash
cd /mnt/d/work/python/ai/remote
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**
```powershell
cd D:\work\python\ai\remote
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 API

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置 OpenRouter + Gemini：

```ini
LLM_PROVIDER=custom
CUSTOM_LLM_API_KEY=sk-or-v1-你的密钥
CUSTOM_LLM_BASE_URL=https://openrouter.ai/api/v1
CUSTOM_LLM_MODEL=google/gemini-2.5-flash-preview
```

---

## 测试命令

### 测试 1: 基础功能测试（不需要 API）

```bash
python test_vision.py
```

**预期输出:**
```
==================================================
测试: _bbox_to_center 坐标转换
==================================================
模拟屏幕尺寸: 1080x2400

bbox (0-1000) → 像素坐标:
  {'xmin': 0, 'ymin': 0, 'xmax': 100, 'ymax': 100} → (54, 120)
  {'xmin': 450, 'ymin': 450, 'xmax': 550, 'ymax': 550} → (540, 1200)
  {'xmin': 900, 'ymin': 900, 'xmax': 1000, 'ymax': 1000} → (1026, 2280)

==================================================
测试: _parse_action 解析 LLM 返回
==================================================
模拟屏幕尺寸: 1080x2400

解析结果:

  输入: {"action": "tap", "xmin": 400, "ymin": 500, ...}
  解析: action=tap, x=540, y=1320, reason=点击按钮

  输入: {"action": "swipe", "xmin": 700, "ymin": 500, ...}
  解析: action=swipe, x=756, y=1200, x2=324, y2=1200, reason=左滑

  输入: {"action": "press_key", "keycode": 3, ...}
  解析: action=press_key, x=None, y=None, reason=按HOME键

  输入: {"action": "success", "reason": "任务完成"}
  解析: action=success, x=None, y=None, reason=任务完成
```

**验证点:**
- [x] bbox 坐标正确转换为像素坐标
- [x] tap 动作使用 bbox 中心点
- [x] swipe 动作的起点和终点正确解析
- [x] press_key 和 success 等无坐标动作正常解析

---

### 测试 2: 文字描述查找元素（需要 API）

准备一张手机截图（如 `screenshot.png`），然后运行：

```bash
python test_vision.py find screenshot.png "Chrome 图标"
```

**预期输出:**
```
==================================================
测试: find_element (文字描述查找)
==================================================
截图: screenshot.png
尺寸: (1080, 2400)
查找: Chrome 图标
LLM: custom/google/gemini-2.5-flash-preview

调用 API...
✓ 找到元素，中心坐标: (540, 1850)
```

**验证点:**
- [x] API 调用成功
- [x] 返回的坐标在合理范围内（0 < x < 1080, 0 < y < 2400）
- [x] 手动检查坐标是否接近目标元素位置

---

### 测试 3: 双图片匹配（需要 API）

准备两张图片：
- `icon.png` - 要查找的图标（小图，如 Chrome 图标截图）
- `screenshot.png` - 手机截图（大图）

```bash
python test_vision.py match icon.png screenshot.png
```

**预期输出:**
```
==================================================
测试: find_element_by_image (双图匹配)
==================================================
参考图: icon.png (128, 128)
截图: screenshot.png (1080, 2400)
LLM: custom/google/gemini-2.5-flash-preview

调用 API...
✓ 找到元素，中心坐标: (540, 1850)
```

**验证点:**
- [x] 双图片正确发送给 API
- [x] 返回的坐标与参考图标在截图中的位置一致

---

### 测试 4: 屏幕分析（需要 API）

```bash
python test_vision.py analyze screenshot.png "打开微信"
```

**预期输出:**
```
==================================================
测试: analyze_screen (屏幕分析)
==================================================
截图: screenshot.png
尺寸: (1080, 2400)
任务: 打开微信
LLM: custom/google/gemini-2.5-flash-preview

调用 API...

返回动作:
  类型: tap
  坐标: x=270, y=1950
  原因: 点击微信图标打开应用
```

**验证点:**
- [x] 返回正确的动作类型（tap/swipe/press_key 等）
- [x] bbox 坐标已转换为像素坐标
- [x] reason 说明合理

---

## 常见问题

### Q: API 调用失败

检查 `.env` 配置：
```bash
cat .env | grep -v "^#"
```

确认：
- API Key 正确
- Base URL 正确（OpenRouter 是 `https://openrouter.ai/api/v1`）
- 模型名称正确（如 `google/gemini-2.5-flash-preview`）

### Q: 坐标转换结果异常

bbox 格式应为 `{"xmin": 0-1000, "ymin": 0-1000, "xmax": 0-1000, "ymax": 0-1000}`

转换公式：
```
x = (xmin + xmax) / 2 / 1000 * 图片宽度
y = (ymin + ymax) / 2 / 1000 * 图片高度
```

### Q: 找不到元素

可能原因：
1. 元素描述不够准确，尝试更具体的描述
2. 元素在截图中不可见
3. LLM 模型能力限制

---

## 测试检查清单

| 测试项 | 命令 | 状态 |
|--------|------|------|
| 坐标转换 | `python test_vision.py` | [ ] |
| JSON 解析 | `python test_vision.py` | [ ] |
| find_element | `python test_vision.py find ...` | [ ] |
| find_element_by_image | `python test_vision.py match ...` | [ ] |
| analyze_screen | `python test_vision.py analyze ...` | [ ] |

全部通过后，VisionAgent 的 bbox 功能验证完成。
