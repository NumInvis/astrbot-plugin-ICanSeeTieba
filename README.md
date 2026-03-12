# 🔍 贴吧观察者

[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-blue)](https://github.com/Soulter/AstrBot)
[![GitHub stars](https://img.shields.io/github/stars/NumInvis/astrbot-plugin-ICanSeeTieba?style=social)](https://github.com/NumInvis/astrbot-plugin-ICanSeeTieba/stargazers)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> 🎯 实时监控贴吧新帖，热帖秒级预警，支持多群推送和 Web 可视化管理

## ✨ 功能亮点

| 功能 | 描述 |
|-----|------|
| 📡 **实时监控** | 自动监控多个贴吧，新帖秒级推送到指定群 |
| 🔥 **热帖预警** | 智能识别热帖（回复/点赞阈值），自动预警提醒 |
| 📊 **数据统计** | 每日发帖统计、贴吧活跃度排行、热门帖子追踪 |
| 🌐 **Web 管理** | 可视化配置界面，支持双模式订阅管理（贴吧↔群） |
| 🔔 **多群推送** | 一个贴吧可推送到多个群，灵活配置 |
| 🔍 **帖子搜索** | 支持按关键词搜索历史帖子 |
| 📜 **历史查看** | 查看贴吧历史帖子记录 |

## 🚀 快速开始

### 1️⃣ 安装插件

在 AstrBot 插件市场搜索 `贴吧观察者` 或手动安装：

```bash
# 克隆到插件目录
git clone https://github.com/NumInvis/astrbot-plugin-ICanSeeTieba.git
```

### 2️⃣ 基本命令

发送以下命令开始使用：

```
/tb菜单          # 查看主菜单
/tb帮助          # 查看详细帮助

# 订阅管理
/tb订阅 鸣潮     # 在当前群订阅"鸣潮"吧
/tb退订 鸣潮     # 在当前群退订"鸣潮"吧
/tb列表          # 查看本群订阅的贴吧
/tb全部订阅      # 查看所有订阅情况

# 查询命令
/tb统计          # 查看发帖统计
/tb排行          # 查看贴吧活跃度排行
/tb热帖          # 查看热门帖子
/tb历史 鸣潮     # 查看历史帖子
/tb搜索 关键词   # 搜索帖子

# 管理命令
/tb刷新 鸣潮     # 手动刷新指定贴吧
/tb检查          # 立即检查所有贴吧
/tb模式          # 切换订阅显示模式
```

### 3️⃣ Web 管理界面

访问 `http://你的服务器IP:5000` 进入可视化配置界面：

- 默认用户名：`root`
- 默认密码：`moning`（首次登录后请立即修改）

支持功能：
- ⚙️ 基础配置（检查间隔、热帖阈值）
- 👤 管理员管理
- 📋 订阅管理（支持双模式切换）

## 📸 功能预览

### 新帖推送
```
【鸣潮吧】新帖标题
👤 作者: xxx
📝 内容: 帖子内容摘要...
💬 回复:10 | 👍 点赞:50
🔗 链接: https://tieba.baidu.com/p/xxx
🕐 发布时间: 2024-01-01 12:00:00
```

### 热帖预警
```
🔥【热帖预警】🔥
【鸣潮吧】热帖标题
💬 回复: 150 | 👍 点赞: 2000
🔗 链接: https://tieba.baidu.com/p/xxx
```

### 每日报告
```
📊 每日数据报告 (2024-01-01)
=========================

📈 昨日发帖统计:
  • 鸣潮: 50帖
  • 原神内鬼: 30帖

🏆 活跃度排行 TOP5:
  1. 鸣潮: 500帖
  2. 原神内鬼: 300帖

🔥 热门帖子 TOP5:
  1. [鸣潮]热帖标题
     回复:100 点赞:1000
```

## ⚙️ 配置说明

### 通过 Web 界面配置

访问 Web 管理界面，可以配置：

| 配置项 | 默认值 | 说明 |
|-------|-------|------|
| 检查间隔 | 300秒 | 多久检查一次贴吧更新 |
| 获取帖子数 | 5条 | 每次获取的最新帖子数量 |
| 热帖回复阈值 | 100 | 回复数超过此值视为热帖 |
| 热帖点赞阈值 | 1000 | 点赞数超过此值视为热帖 |

### 通过 AstrBot 配置

在 `data/config/astrbot_config.yaml` 中添加：

```yaml
# 贴吧观察者配置
tieba_check_interval_seconds: 300
tieba_threads_to_retrieve: 5
tieba_hot_reply_threshold: 100
tieba_hot_agree_threshold: 1000
tieba_admin_users:
  - "你的QQ号"
tieba_forum_groups:
  鸣潮:
    - "群号1"
    - "群号2"
```

## 🏗️ 技术架构

```
┌─────────────────────────────────────────┐
│           AstrBot 框架                   │
├─────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    │
│  │  命令处理器  │    │  定时任务   │    │
│  └──────┬──────┘    └──────┬──────┘    │
│         │                  │           │
│  ┌──────▼──────────────────▼──────┐    │
│  │        贴吧观察者插件          │    │
│  │  ┌─────────┐  ┌─────────────┐ │    │
│  │  │订阅管理器│  │  热帖追踪器  │ │    │
│  │  └────┬────┘  └──────┬──────┘ │    │
│  │       │              │        │    │
│  │  ┌────▼──────────────▼────┐   │    │
│  │  │      贴吧客户端        │   │    │
│  │  │   (aiotieba封装)      │   │    │
│  │  └────────────────────────┘   │    │
│  └────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## 📝 更新日志

### v1.0.0 (2024-03-12)
- ✨ 初始版本发布
- 📡 贴吧实时监控功能
- 🔥 热帖预警功能
- 📊 数据统计功能
- 🌐 Web 管理界面
- 🔄 数据自动迁移

## 🤝 贡献指南

欢迎提交 Issue 和 PR！

1. Fork 本仓库
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的变更 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开一个 Pull Request

## 💖 赞助支持

如果这个插件对你有帮助，可以考虑赞助支持开发者：

[![爱发电](https://img.shields.io/badge/爱发电-赞助开发者-pink)](https://afdian.com/a/r0xy0)

👉 [https://afdian.com/a/r0xy0](https://afdian.com/a/r0xy0)

你的支持是我持续开发的动力！❤️

## 📄 许可证

本项目基于 [MIT](LICENSE) 许可证开源。

## 🙏 致谢

- [AstrBot](https://github.com/Soulter/AstrBot) - 优秀的聊天机器人框架
- [aiotieba](https://github.com/Starry-OvO/aiotieba) - 贴吧 API 封装库

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/NumInvis">NumInvis</a>
</p>
