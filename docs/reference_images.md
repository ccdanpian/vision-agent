# VisionAgent 参考图规范

## 目录结构

```
project/
├── assets/                          # 全局参考图库
│   ├── index.json                   # 全局索引文件
│   ├── icons/                       # 应用图标
│   │   ├── wechat.png
│   │   ├── chrome.png
│   │   └── ...
│   ├── ui/                          # 通用 UI 元素
│   │   ├── navigation/              # 导航元素
│   │   ├── actions/                 # 操作按钮
│   │   ├── dialogs/                 # 对话框元素
│   │   ├── input/                   # 输入相关
│   │   └── media/                   # 媒体控件
│   └── states/                      # 屏幕状态
│       ├── system/                  # 系统状态
│       └── wechat/                  # 微信状态
│
└── apps/                            # 应用模块
    ├── wechat/
    │   ├── images/                  # 微信专属参考图
    │   │   ├── aliases.yaml         # 中文别名配置
    │   │   └── *.png
    │   └── prompts/
    ├── chrome/
    │   └── images/
    └── system/
        └── images/
```

---

## 命名规范

### 通用规则

1. **小写字母 + 下划线**：`wechat_add_button.png`
2. **格式**：`{app}_{location}_{element}.png`
3. **支持格式**：PNG（推荐）、JPG、WebP

### 命名模式

| 类型 | 格式 | 示例 |
|------|------|------|
| 应用图标 | `{app}.png` | `wechat.png`, `chrome.png` |
| 导航元素 | `{app}_{nav}_{element}.png` | `wechat_tab_contacts.png` |
| 按钮 | `{app}_{page}_{button}.png` | `wechat_chat_send_button.png` |
| 输入框 | `{app}_{page}_input.png` | `chrome_address_input.png` |
| 状态截图 | `{app}_{state}.png` | `wechat_home.png` |

---

## 全局参考图 (assets/)

### icons/ - 应用图标

用于启动应用、识别应用状态。

| 文件名 | 别名 | 包名 | 说明 |
|--------|------|------|------|
| `wechat.png` | 微信, WeChat | com.tencent.mm | 微信应用图标 |
| `chrome.png` | Chrome, 谷歌浏览器 | com.android.chrome | Chrome 图标 |
| `settings.png` | 设置, Settings | com.android.settings | 系统设置 |
| `phone.png` | 电话, 拨号 | com.android.dialer | 电话应用 |
| `contacts.png` | 联系人, 通讯录 | com.android.contacts | 联系人应用 |
| `messages.png` | 短信, 信息 | com.android.mms | 短信应用 |
| `camera.png` | 相机 | com.android.camera | 相机应用 |
| `gallery.png` | 相册, 图库 | com.android.gallery3d | 相册应用 |
| `alipay.png` | 支付宝 | com.eg.android.AlipayGphone | 支付宝 |
| `taobao.png` | 淘宝 | com.taobao.taobao | 淘宝 |
| `qq.png` | QQ | com.tencent.mobileqq | QQ |
| `wechat_work.png` | 企业微信 | com.tencent.wework | 企业微信 |

### ui/navigation/ - 导航元素

| 文件名 | 说明 |
|--------|------|
| `back_arrow_black.png` | 黑色返回箭头 (浅色主题) |
| `back_arrow_white.png` | 白色返回箭头 (深色主题) |
| `home_button.png` | 主页按钮 |
| `recent_apps.png` | 最近任务按钮 |
| `hamburger_menu.png` | 汉堡菜单 (三横线) |

### ui/actions/ - 操作按钮

| 文件名 | 说明 |
|--------|------|
| `search_icon.png` | 搜索图标 (放大镜) |
| `add_plus.png` | 添加按钮 (+) |
| `more_dots_v.png` | 更多选项 (竖向三点 ⋮) |
| `more_dots_h.png` | 更多选项 (横向三点 ⋯) |
| `share_icon.png` | 分享图标 |
| `delete_icon.png` | 删除图标 |
| `edit_icon.png` | 编辑图标 (铅笔) |
| `refresh_icon.png` | 刷新图标 |

### ui/dialogs/ - 对话框元素

| 文件名 | 说明 |
|--------|------|
| `confirm_button.png` | 确认/允许按钮 |
| `cancel_button.png` | 取消按钮 |
| `ok_button.png` | 确定按钮 |
| `close_x.png` | 关闭按钮 (X) |
| `close_x_circle.png` | 圆形关闭按钮 |
| `checkbox_checked.png` | 已勾选复选框 |

### ui/input/ - 输入元素

| 文件名 | 说明 |
|--------|------|
| `text_field.png` | 通用文本输入框 |
| `search_bar.png` | 搜索栏 |
| `send_button.png` | 发送按钮 |
| `voice_input.png` | 语音输入按钮 |

