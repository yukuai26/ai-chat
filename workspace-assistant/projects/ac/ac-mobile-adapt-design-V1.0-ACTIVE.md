# 手机适配设计文档 — Phase 12

> 版本：V1.0 | 状态：ACTIVE | 日期：2026-05-27

---

## 一、概述

全面的移动端适配。一套 CSS 兼容安卓/苹果，不分开写。

## 二、适配目标

| 屏幕 | 宽度 | 布局 |
|------|------|------|
| 手机竖屏 | < 768px | 单列 + 底部 Tab |
| 手机横屏 | 768-1024px | 双列 |
| 平板/桌面 | > 1024px | 三列（侧边栏+内容+右侧） |

## 三、手机布局（< 768px）

```
┌─────────────────────┐
│ 小助手        ☰ 登录│  ← 顶部栏（44px）
├─────────────────────┤
│                     │
│  当前 Tab 内容       │  ← 占满屏幕
│  （聊天 / 文件 /     │
│   每日 Dashboard）   │
│                     │
├─────────────────────┤
│ 💬  │ 📁  │ 📊  │ ⚙ │  ← 底部 Tab 栏（56px）
└─────────────────────┘
```

**交互规则：**
- 侧边栏 → 独立页面 / 滑出面板
- 设置面板 → 独立页面
- 顶部栏：Logo + ☰ 汉堡菜单（侧滑出导航）

## 四、底部 Tab 栏

```
固定底部 56px
  💬 聊天   📁 文件   📊 每日   ⚙ 设置
  活跃 Tab 深色文字 + 顶部 2px 线
  非活跃 灰色文字
```

## 五、各 Tab 手机适配

### 5.1 聊天 Tab
- 对话列表 + 消息区 → 分两页（列表页 → 点进聊天 → 消息页）
- 消息页顶部：← 返回 + 对话标题
- 文件选择器：底部弹 Sheet
- 输入框：固定底部，不被键盘挡住（`visualViewport` API）

### 5.2 文件 Tab
- 目录树 → 折叠到顶部下拉选择
- 文件列表 → 每行占满宽度
- 文件查看器 → 全屏模式
- 上传按钮 → 底部悬浮 `+` 按钮

### 5.3 每日 Tab
- 卡片从 3 列变单列纵向排列
- 展开模式 → 全屏占满
- 指令输入框 → 固定底部

## 六、触摸优化

| 项 | 规范 |
|------|------|
| 最小触摸目标 | 44×44px（iOS HIG）/ 48×48px（Material） |
| 按钮间距 | ≥ 8px |
| 滑动删除 | Todo/随手记/收藏 支持左滑删除 |
| 下拉刷新 | 新闻/数据卡片 支持下拉刷新 |
| 长按 | 文件/消息 长按出现操作菜单 |
| 双击 | 图片/代码 双击缩放 |

## 七、文件操作手机化

**上传：**
```html
<!-- 点击触发手机原生选择器 -->
<input type="file" accept="*/*" capture="environment">
<!-- capture: 直接拍照；不设 capture: 弹相册/文件管理器 -->
```

**下载：**
```html
<a href="/v1/files/download?path=xxx" download>
  → 手机浏览器直接下载到 Downloads
```

**拖拽：** 移动端不支持拖拽，改用 + 按钮触发上传。

## 八、CSS 断点

```css
/* 全局 */
:root { --mobile: 768px; --tablet: 1024px; }

/* 手机 */
@media (max-width: 767px) {
  .sidebar { display: none; }        /* 侧栏隐藏 */
  .desktop-nav { display: none; }    /* 顶部导航隐藏 */
  .mobile-bottom-nav { display: flex; } /* 底部 Tab 显示 */
  .card-grid { grid-template-columns: 1fr; } /* 卡片单列 */
  .message-bubble { max-width: 85%; }  /* 消息气泡更宽 */
}

/* 平板 */
@media (min-width: 768px) and (max-width: 1023px) {
  .card-grid { grid-template-columns: repeat(2, 1fr); }
}
```

## 九、键盘适配

```javascript
// 监听虚拟键盘弹出，调整输入框位置
window.visualViewport.addEventListener('resize', () => {
  const keyboardHeight = window.innerHeight - visualViewport.height;
  inputArea.style.bottom = keyboardHeight + 'px';
});
```

## 十、TODO

| # | TODO | 状态 |
|---|------|:--:|
| MB1 | 底部 Tab 栏组件（💬📁📊⚙ + 活跃指示 + 路由切换） | [x] |
| MB2 | 顶部栏组件（Logo + 汉堡菜单 + 用户头像） | [x] |
| MB3 | 侧滑导航面板（从左侧滑出，半透明遮罩） | [x] |
| MB4 | CSS 断点系统（手机/平板/桌面三档） | [x] |
| MB5 | 聊天 Tab 手机化（列表页+消息页分页 + 输入框键盘适配） | [x] |
| MB6 | 文件 Tab 手机化（目录下拉 + 全屏查看 + 悬浮上传按钮） | [x] |
| MB7 | 每日 Tab 手机化（单列卡片 + 全屏展开） | [x] |
| MB8 | 触摸优化（44px 最小目标 + 左滑删除 + 下拉刷新 + 长按菜单） | [x] |
| MB9 | 文件上传手机化（input file + capture 拍照） | [x] |
| MB10 | 文件下载手机化（<a download> 触发浏览器下载） | [x] |
| MB11 | 安全区适配（刘海屏 + 底部指示条 padding） | [x] |

## 十一、进度追踪

| Phase | 内容 | 状态 | TODO |
|:-----:|------|:----:|:--:|
| 12 | 📱 手机适配 | ✅ 已完成 | 11 |
