# 参考图片管理

参考图片用于界面元素定位和页面验证，是工作流执行的基础。

## 目录结构

```
apps/{channel}/images/
├── aliases.yaml              # 中文别名映射
├── {channel}_*.png           # 点击操作参考图（根目录）
├── {channel}_*_v1.png        # 变体版本（多设备适配）
├── contacts/                 # 联系人参考图
│   └── {contact_name}.png
└── system/                   # 界面验证参考图
    └── {channel}_*_page.png
```

## 参考图分类

| 类型 | 目录 | 用途 | 命名示例 |
|------|------|------|----------|
| 点击操作图 | `images/` | 定位可点击元素中心点 | `wechat_send_button.png` |
| 界面验证图 | `images/system/` | 验证当前在哪个页面 | `wechat_home_page.png` |
| 联系人图 | `images/contacts/` | 识别联系人头像/名称 | `zhanghua.png` |
| 变体图 | `images/` | 多设备适配 | `wechat_send_button_v1.png` |

## ModuleAssets 类

以下是 `apps/base.py` 中资源管理的实际实现：

```python
# apps/base.py 实际代码

class ModuleAssets:
    """
    模块资源管理器

    管理模块的参考图片、提示词模板等资源。
    """

    def __init__(self, module_dir: Path):
        self.module_dir = module_dir
        self.images_dir = module_dir / "images"
        self.prompts_dir = module_dir / "prompts"

        self._image_cache: Dict[str, Path] = {}
        self._prompt_cache: Dict[str, str] = {}
        self._aliases: Dict[str, str] = {}

        self._load_aliases()

    def _load_aliases(self):
        """加载图片别名配置"""
        alias_file = self.images_dir / "aliases.yaml"
        if alias_file.exists():
            with open(alias_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                self._aliases = data.get('aliases', {})
```

## 获取参考图

```python
# apps/base.py 实际代码

def get_image(self, name: str) -> Optional[Path]:
    """
    获取参考图片路径

    支持：
    - 直接文件名: "wechat_icon.png"
    - 别名: "微信图标" -> "wechat_icon.png"
    - 子目录路径: "contacts/zhanghua" -> contacts/zhanghua.png
    - 联系人别名: "张华" -> contacts/zhanghua.png
    """
    # 检查缓存
    if name in self._image_cache:
        return self._image_cache[name]

    # 检查别名
    actual_name = self._aliases.get(name, name)

    # 搜索图片
    if not self.images_dir.exists():
        return None

    # 尝试精确匹配（支持子目录路径，如 contacts/zhanghua）
    for ext in ['.png', '.jpg', '.jpeg', '.webp']:
        path = self.images_dir / f"{actual_name}{ext}"
        if path.exists():
            self._image_cache[name] = path
            return path

    # 尝试带扩展名的匹配
    path = self.images_dir / actual_name
    if path.exists():
        self._image_cache[name] = path
        return path

    # 在根目录模糊匹配
    for file in self.images_dir.iterdir():
        if file.is_file() and actual_name.lower() in file.stem.lower():
            self._image_cache[name] = file
            return file

    # 在 contacts 子目录中搜索（用于联系人）
    contacts_dir = self.images_dir / "contacts"
    if contacts_dir.exists():
        for ext in ['.png', '.jpg', '.jpeg', '.webp']:
            path = contacts_dir / f"{actual_name}{ext}"
            if path.exists():
                self._image_cache[name] = path
                return path
        # 模糊匹配联系人
        for file in contacts_dir.iterdir():
            if file.is_file() and actual_name.lower() in file.stem.lower():
                self._image_cache[name] = file
                return file

    return None
```

## 获取参考图变体

用于多设备适配：

