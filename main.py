"""
贴吧观察者 - AstrBot 贴吧监控插件
移植自 nonebot-plugin-tieba-monitor
版本: 1.0.0
"""

import asyncio
import json
import os
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.message_event_result import MessageChain
import astrbot.core.message.components as Comp

from ._version import __version__, __plugin_name__, __author__, __plugin_desc__
from .tieba_client import TiebaClient
from .tracker import HotThreadTracker


# ============ 配置常量 ============
ADMIN_USERS: List[str] = []  # 将在初始化时从配置加载


@register(__plugin_name__, __author__, __plugin_desc__, __version__)
class TiebaPlugin(Star):
    """贴吧观察者插件主类"""

    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config
        self.context = context

        # 数据目录 - 使用 AstrBot 的数据目录规范
        self.data_dir = str(StarTools.get_data_dir("astrbot_plugin_ICanSeeTieba"))
        os.makedirs(self.data_dir, exist_ok=True)

        # 配置文件路径
        self.config_file = os.path.join(self.data_dir, "config.json")
        self.subscription_file = os.path.join(self.data_dir, "subscription.json")
        
        # 保存群的 unified_msg_origin
        self.group_origins: Dict[str, str] = {}

        # 加载配置
        self._load_config()

        # 初始化组件
        self.tieba_client = TiebaClient()
        self.tracker = HotThreadTracker(self.data_dir)

        # 全局管理员列表
        global ADMIN_USERS
        ADMIN_USERS = self.admin_users.copy()

        # 文件写入锁，防止并发写入
        self._file_lock = asyncio.Lock()

        logger.info(f"贴吧观察者已加载: 监控{len(self.forum_groups)}个贴吧")

    def _load_config(self):
        """加载配置文件"""
        # 默认配置
        default_config = {
            "check_interval_seconds": 300,
            "threads_to_retrieve": 5,
            "hot_reply_threshold": 100,
            "hot_agree_threshold": 1000,
            "admin_users": [],
            "forum_groups": {},
            "group_origins": {}
        }

        # 从文件加载配置
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    default_config.update(loaded_config)
            except json.JSONDecodeError as e:
                logger.error(f"配置文件JSON格式错误: {e}")
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")

        # 从 AstrBot 配置加载（优先级更高）
        if self.config:
            default_config["check_interval_seconds"] = self.config.get(
                "tieba_check_interval_seconds", default_config["check_interval_seconds"]
            )
            default_config["threads_to_retrieve"] = self.config.get(
                "tieba_threads_to_retrieve", default_config["threads_to_retrieve"]
            )
            default_config["hot_reply_threshold"] = self.config.get(
                "tieba_hot_reply_threshold", default_config["hot_reply_threshold"]
            )
            default_config["hot_agree_threshold"] = self.config.get(
                "tieba_hot_agree_threshold", default_config["hot_agree_threshold"]
            )

            # 加载管理员列表
            admin_from_config = self.config.get("tieba_admin_users", [])
            if admin_from_config:
                default_config["admin_users"] = [str(u) for u in admin_from_config]

            # 加载贴吧-群组映射
            forum_groups_from_config = self.config.get("tieba_forum_groups", {})
            if forum_groups_from_config:
                # 转换格式: {贴吧名: [群号]} -> {贴吧名: [群号列表]}
                default_config["forum_groups"] = {
                    k: [str(g) for g in v]
                    for k, v in forum_groups_from_config.items()
                }

        # 加载订阅配置（动态修改的）
        if os.path.exists(self.subscription_file):
            try:
                with open(self.subscription_file, 'r', encoding='utf-8') as f:
                    sub_data = json.load(f)
                    # 合并订阅配置
                    for forum, groups in sub_data.get("forum_groups", {}).items():
                        if forum not in default_config["forum_groups"]:
                            default_config["forum_groups"][forum] = []
                        for group in groups:
                            group_str = str(group)
                            if group_str not in default_config["forum_groups"][forum]:
                                default_config["forum_groups"][forum].append(group_str)
            except json.JSONDecodeError as e:
                logger.error(f"订阅配置文件JSON格式错误: {e}")
            except Exception as e:
                logger.error(f"加载订阅配置失败: {e}")

        # 应用配置
        self.check_interval_seconds = default_config["check_interval_seconds"]
        self.threads_to_retrieve = default_config["threads_to_retrieve"]
        self.hot_reply_threshold = default_config["hot_reply_threshold"]
        self.hot_agree_threshold = default_config["hot_agree_threshold"]
        self.admin_users = default_config["admin_users"]
        self.forum_groups: Dict[str, List[str]] = default_config["forum_groups"]
        self.group_origins = default_config.get("group_origins", {})

        # 保存配置
        self._save_config()

    async def _save_config_async(self):
        """异步保存配置到文件（带锁）"""
        config_data = {
            "check_interval_seconds": self.check_interval_seconds,
            "threads_to_retrieve": self.threads_to_retrieve,
            "hot_reply_threshold": self.hot_reply_threshold,
            "hot_agree_threshold": self.hot_agree_threshold,
            "admin_users": self.admin_users,
            "forum_groups": self.forum_groups,
            "group_origins": self.group_origins
        }

        async with self._file_lock:
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=4)
            except Exception as e:
                logger.error(f"保存配置文件失败: {e}")

    def _save_config(self):
        """同步保存配置到文件"""
        config_data = {
            "check_interval_seconds": self.check_interval_seconds,
            "threads_to_retrieve": self.threads_to_retrieve,
            "hot_reply_threshold": self.hot_reply_threshold,
            "hot_agree_threshold": self.hot_agree_threshold,
            "admin_users": self.admin_users,
            "forum_groups": self.forum_groups,
            "group_origins": self.group_origins
        }

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

    async def _save_subscription_async(self):
        """异步保存订阅配置（带锁）"""
        async with self._file_lock:
            try:
                with open(self.subscription_file, 'w', encoding='utf-8') as f:
                    json.dump({"forum_groups": self.forum_groups}, f, ensure_ascii=False, indent=4)
            except Exception as e:
                logger.error(f"保存订阅配置失败: {e}")

    def _save_subscription(self):
        """同步保存订阅配置"""
        try:
            with open(self.subscription_file, 'w', encoding='utf-8') as f:
                json.dump({"forum_groups": self.forum_groups}, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存订阅配置失败: {e}")

    def _init_scheduler(self):
        """初始化定时任务"""
        if not self.forum_groups:
            logger.warning("没有配置任何贴吧监控")
            return

        # 检查是否有调度器
        if not hasattr(self.context, 'scheduler') or self.context.scheduler is None:
            logger.warning("AstrBot 调度器不可用，使用异步任务替代")
            # 创建异步任务替代调度器
            asyncio.create_task(self._async_monitor())
            return

        # 移除旧任务
        try:
            self.context.scheduler.remove_job("tieba_monitor")
        except Exception:
            pass
        try:
            self.context.scheduler.remove_job("tieba_daily_report")
        except Exception:
            pass

        # 添加定时检查任务
        self.context.scheduler.add_job(
            self._check_all_forums,
            "interval",
            seconds=self.check_interval_seconds,
            id="tieba_monitor",
            replace_existing=True
        )

        # 添加每日报告任务 (每天0点)
        self.context.scheduler.add_job(
            self._daily_report,
            "cron",
            hour=0,
            minute=0,
            id="tieba_daily_report",
            replace_existing=True
        )

        logger.info(f"定时任务已启动: 检查间隔{self.check_interval_seconds}秒")

    async def _async_monitor(self):
        """异步监控任务（当调度器不可用时使用）"""
        logger.info("启动异步监控任务")
        while True:
            try:
                await self._check_all_forums()
            except Exception as e:
                logger.error(f"监控任务出错: {e}")
            await asyncio.sleep(self.check_interval_seconds)

    async def initialize(self):
        """插件初始化时执行"""
        # 延迟初始化定时任务，确保scheduler已准备好
        await asyncio.sleep(2)
        self._init_scheduler()
        # 延迟执行首次检查
        await asyncio.sleep(5)
        await self._check_all_forums()

    async def terminate(self):
        """插件卸载时清理资源"""
        await self.tieba_client.close()

    # ========== 权限检查 ==========

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        """检查用户是否为管理员"""
        user_id = str(event.get_sender_id())

        # 检查是否在管理员列表中
        if user_id in self.admin_users:
            return True

        # 检查是否为群管理员
        return event.is_admin()

    def _get_group_id(self, event: AstrMessageEvent) -> Optional[str]:
        """获取群组ID"""
        group_id = event.get_group_id()
        if group_id:
            return str(group_id)
        return None

    def _save_group_origin(self, event: AstrMessageEvent):
        """保存群的 unified_msg_origin"""
        group_id = self._get_group_id(event)
        if group_id and hasattr(event, 'unified_msg_origin'):
            self.group_origins[group_id] = event.unified_msg_origin
            self._save_config()

    def _get_session_for_group(self, group_id: str) -> str:
        """获取群的会话标识"""
        if group_id in self.group_origins:
            return self.group_origins[group_id]
        return group_id

    # ========== 定时任务 ==========

    async def _check_all_forums(self):
        """检查所有订阅的贴吧"""
        for forum_name in list(self.forum_groups.keys()):
            try:
                await self._check_forum(forum_name)
            except Exception as e:
                logger.error(f"检查贴吧[{forum_name}]时出错: {e}")
            # 添加延迟避免请求过快
            await asyncio.sleep(random.uniform(2, 4))

    async def _check_forum(self, forum_name: str):
        """检查单个贴吧的新帖子"""
        notify_groups = self.forum_groups.get(forum_name, [])
        if not notify_groups:
            return

        # 获取新帖子
        threads = await self.tieba_client.get_threads(forum_name)
        if not threads:
            return

        # 处理帖子数据
        new_threads = await self._process_threads(forum_name, threads)

        if new_threads:
            # 发送通知
            await self._send_notifications(new_threads, notify_groups)
            logger.info(f"贴吧[{forum_name}]发现{len(new_threads)}条新帖子")

    async def _process_threads(self, forum_name: str, threads: List[Dict]) -> List[Dict]:
        """处理帖子数据，过滤已存在的帖子"""
        # 加载已有数据
        output_path = os.path.join(self.data_dir, f"{forum_name}.json")
        existing_tids: Set[str] = set()
        existing_threads: List[Dict] = []

        if os.path.exists(output_path):
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    existing_threads = json.load(f)
                    existing_tids = {str(t["tid"]) for t in existing_threads}
            except json.JSONDecodeError as e:
                logger.error(f"贴吧[{forum_name}]数据文件JSON格式错误: {e}")
            except Exception as e:
                logger.error(f"读取贴吧[{forum_name}]数据文件失败: {e}")

        new_threads: List[Dict] = []
        hot_threads: List[Dict] = []

        for thread in threads[:self.threads_to_retrieve]:
            tid = str(thread.get("tid"))
            if tid in existing_tids:
                continue

            # 检查是否为热帖
            hot_info = self.tracker.check_hot_thread(
                thread,
                self.hot_reply_threshold,
                self.hot_agree_threshold
            )
            if hot_info:
                hot_threads.append(hot_info)

            new_threads.append(thread)
            existing_threads.append(thread)

        # 保存数据（带锁）
        if new_threads:
            async with self._file_lock:
                try:
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(existing_threads, f, ensure_ascii=False, indent=4)

                    # 更新统计
                    self.tracker.update_stats(forum_name, len(new_threads))
                except Exception as e:
                    logger.error(f"保存贴吧[{forum_name}]数据失败: {e}")

        # 发送热帖通知
        if hot_threads:
            notify_groups = self.forum_groups.get(forum_name, [])
            for hot_info in hot_threads:
                await self._send_hot_notification(hot_info, notify_groups)

        return new_threads

    async def _send_notifications(self, threads: List[Dict], group_ids: List[str]):
        """发送新帖通知到多个群"""
        for group_id in group_ids:
            for thread in threads:
                try:
                    await self._send_thread(group_id, thread)
                    await asyncio.sleep(random.uniform(2, 4))
                except Exception as e:
                    logger.error(f"发送通知到群{group_id}失败: {e}")

    async def _send_thread(self, group_id: str, thread_info: Dict, is_manual: bool = False):
        """发送单个帖子通知"""
        try:
            chain = []

            # 前缀
            prefix = "【手动刷新】\n" if is_manual else ""

            # 标题
            tieba_name = thread_info.get('tieba_name', '未知贴吧')
            title = thread_info.get('title', '无标题')
            if len(title) > 50:
                title = title[:47] + "..."

            chain.append(Comp.Plain(f"{prefix}【{tieba_name}吧】{title}\n"))

            # 作者
            author = thread_info.get('author_id', '未知作者')
            chain.append(Comp.Plain(f"👤 作者: {author}\n"))

            # 内容摘要
            content = thread_info.get('text', '')
            if len(content) > 100:
                content = content[:97] + "..."
            if content:
                chain.append(Comp.Plain(f"📝 内容: {content}\n"))

            # 热度信息
            reply_num = thread_info.get('reply_num', 0)
            agree_num = thread_info.get('agree', 0)
            if reply_num > 0 or agree_num > 0:
                chain.append(Comp.Plain(f"💬 回复:{reply_num} | 👍 点赞:{agree_num}\n"))

            # 链接
            url = thread_info.get('url', '')
            if url:
                chain.append(Comp.Plain(f"🔗 链接: {url}\n"))

            # 发布时间
            create_time = thread_info.get('create_time', '')
            if create_time:
                chain.append(Comp.Plain(f"🕐 发布时间: {create_time}"))

            # 图片
            images = thread_info.get('images', [])
            for image_url in images[:3]:
                try:
                    if image_url and image_url.startswith(('http://', 'https://')):
                        chain.append(Comp.Image.fromURL(image_url))
                except Exception as img_e:
                    logger.warning(f"添加图片到消息时出错: {img_e}")

            # 发送消息
            await self.context.send_message(self._get_session_for_group(group_id), MessageChain(chain))
            logger.info(f"帖子通知已发送到群 {group_id}: {title}")

        except Exception as e:
            logger.error(f"发送通知到群 {group_id} 时出错: {e}")

    async def _send_hot_notification(self, hot_info: Dict, group_ids: List[str]):
        """发送热帖通知"""
        for group_id in group_ids:
            try:
                hot_type = hot_info.get("type", "new")
                tieba_name = hot_info.get("tieba_name", "")
                title = hot_info.get("title", "")
                reply_num = hot_info.get("reply_num", 0)
                agree_num = hot_info.get("agree", 0)
                url = hot_info.get("url", "")

                if len(title) > 40:
                    title = title[:37] + "..."

                chain = []

                if hot_type == "new":
                    chain.append(Comp.Plain(f"🔥【热帖预警】🔥\n"))
                    chain.append(Comp.Plain(f"【{tieba_name}吧】{title}\n"))
                    chain.append(Comp.Plain(f"💬 回复: {reply_num} | 👍 点赞: {agree_num}\n"))
                    chain.append(Comp.Plain(f"🔗 链接: {url}"))
                else:
                    old_reply = hot_info.get("old_reply_num", 0)
                    old_agree = hot_info.get("old_agree", 0)
                    reply_diff = reply_num - old_reply
                    agree_diff = agree_num - old_agree

                    chain.append(Comp.Plain(f"📈【热帖升温】📈\n"))
                    chain.append(Comp.Plain(f"【{tieba_name}吧】{title}\n"))
                    chain.append(Comp.Plain(
                        f"💬 回复: {reply_num}(+{reply_diff}) | "
                        f"👍 点赞: {agree_num}(+{agree_diff})\n"
                    ))
                    chain.append(Comp.Plain(f"🔗 链接: {url}"))

                await self.context.send_message(self._get_session_for_group(group_id), MessageChain(chain))
                logger.info(f"热帖通知已发送到群 {group_id}: {title}")
                await asyncio.sleep(random.uniform(2, 3))

            except Exception as e:
                logger.error(f"发送热帖通知到群 {group_id} 时出错: {e}")

    async def _daily_report(self):
        """每日数据报告"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        daily_stats = self.tracker.get_daily_stats(1)
        ranking = self.tracker.get_forum_ranking()
        hot_threads = self.tracker.get_hot_threads_list(5)

        sent_groups: Set[str] = set()

        for forum_name in self.forum_groups:
            groups = self.forum_groups.get(forum_name, [])

            for group_id in groups:
                if group_id in sent_groups:
                    continue

                try:
                    msg = self._build_report(yesterday, daily_stats, ranking, hot_threads)
                    await self._send_plain_text(group_id, msg)
                    sent_groups.add(group_id)
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"发送每日报告到群{group_id}失败: {e}")

    def _build_report(self, yesterday: str, daily_stats: Dict, ranking: List[Dict], hot_threads: List[Dict]) -> str:
        """构建报告消息"""
        lines = []
        lines.append(f"📊 每日数据报告 ({yesterday})")
        lines.append("=" * 25)
        lines.append("")

        # 昨日统计
        lines.append("📈 昨日发帖统计:")
        yesterday_data = daily_stats.get(yesterday, {})
        if yesterday_data:
            for name, count in sorted(yesterday_data.items(), key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f"  • {name}: {count}帖")
        else:
            lines.append("  暂无数据")

        lines.append("")
        lines.append("🏆 活跃度排行 TOP5:")
        if ranking:
            for i, forum in enumerate(ranking[:5], 1):
                lines.append(f"  {i}. {forum['name']}: {forum['total_posts']}帖")
        else:
            lines.append("  暂无数据")

        lines.append("")
        lines.append("🔥 热门帖子 TOP5:")
        if hot_threads:
            for i, thread in enumerate(hot_threads[:5], 1):
                title = thread.get('title', '')[:15]
                if len(thread.get('title', '')) > 15:
                    title += "..."
                reply = thread.get('reply_num', 0)
                agree = thread.get('agree', 0)
                lines.append(f"  {i}. [{thread.get('tieba_name', '')}]{title}")
                lines.append(f"     回复:{reply} 点赞:{agree}")
        else:
            lines.append("  暂无热帖")

        return "\n".join(lines)

    async def _send_plain_text(self, group_id: str, text: str):
        """发送纯文本消息"""
        try:
            chain = [Comp.Plain(text)]
            await self.context.send_message(self._get_session_for_group(group_id), MessageChain(chain))
        except Exception as e:
            logger.error(f"发送消息到群 {group_id} 时出错: {e}")

    # ========== 命令处理 ==========

    @filter.command("tb菜单")
    async def cmd_menu(self, event: AstrMessageEvent):
        """显示主菜单"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        msg = """🤖 贴吧观察者 - 主菜单

【查询命令】
📊 /tb统计 - 查看发帖统计
📈 /tb排行 - 查看贴吧活跃度排行
🔥 /tb热帖 - 查看热门帖子
📜 /tb历史 <贴吧名> [数量] - 查看历史帖子
🔍 /tb搜索 <关键词> - 搜索帖子

【管理命令】
➕ /tb订阅 <贴吧名> - 订阅新贴吧
➕ /tb订阅 <群号> <贴吧名> - 为指定群订阅
➖ /tb退订 <贴吧名> - 取消订阅
➖ /tb退订 <群号> <贴吧名> - 为指定群退订
📋 /tb列表 - 查看当前群订阅
📋 /tb全部订阅 - 查看所有群的订阅
🔄 /tb刷新 <贴吧名> - 手动刷新指定贴吧
🔎 /tb检查 - 立即检查所有贴吧

💡 提示: 发送 /tb帮助 查看详细说明"""
        yield event.plain_result(msg)

    @filter.command("tb帮助")
    async def cmd_help(self, event: AstrMessageEvent):
        """显示详细帮助"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        msg = """📖 贴吧观察者 - 详细使用说明

【查询命令】
1️⃣ /tb统计 - 显示最近7天的发帖统计数据
2️⃣ /tb排行 - 显示所有监控贴吧的活跃度排行
3️⃣ /tb热帖 - 显示当前热门帖子(回复>100或点赞>1000)
4️⃣ /tb历史 <贴吧名> [数量] - 查看指定贴吧的历史帖子
   例: /tb历史 鸣潮
   例: /tb历史 鸣潮 10
5️⃣ /tb搜索 <关键词> - 搜索帖子标题和内容
   例: /tb搜索 攻略

【管理命令】
6️⃣ /tb订阅 <贴吧名> - 在当前群订阅新贴吧
   例: /tb订阅 鸣潮
7️⃣ /tb订阅 <群号> <贴吧名> - 为指定群订阅贴吧(超级管理员)
   例: /tb订阅 123456789 鸣潮
8️⃣ /tb退订 <贴吧名> - 在当前群取消贴吧订阅
   例: /tb退订 鸣潮
9️⃣ /tb退订 <群号> <贴吧名> - 为指定群退订贴吧(超级管理员)
   例: /tb退订 123456789 鸣潮
🔟 /tb列表 - 查看当前群订阅的所有贴吧
1️⃣1️⃣ /tb全部订阅 - 查看所有群的订阅情况(超级管理员)
1️⃣2️⃣ /tb刷新 <贴吧名> - 手动刷新指定贴吧的最新帖子
   例: /tb刷新 鸣潮
1️⃣3️⃣ /tb检查 - 立即检查所有订阅的贴吧"""
        yield event.plain_result(msg)

    @filter.command("tb统计")
    async def cmd_stats(self, event: AstrMessageEvent):
        """查看发帖统计"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        daily_stats = self.tracker.get_daily_stats(7)

        if not daily_stats or all(not v for v in daily_stats.values()):
            yield event.plain_result("📊 暂无统计数据")
            return

        lines = []
        lines.append("📊 最近7天发帖统计")
        lines.append("=" * 20)
        total = 0

        for date, forums in sorted(daily_stats.items()):
            day_total = sum(forums.values()) if forums else 0
            total += day_total
            lines.append(f"{date[-5:]}: {day_total}帖")

        lines.append("=" * 20)
        lines.append(f"总计: {total}帖")

        yield event.plain_result("\n".join(lines))

    @filter.command("tb排行")
    async def cmd_rank(self, event: AstrMessageEvent):
        """查看贴吧活跃度排行"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        ranking = self.tracker.get_forum_ranking()

        if not ranking:
            yield event.plain_result("📈 暂无排行数据")
            return

        lines = []
        lines.append("📈 贴吧活跃度排行 TOP10")
        lines.append("=" * 25)

        for i, forum in enumerate(ranking[:10], 1):
            name = forum['name']
            posts = forum['total_posts']
            bar = "█" * min(int(posts / 10), 10)
            lines.append(f"{i}. {name}")
            lines.append(f"   {bar} {posts}帖")

        yield event.plain_result("\n".join(lines))

    @filter.command("tb热帖")
    async def cmd_hot(self, event: AstrMessageEvent):
        """查看热门帖子"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        hot_threads = self.tracker.get_hot_threads_list(10)

        if not hot_threads:
            yield event.plain_result("🔥 暂无热帖数据")
            return

        lines = []
        lines.append("🔥 热门帖子 TOP10")
        lines.append("=" * 25)

        for i, thread in enumerate(hot_threads, 1):
            title = thread.get('title', '')[:15]
            if len(thread.get('title', '')) > 15:
                title += "..."
            tieba = thread.get('tieba_name', '')
            reply = thread.get('reply_num', 0)
            agree = thread.get('agree', 0)

            heat = "🔥" * min((reply + agree) // 1000 + 1, 3)
            lines.append(f"{i}. [{tieba}]{title}")
            lines.append(f"   回复:{reply} 点赞:{agree} {heat}")

        yield event.plain_result("\n".join(lines))

    @filter.command("tb历史")
    async def cmd_history(self, event: AstrMessageEvent, forum_name: str = "", limit: str = "5"):
        """查看历史帖子"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        if not forum_name:
            yield event.plain_result("❌ 请指定贴吧名\n例: /tb历史 鸣潮\n例: /tb历史 鸣潮 10")
            return

        # 解析limit参数
        try:
            limit_num = int(limit)
        except ValueError:
            limit_num = 5

        limit_num = min(max(limit_num, 1), 20)
        file_path = os.path.join(self.data_dir, f"{forum_name}.json")

        if not os.path.exists(file_path):
            yield event.plain_result(f"❌ 未找到【{forum_name}吧】的数据")
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                threads = json.load(f)

            if not threads:
                yield event.plain_result(f"📭 【{forum_name}吧】暂无帖子")
                return

            recent = threads[-limit_num:]
            lines = []
            lines.append(f"📜 【{forum_name}吧】最近{len(recent)}条")
            lines.append("=" * 25)

            for i, thread in enumerate(reversed(recent), 1):
                title = thread.get('title', '')[:20]
                if len(thread.get('title', '')) > 20:
                    title += "..."
                author = thread.get('author_id', '未知')
                time = thread.get('create_time', '')
                reply = thread.get('reply_num', 0)

                lines.append(f"{i}. {title}")
                lines.append(f"   👤{author} 💬{reply} 🕐{time}")

            yield event.plain_result("\n".join(lines))

        except json.JSONDecodeError:
            yield event.plain_result("❌ 数据文件格式错误")
        except Exception as e:
            logger.error(f"读取历史失败: {e}")
            yield event.plain_result("❌ 读取数据失败")

    @filter.command("tb搜索")
    async def cmd_search(self, event: AstrMessageEvent, keyword: str = ""):
        """搜索帖子"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        if not keyword:
            yield event.plain_result("❌ 请指定搜索关键词\n例: /tb搜索 攻略")
            return

        results = []

        for filename in os.listdir(self.data_dir):
            if not filename.endswith('.json') or filename in ['hot_threads.json', 'stats.json', 'config.json', 'subscription.json']:
                continue

            forum_name = filename[:-5]
            file_path = os.path.join(self.data_dir, filename)

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    threads = json.load(f)

                for thread in threads:
                    title = thread.get('title', '')
                    content = thread.get('text', '')

                    if keyword.lower() in title.lower() or keyword.lower() in content.lower():
                        results.append({
                            'tieba': forum_name,
                            'title': title,
                            'author': thread.get('author_id', ''),
                            'time': thread.get('create_time', '')
                        })

                        if len(results) >= 10:
                            break

                if len(results) >= 10:
                    break

            except json.JSONDecodeError:
                logger.warning(f"搜索时JSON解析失败: {file_path}")
            except Exception:
                continue

        if not results:
            yield event.plain_result(f'🔍 未找到包含"{keyword}"的帖子')
            return

        lines = []
        lines.append(f'🔍 搜索"{keyword}" 结果({len(results)}条)')
        lines.append("=" * 25)

        for i, r in enumerate(results, 1):
            title = r['title'][:18]
            if len(r['title']) > 18:
                title += "..."
            lines.append(f"{i}. [{r['tieba']}]{title}")
            lines.append(f"   👤{r['author']} 🕐{r['time']}")

        yield event.plain_result("\n".join(lines))

    @filter.command("tb订阅")
    async def cmd_subscribe(self, event: AstrMessageEvent, arg1: str = "", arg2: str = ""):
        """订阅贴吧 - 支持两种格式：/tb订阅 贴吧名 或 /tb订阅 群号 贴吧名"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        if not arg1:
            yield event.plain_result("❌ 参数错误\n用法1: /tb订阅 贴吧名\n用法2: /tb订阅 群号 贴吧名")
            return

        # 判断格式
        if arg2:  # /tb订阅 群号 贴吧名
            group_id = str(arg1)
            forum_name = arg2
        else:  # /tb订阅 贴吧名
            group_id = self._get_group_id(event)
            forum_name = arg1
            if not group_id:
                yield event.plain_result("❌ 该命令只能在群聊中使用，或在命令中指定群号")
                return

        if forum_name not in self.forum_groups:
            self.forum_groups[forum_name] = []

        if group_id in self.forum_groups[forum_name]:
            yield event.plain_result(f"⚠️ 群{group_id}已订阅【{forum_name}吧】")
            return

        self.forum_groups[forum_name].append(group_id)
        await self._save_subscription_async()

        # 重新初始化定时任务
        self._init_scheduler()

        yield event.plain_result(f"✅ 成功为群{group_id}订阅【{forum_name}吧】\n新帖子将推送到该群")

    @filter.command("tb退订")
    async def cmd_unsubscribe(self, event: AstrMessageEvent, arg1: str = "", arg2: str = ""):
        """退订贴吧 - 支持两种格式：/tb退订 贴吧名 或 /tb退订 群号 贴吧名"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        if not arg1:
            yield event.plain_result("❌ 参数错误\n用法1: /tb退订 贴吧名\n用法2: /tb退订 群号 贴吧名")
            return

        # 判断格式
        if arg2:  # /tb退订 群号 贴吧名
            group_id = str(arg1)
            forum_name = arg2
        else:  # /tb退订 贴吧名
            group_id = self._get_group_id(event)
            forum_name = arg1
            if not group_id:
                yield event.plain_result("❌ 该命令只能在群聊中使用，或在命令中指定群号")
                return

        if forum_name not in self.forum_groups:
            yield event.plain_result(f"❌ 【{forum_name}吧】未被监控")
            return

        if group_id not in self.forum_groups[forum_name]:
            yield event.plain_result(f"⚠️ 群{group_id}未订阅【{forum_name}吧】")
            return

        self.forum_groups[forum_name].remove(group_id)

        # 如果没有群组订阅，删除该贴吧
        if not self.forum_groups[forum_name]:
            del self.forum_groups[forum_name]

        await self._save_subscription_async()
        yield event.plain_result(f"✅ 已取消群{group_id}对【{forum_name}吧】的订阅")

    @filter.command("tb列表")
    async def cmd_list(self, event: AstrMessageEvent):
        """查看当前群订阅列表"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        group_id = self._get_group_id(event)
        if not group_id:
            yield event.plain_result("❌ 该命令只能在群聊中使用")
            return

        subscribed = []
        for name, groups in self.forum_groups.items():
            if group_id in groups:
                subscribed.append(name)

        if not subscribed:
            yield event.plain_result("📭 本群暂无订阅任何贴吧")
            return

        lines = []
        lines.append("📋 本群订阅列表")
        lines.append("=" * 20)
        for i, name in enumerate(subscribed, 1):
            lines.append(f"{i}. {name}吧")
        lines.append("=" * 20)
        lines.append(f"共 {len(subscribed)} 个")

        yield event.plain_result("\n".join(lines))

    @filter.command("tb全部订阅")
    async def cmd_all_subscriptions(self, event: AstrMessageEvent):
        """查看所有群的订阅情况（超级管理员命令）"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        if not self.forum_groups:
            yield event.plain_result("📭 暂无订阅任何贴吧")
            return

        lines = []
        lines.append("📋 全部订阅情况")
        lines.append("=" * 30)

        for forum_name, groups in sorted(self.forum_groups.items()):
            lines.append(f"\n【{forum_name}吧】")
            if groups:
                for i, group_id in enumerate(groups, 1):
                    lines.append(f"  {i}. 群{group_id}")
            else:
                lines.append("  暂无群订阅")

        lines.append("\n" + "=" * 30)
        lines.append(f"总计: {len(self.forum_groups)}个贴吧")

        yield event.plain_result("\n".join(lines))

    @filter.command("tb刷新")
    async def cmd_refresh(self, event: AstrMessageEvent, forum_name: str = ""):
        """手动刷新指定贴吧"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        if not forum_name:
            yield event.plain_result("❌ 请指定贴吧名\n例: /tb刷新 鸣潮")
            return

        group_id = self._get_group_id(event)
        if not group_id:
            yield event.plain_result("❌ 该命令只能在群聊中使用")
            return

        # 检查是否订阅
        if forum_name not in self.forum_groups or group_id not in self.forum_groups.get(forum_name, []):
            yield event.plain_result(f"❌ 本群未订阅【{forum_name}吧】")
            return

        yield event.plain_result(f"🔄 正在刷新【{forum_name}吧】...")

        try:
            # 获取最新帖子
            threads = await self.tieba_client.get_threads(forum_name)
            if not threads:
                yield event.plain_result(f"⚠️ 未获取到【{forum_name}吧】的帖子")
                return

            # 获取第一条帖子发送
            latest = threads[0]
            await self._send_thread(group_id, latest, is_manual=True)

        except Exception as e:
            logger.error(f"刷新贴吧失败: {e}")
            yield event.plain_result(f"❌ 刷新失败: {str(e)}")

    @filter.command("tb检查")
    async def cmd_check(self, event: AstrMessageEvent):
        """立即检查所有贴吧"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        if not self.forum_groups:
            yield event.plain_result("❌ 未配置任何贴吧监控")
            return

        forums = list(self.forum_groups.keys())
        yield event.plain_result(f"🔎 开始检查所有贴吧（共{len(forums)}个）...")

        try:
            success_count = 0
            fail_count = 0

            for forum_name in forums:
                try:
                    await self._check_forum(forum_name)
                    success_count += 1
                except Exception as e:
                    logger.error(f"检查贴吧[{forum_name}]失败: {e}")
                    fail_count += 1
                await asyncio.sleep(2)

            result_msg = f"检查完成！\n✅ 成功: {success_count}个\n❌ 失败: {fail_count}个"
            yield event.plain_result(result_msg)

        except Exception as e:
            logger.error(f"手动检查贴吧失败: {e}")
            yield event.plain_result(f"❌ 检查失败: {str(e)}")