### ui/media/ - 媒体控件

| 文件名 | 说明 |
|--------|------|
| `play_button.png` | 播放按钮 |
| `pause_button.png` | 暂停按钮 |
| `video_call.png` | 视频通话按钮 |
| `voice_call.png` | 语音通话按钮 |
| `camera_switch.png` | 切换摄像头 |

### states/ - 屏幕状态

| 文件名 | 说明 |
|--------|------|
| `states/system/home_screen.png` | 手机桌面 |
| `states/system/lock_screen.png` | 锁屏界面 |
| `states/system/notification_panel.png` | 通知栏 |
| `states/system/app_drawer.png` | 应用抽屉 |

---

## 微信模块 (apps/wechat/images/)

### 首页元素

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `wechat_home.png` | 微信首页 | 微信主界面截图 |
| `wechat_tab_chat.png` | 微信标签 | 底部"微信"标签 |
| `wechat_tab_contacts.png` | 通讯录标签 | 底部"通讯录"标签 |
| `wechat_tab_discover.png` | 发现标签 | 底部"发现"标签 |
| `wechat_tab_me.png` | 我标签 | 底部"我"标签 |

### 顶部操作

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `wechat_add_button.png` | 添加, + | 右上角 + 按钮 |
| `wechat_search_button.png` | 搜索 | 右上角搜索按钮 |

### 添加菜单

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `wechat_menu_add_friend.png` | 添加朋友 | +菜单 - 添加朋友 |
| `wechat_menu_scan.png` | 扫一扫 | +菜单 - 扫一扫 |
| `wechat_menu_group_chat.png` | 发起群聊 | +菜单 - 发起群聊 |
| `wechat_menu_receive_payment.png` | 收付款 | +菜单 - 收付款 |

### 聊天界面

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `wechat_chat_input.png` | 输入框 | 聊天输入框 |
| `wechat_chat_send.png` | 发送 | 发送按钮 |
| `wechat_chat_voice.png` | 语音 | 语音按钮 |
| `wechat_chat_emoji.png` | 表情 | 表情按钮 |
| `wechat_chat_more.png` | 更多 | 更多按钮 (+) |

### 添加好友

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `wechat_add_search_input.png` | 搜索输入框 | 添加好友搜索框 |
| `wechat_add_contact_button.png` | 添加到通讯录 | 添加联系人按钮 |
| `wechat_add_send_button.png` | 发送申请 | 发送好友申请按钮 |

### 通讯录界面

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `wechat_contacts_new_friend.png` | 新的朋友 | 新的朋友入口 |
| `wechat_contacts_group_chat.png` | 群聊 | 群聊入口 |
| `wechat_contacts_tag.png` | 标签 | 标签入口 |
| `wechat_contacts_official.png` | 公众号 | 公众号入口 |

### 朋友圈

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `wechat_moments_camera.png` | 发朋友圈 | 朋友圈相机按钮 |
| `wechat_moments_publish.png` | 发表 | 发表按钮 |

---

## Chrome 模块 (apps/chrome/images/)

### 首页元素

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `chrome_home.png` | Chrome首页 | Chrome 主界面 |
| `chrome_address_bar.png` | 地址栏 | 顶部地址/搜索栏 |

### 导航

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `chrome_back.png` | 返回 | 返回按钮 |
| `chrome_forward.png` | 前进 | 前进按钮 |
| `chrome_refresh.png` | 刷新 | 刷新按钮 |
| `chrome_home_button.png` | 主页 | 主页按钮 |

### 标签页

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `chrome_tabs_button.png` | 标签页 | 标签页切换按钮 |
| `chrome_new_tab.png` | 新建标签 | 新建标签按钮 |
| `chrome_close_tab.png` | 关闭标签 | 关闭标签按钮 |

### 菜单

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `chrome_menu_button.png` | 菜单 | 三点菜单按钮 |
| `chrome_menu_new_tab.png` | 新建标签页 | 菜单 - 新建标签页 |
| `chrome_menu_incognito.png` | 无痕模式 | 菜单 - 无痕模式 |
| `chrome_menu_bookmarks.png` | 书签 | 菜单 - 书签 |
| `chrome_menu_history.png` | 历史记录 | 菜单 - 历史记录 |
| `chrome_menu_downloads.png` | 下载内容 | 菜单 - 下载内容 |
| `chrome_menu_settings.png` | 设置 | 菜单 - 设置 |
| `chrome_menu_find.png` | 在页面中查找 | 菜单 - 查找 |
| `chrome_menu_share.png` | 分享 | 菜单 - 分享 |

### 搜索/输入

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `chrome_search_input.png` | 搜索框 | 搜索输入框 |
| `chrome_voice_search.png` | 语音搜索 | 语音搜索按钮 |
| `chrome_go_button.png` | 前往 | 前往/搜索按钮 |

