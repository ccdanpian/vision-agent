# Florence-2 小模型安装指南 (Windows)

## 概述

Florence-2 是微软开源的轻量级视觉模型，用于快速元素定位。在 CPU 上运行速度约 1-3 秒，GPU 上约 200-500ms。

## 安装步骤

### 1. 激活虚拟环境

```powershell
cd D:\work\python\ai\remote
.\venv\Scripts\activate
```

### 2. 安装 PyTorch (CPU 版本)

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

如果有 NVIDIA GPU，使用 CUDA 版本（更快）：

```powershell
# CUDA 11.8
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# 或 CUDA 12.1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

### 3. 安装 Transformers 和依赖

```powershell
pip install transformers einops timm
```

### 4. 预下载模型（可选但推荐）

首次运行时会自动下载模型（约 500MB），可以提前下载避免超时：

```powershell
python -c "from transformers import AutoProcessor, AutoModelForCausalLM; AutoProcessor.from_pretrained('microsoft/Florence-2-base', trust_remote_code=True); AutoModelForCausalLM.from_pretrained('microsoft/Florence-2-base', trust_remote_code=True)"
```

模型会缓存到 `C:\Users\<用户名>\.cache\huggingface\`

### 5. 验证安装

```powershell
python scripts/test_florence2.py
```

## 测试脚本用法

```powershell
# 基本测试
python scripts/test_florence2.py

# 使用指定图片测试
python scripts/test_florence2.py temp/current_screenshot.png

# 运行性能基准测试
python scripts/test_florence2.py --benchmark

# 指定迭代次数
python scripts/test_florence2.py --benchmark --iterations 20
```

## 环境变量配置（可选）

```powershell
# 强制使用 CPU（即使有 GPU）
set SMALL_MODEL_DEVICE=cpu

# 指定模型缓存目录
set SMALL_MODEL_CACHE=D:\models\huggingface

# Hugging Face 缓存目录
set HF_HOME=D:\models\huggingface
```

## 性能参考

| 设备 | 首次加载 | 单次定位 |
|------|----------|----------|
| CPU (i5/i7) | 5-10s | 1-3s |
| GPU (GTX 1060) | 3-5s | 300-500ms |
| GPU (RTX 3060) | 2-3s | 150-300ms |

## 故障排除

### 1. 下载模型超时

设置 Hugging Face 镜像：

```powershell
set HF_ENDPOINT=https://hf-mirror.com
```

### 2. 内存不足

Florence-2-base 需要约 2GB 内存。如果内存不足：

```python
# 使用 TaskRunner 时禁用小模型
runner = TaskRunner(adb, llm_config, small_model_backend="none")
```

### 3. CUDA 版本不匹配

确保 PyTorch CUDA 版本与系统 CUDA 版本匹配：

```powershell
# 查看系统 CUDA 版本
nvidia-smi

# 查看 PyTorch CUDA 版本
python -c "import torch; print(torch.version.cuda)"
```

### 4. 模型加载失败

尝试清除缓存重新下载：

```powershell
rmdir /s /q C:\Users\%USERNAME%\.cache\huggingface\hub\models--microsoft--Florence-2-base
```

## 在代码中使用

```python
from ai.small_model_locator import preload_florence2, check_gpu_available

# 检查 GPU 状态
info = check_gpu_available()
print(f"推荐设备: {info['recommended_device']}")

# 预加载模型（程序启动时调用一次）
preload_florence2()

# 在 TaskRunner 中使用（默认启用）
from core.task_runner import TaskRunner
runner = TaskRunner(adb, llm_config)  # 默认使用 florence2

# 或明确指定
runner = TaskRunner(adb, llm_config, small_model_backend="florence2")
```
