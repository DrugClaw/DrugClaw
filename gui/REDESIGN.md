# DrugClaw Tauri - 重新设计

## 设计改进

### 🎨 视觉优化
- **现代配色方案**：从深绿色主题改为深蓝灰色（Slate）+ 青色（Cyan）+ 翠绿色（Emerald）渐变
- **柔和渐变**：使用更细腻的渐变效果，提升视觉层次
- **改进的对比度**：更好的文字可读性和视觉焦点
- **自定义滚动条**：统一的深色主题滚动条样式

### 🏗️ 架构优化
- **组件化**：拆分为独立的可复用组件
  - `Field` - 表单字段组件
  - `Toggle` - 开关组件
  - `Charts` - 图表组件（UptimeLineChart, ActivityBars）
  - `StatusBadge` - 状态徽章组件
- **视图分离**：
  - `SetupView` - 系统配置视图
  - `OperationsView` - 运行监控视图
- **类型安全**：集中的类型定义文件 `types.ts`
- **配置管理**：独立的 provider 配置文件

### ✨ 交互增强
- **流畅动画**：所有交互都有平滑的过渡效果
- **悬停反馈**：按钮和可交互元素的悬停状态
- **视觉反馈**：加载状态、禁用状态的清晰指示
- **渐变按钮**：主要操作使用渐变背景和阴影效果

### 📊 数据可视化
- **趋势图优化**：使用 SVG 渐变色的折线图
- **活跃度柱状图**：渐变色柱状图，支持悬停效果
- **流式统计**：彩色进度条显示不同日志类型的比例

## 文件结构

```
src/
├── components/          # 可复用组件
│   ├── Field.tsx
│   ├── Toggle.tsx
│   ├── Charts.tsx
│   └── StatusBadge.tsx
├── views/              # 视图组件
│   ├── SetupView.tsx
│   └── OperationsView.tsx
├── config/             # 配置文件
│   └── providers.ts
├── types.ts            # TypeScript 类型定义
├── App.tsx             # 主应用组件
├── main.tsx            # 入口文件
└── styles.css          # 全局样式
```

## 运行

```bash
npm run dev          # 开发模式
npm run build        # 构建生产版本
npm run tauri dev    # Tauri 开发模式
npm run tauri build  # 构建 Tauri 应用
```

## 技术栈

- React 18
- TypeScript
- Tailwind CSS 4
- Tauri 2
- Vite 5