### 百度搜索页面（重要）

百度是常用的搜索引擎，需要准备专门的参考图以提高搜索任务的成功率：

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `chrome_baidu_search_box.png` | 百度搜索框 | 百度首页的搜索输入框 |
| `chrome_baidu_search_box_v2.png` | - | 搜索框变体（聚焦状态） |
| `chrome_baidu_search_button.png` | 百度一下 | 百度搜索按钮 |
| `chrome_baidu_logo.png` | 百度Logo | 百度首页 Logo |

**参考图变体命名规则**：
- 变体从 `_v2` 开始，不是 `_v1`
- 例如：`chrome_baidu_search_box.png`（主版本）、`chrome_baidu_search_box_v2.png`（变体）
- 变体用于适应不同状态（聚焦/非聚焦）或不同分辨率

**截取建议**：
1. 在百度首页截取搜索框，确保包含完整边框
2. 搜索按钮截取「百度一下」文字和按钮背景
3. 避免截取时包含动态内容（如热搜推荐）

---

## 系统模块 (apps/system/images/)

### 设置界面

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `settings_home.png` | 设置首页 | 设置主界面 |
| `settings_wifi.png` | WLAN | WiFi 设置入口 |
| `settings_bluetooth.png` | 蓝牙 | 蓝牙设置入口 |
| `settings_display.png` | 显示 | 显示设置入口 |
| `settings_sound.png` | 声音 | 声音设置入口 |
| `settings_battery.png` | 电池 | 电池设置入口 |
| `settings_apps.png` | 应用 | 应用管理入口 |
| `settings_about.png` | 关于手机 | 关于手机入口 |

### 开关控件

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `toggle_on.png` | 开关开 | 开启状态的开关 |
| `toggle_off.png` | 开关关 | 关闭状态的开关 |

### 快捷设置

| 文件名 | 别名 | 说明 |
|--------|------|------|
| `quick_wifi.png` | WiFi图标 | 快捷设置 WiFi |
| `quick_bluetooth.png` | 蓝牙图标 | 快捷设置蓝牙 |
| `quick_airplane.png` | 飞行模式 | 快捷设置飞行模式 |
| `quick_flashlight.png` | 手电筒 | 快捷设置手电筒 |
| `quick_rotation.png` | 自动旋转 | 快捷设置自动旋转 |

---

## index.json 格式

```json
{
  "version": "1.0",
  "icons": {
    "wechat": {
      "path": "icons/wechat.png",
      "aliases": ["微信", "WeChat"],
      "package": "com.tencent.mm",
      "exists": true
    }
  },
  "ui": {
    "back_arrow_black": {
      "path": "ui/navigation/back_arrow_black.png",
      "description": "黑色返回箭头",
      "exists": true
    }
  },
  "states": {
    "wechat_main": {
      "path": "states/wechat/main.png",
      "description": "微信主界面",
      "exists": false
    }
  }
}
```

---

## aliases.yaml 格式

放置在 `apps/{module}/images/aliases.yaml`：

```yaml
# 微信模块别名配置
aliases:
  # 中文 -> 英文文件名
  添加按钮: wechat_add_button
  发送: wechat_chat_send
  搜索框: wechat_search_input
  通讯录: wechat_tab_contacts
  朋友圈: wechat_moments_camera
```

---

## 参考图制作建议

### 截图要求

1. **分辨率**：建议 1080x2400 或设备原始分辨率
2. **裁剪**：只保留目标元素，去除多余背景
3. **尺寸**：按钮/图标建议 50-150px，状态截图保持原始比例

### 最佳实践

1. **多主题**：为深色/浅色主题分别准备参考图
2. **多状态**：按钮的正常/按下/禁用状态
3. **去除动态内容**：避免包含时间、通知数等动态元素
4. **高对比度**：确保元素边缘清晰

### 优先级

按以下顺序准备参考图：

1. **必须**：应用图标、核心操作按钮
2. **推荐**：导航元素、输入框、发送按钮
3. **可选**：状态截图、辅助元素

---

## 使用示例

### 在 tasks.yaml 中引用

```yaml
steps:
  - action: tap
    target_ref: wechat_add_button      # 使用文件名
    description: 点击添加按钮

  - action: tap
    target_ref: 添加朋友               # 使用中文别名
    description: 点击添加朋友菜单项

  - action: tap
    target_ref: dynamic:搜索框         # 使用动态描述（AI定位）
    description: 点击搜索框
```

### 定位优先级

1. **模块参考图** (`apps/{module}/images/`)
2. **全局参考图** (`assets/icons/`, `assets/ui/`)
3. **AI 动态定位** (`dynamic:描述`)
