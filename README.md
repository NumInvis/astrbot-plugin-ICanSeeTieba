# 贴吧观察者 (astrbot_plugin_ICanSeeTieba)

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/NumInvis/astrbot-plugin-ICanSeeTieba)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.0+-green.svg)](https://github.com/AstrBotDevs/AstrBot)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

一个用于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的贴吧监控插件。

**当前版本: v1.0.0**

## 📢 项目说明

本项目是基于 **nonebot-plugin-tieba-monitor** 移植的 AstrBot 插件。

- **原项目**: nonebot-plugin-tieba-monitor (NoneBot2 贴吧监控插件)
- **移植作者**: [NumInvis](https://github.com/NumInvis)
- **适配平台**: [AstrBot](https://github.com/AstrBotDevs/AstrBot)

本项目在原项目的基础上，将其从 NoneBot2 框架移植到 AstrBot 框架，并进行了以下改进：
- ✅ 完全适配 AstrBot 插件架构
- ✅ 使用 AstrBot 的调度器进行定时任务
- ✅ 使用 AstrBot 的消息链发送消息
- ✅ 添加文件锁防止并发写入冲突
- ✅ 完善错误处理和日志记录
- ✅ 支持跨群订阅管理

## 功能特性

- 📢 **自动监控**: 定时检查指定贴吧的新帖子
- 🔥 **热帖追踪**: 自动检测热门帖子（回复>100或点赞>1000）并发送预警
- 📊 **数据统计**: 提供发帖统计、活跃度排行等功能
- 🔍 **帖子搜索**: 支持搜索历史帖子
- 📱 **消息推送**: 新帖自动推送到订阅的QQ群
- 🖼️ **图片支持**: 自动获取并发送帖子图片

## 安装方法

### 方法一：通过 AstrBot 插件市场安装（推荐）

1. 打开 AstrBot 管理面板
2. 进入插件市场
3. 搜索 "贴吧观察者" 或 "ICanSeeTieba"
4. 点击安装

### 方法二：手动安装

1. 将插件文件夹复制到 AstrBot 的插件目录：
```bash
cd /path/to/astrbot/data/plugins
git clone https://github.com/NumInvis/astrbot-plugin-ICanSeeTieba.git
```

2. 安装依赖：
```bash
cd astrbot-plugin-ICanSeeTieba
pip install -r requirements.txt
```

3. 重启 AstrBot

## 配置说明

在 AstrBot 的 `config.yaml` 中添加以下配置：

```yaml
# 贴吧观察者插件配置 (v1.0.0)
tieba_check_interval_seconds: 300  # 检查间隔（秒），默认5分钟
tieba_threads_to_retrieve: 5  # 每次获取的帖子数量

# 贴吧-群组映射（必填）
# 格式: {"贴吧名": ["群号1", "群号2"]}
tieba_forum_groups:
  "鸣潮":
    - "123456789"
  "李毅":
    - "123456789"
    - "987654321"

# 管理员QQ列表（可选，这些QQ号可以使用所有命令）
tieba_admin_users:
  - "123456789"

# 热帖阈值配置（可选）
tieba_hot_reply_threshold: 100  # 回复数阈值
tieba_hot_agree_threshold: 1000  # 点赞数阈值
```

## 使用命令

**注意：所有命令都需要管理员权限（群管理员或在配置中指定的管理员）**

### 查询命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `/tb菜单` | 显示主菜单 | `/tb菜单` |
| `/tb帮助` | 显示详细帮助 | `/tb帮助` |
| `/tb统计` | 查看最近7天发帖统计 | `/tb统计` |
| `/tb排行` | 查看贴吧活跃度排行 | `/tb排行` |
| `/tb热帖` | 查看热门帖子 | `/tb热帖` |
| `/tb历史 <贴吧名> [数量]` | 查看历史帖子 | `/tb历史 鸣潮 10` |
| `/tb搜索 <关键词>` | 搜索帖子 | `/tb搜索 攻略` |

### 管理命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `/tb订阅 <贴吧名>` | 在当前群订阅贴吧 | `/tb订阅 鸣潮` |
| `/tb订阅 <群号> <贴吧名>` | 为指定群订阅贴吧 | `/tb订阅 123456789 鸣潮` |
| `/tb退订 <贴吧名>` | 在当前群取消贴吧订阅 | `/tb退订 鸣潮` |
| `/tb退订 <群号> <贴吧名>` | 为指定群退订贴吧 | `/tb退订 123456789 鸣潮` |
| `/tb列表` | 查看当前群订阅列表 | `/tb列表` |
| `/tb全部订阅` | 查看所有群的订阅情况 | `/tb全部订阅` |
| `/tb刷新 <贴吧名>` | 手动刷新指定贴吧 | `/tb刷新 鸣潮` |
| `/tb检查` | 立即检查所有贴吧 | `/tb检查` |

## 消息推送示例

当有新帖子时，插件会发送如下格式的消息：

```
【鸣潮吧】这是帖子标题
👤 作者: 用户名
📝 内容: 帖子内容摘要...
💬 回复:5 | 👍 点赞:10
🔗 链接: https://tieba.baidu.com/p/123456789
🕐 发布时间: 2024-01-15 10:30:00
[图片]
```

热帖预警消息：

```
🔥【热帖预警】🔥
【鸣潮吧】热门帖子标题
💬 回复: 150 | 👍 点赞: 1200
🔗 链接: https://tieba.baidu.com/p/123456789
```

热帖升温提醒：

```
📈【热帖升温】📈
【鸣潮吧】热门帖子标题
💬 回复: 250(+100) | 👍 点赞: 2200(+1000)
🔗 链接: https://tieba.baidu.com/p/123456789
```

## 文件结构

```
astrbot_plugin_ICanSeeTieba/
├── __init__.py          # 插件入口
├── _version.py          # 版本管理
├── main.py              # 主插件类（包含所有功能）
├── tieba_client.py      # 贴吧客户端（aiotieba封装）
├── tracker.py           # 热帖追踪和统计
├── metadata.yaml        # 插件元数据
├── requirements.txt     # 依赖
├── README.md            # 说明文档
├── LICENSE              # 许可证
└── data/                # 数据目录（运行时创建）
    ├── config.json          # 配置文件
    ├── subscription.json    # 订阅配置
    ├── {贴吧名}.json        # 各贴吧帖子数据
    ├── hot_threads.json     # 热帖记录
    └── stats.json           # 统计数据
```

## 数据存储

插件会在 `data/` 目录下存储以下 JSON 文件：

- `config.json` - 插件配置（检查间隔、阈值、管理员等）
- `subscription.json` - 贴吧-群组订阅映射
- `{贴吧名}.json` - 各贴吧的帖子数据
- `hot_threads.json` - 热帖记录
- `stats.json` - 统计数据（每日发帖量、活跃度等）

## 版本历史

### v1.0.0 (2024-03-12)
- 🎉 初始版本发布
- ✅ 贴吧监控核心功能
- ✅ 热帖追踪与预警
- ✅ 数据统计与排行
- ✅ 跨群订阅管理
- ✅ 完整的权限控制

## 注意事项

1. **频率限制**: 贴吧有反爬机制，请合理设置检查间隔（建议不小于300秒）
2. **风控规避**: 插件内置了随机延迟机制，避免消息发送过快被风控
3. **权限要求**: 所有命令需要管理员权限（群管理员或配置的管理员QQ）
4. **订阅管理**: 使用 `/tb订阅` 和 `/tb退订` 可以动态管理订阅，无需重启机器人

## 依赖

- [aiotieba](https://github.com/Starry-OvO/aiotieba) >= 4.0.0 - 贴吧API封装
- [aiohttp](https://github.com/aio-libs/aiohttp) >= 3.8.0 - HTTP客户端

## 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。

## 致谢

### 原项目
- **nonebot-plugin-tieba-monitor** - 本项目的原始代码基础
  - 感谢原作者开发的优秀 NoneBot2 贴吧监控插件

### 依赖项目
- [AstrBot](https://github.com/AstrBotDevs/AstrBot) - 优秀的QQ机器人框架
- [aiotieba](https://github.com/Starry-OvO/aiotieba) - 贴吧API封装库

## 相关项目

- [astrbot-plugin-monningsignin](https://github.com/NumInvis/astrbot-plugin-monningsignin) - 莫宁宁的币 - AstrBot 经济系统插件

## 联系方式

- **作者**: [NumInvis](https://github.com/NumInvis)
- **GitHub**: https://github.com/NumInvis/astrbot-plugin-ICanSeeTieba
- **B站**: [鬼神莫能窥](https://space.bilibili.com/274736623)

欢迎提交 Issue 和 Pull Request！