```python
# apps/base.py 实际代码

def get_image_variants(self, name: str) -> List[Path]:
    """
    获取参考图片的所有变体路径

    支持多设备适配：
    - wechat_add_button.png (主图)
    - wechat_add_button_v1.png (变体1)
    - wechat_add_button_v2.png (变体2)

    Args:
        name: 参考图名称

    Returns:
        所有变体的路径列表（按优先级排序）
    """
    variants = []

    # 先获取主图
    primary = self.get_image(name)
    if primary:
        variants.append(primary)

    # 检查别名
    actual_name = self._aliases.get(name, name)

    # 查找变体 (_v1, _v2, _v3, ...)
    if not self.images_dir.exists():
        return variants

    for i in range(1, 10):  # 支持最多 9 个变体（从 _v1 开始）
        variant_name = f"{actual_name}_v{i}"
        for ext in ['.png', '.jpg', '.jpeg', '.webp']:
            path = self.images_dir / f"{variant_name}{ext}"
            if path.exists():
                variants.append(path)
                break

    return variants
```

## 列出所有参考图

```python
# apps/base.py 实际代码

def list_images(self) -> List[str]:
    """列出所有可用的参考图片（包括子目录）"""
    if not self.images_dir.exists():
        return []

    images = []
    valid_exts = ['.png', '.jpg', '.jpeg', '.webp']

    # 根目录图片
    for file in self.images_dir.iterdir():
        if file.is_file() and file.suffix.lower() in valid_exts:
            images.append(file.stem)

    # 扫描子目录（contacts, system 等）
    subdirs = ["contacts", "system"]
    for subdir in subdirs:
        subdir_path = self.images_dir / subdir
        if subdir_path.exists():
            for file in subdir_path.iterdir():
                if file.is_file() and file.suffix.lower() in valid_exts:
                    images.append(f"{subdir}/{file.stem}")

    return sorted(images)
```

## aliases.yaml 配置示例

```yaml
# apps/wechat/images/aliases.yaml

aliases:
  # 中文别名 -> 英文文件名
  微信图标: wechat_icon
  发送按钮: wechat_chat_send
  输入框: wechat_chat_input
  返回: wechat_back
  搜索: wechat_search_button
  朋友圈入口: wechat_moments_entry
  相机图标: wechat_moments_camera

  # 联系人别名
  张华: contacts/wechat_contacts_zhanghua
  李明: contacts/wechat_contacts_liming
```

## 参考图命名规范

### 根目录（点击操作图）

```
{channel}_{element}.png
{channel}_{element}_v{n}.png  # 变体
```

示例：
- `wechat_send_button.png` - 发送按钮
- `wechat_chat_input.png` - 聊天输入框
- `wechat_back.png` - 返回按钮
- `wechat_back_v1.png` - 返回按钮变体1

### system/ 目录（界面验证图）

```
{channel}_{screen}_page.png
```

示例：
- `wechat_home_page.png` - 首页
- `wechat_contacts_page.png` - 通讯录页
- `wechat_discover_page.png` - 发现页

### contacts/ 目录（联系人图）

```
{channel}_contacts_{name}.png
```

示例：
- `wechat_contacts_zhanghua.png` - 张华
- `wechat_contacts_liming.png` - 李明

## 参考图制作建议

### 1. 截图质量

- 使用高清截图
- 避免截图时出现动态元素（加载动画、时间等）
- 保持界面稳定后再截图

### 2. 元素边界

```
┌─────────────────────┐
│     适当留白边距     │
│   ┌─────────────┐   │
│   │   目标元素   │   │
│   └─────────────┘   │
│                     │
└─────────────────────┘
```

- 包含完整的目标元素
- 适当留白，但不要太多背景
- 确保元素在不同分辨率下仍可识别

### 3. 避免动态内容

**不要包含：**
- 时间显示
- 未读消息数
- 头像（除非是固定的）
- 在线状态指示器

**推荐做法：**
- 截取静态 UI 元素
- 选择不易变化的特征区域

### 4. 多设备适配

为不同设备/分辨率准备变体：

```
wechat_send_button.png     # 主图（1080p）
wechat_send_button_v1.png  # 变体1（720p）
wechat_send_button_v2.png  # 变体2（平板）
```

## 参考图使用流程

```
用户任务: "点击发送按钮"
         │
         ▼
┌─────────────────────┐
│ handler.get_image() │
│ 或 get_image_variants() │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 检查别名映射         │
│ aliases.yaml        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 搜索参考图文件       │
│ 1. 精确匹配         │
│ 2. 模糊匹配         │
│ 3. 子目录搜索       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ HybridLocator.locate│
│ OpenCV + AI 混合定位 │
└─────────────────────┘
```
