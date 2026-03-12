"""
热帖追踪和统计模块
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from astrbot.api import logger


class HotThreadTracker:
    """热帖追踪器 - 使用锁保护并发写入"""
    
    def __init__(self, data_dir: str):
        """
        初始化热帖追踪器
        
        Args:
            data_dir: 数据目录路径
        """
        self.data_dir = data_dir
        self.hot_threads_file = os.path.join(data_dir, "hot_threads.json")
        self.stats_file = os.path.join(data_dir, "stats.json")
        self.hot_threads: Dict[str, Dict] = self._load_hot_threads()
        self.stats: Dict = self._load_stats()
        # 异步锁，保护并发写入
        self._lock = asyncio.Lock()
    
    def _load_hot_threads(self) -> Dict[str, Dict]:
        """加载已记录的热帖数据"""
        if os.path.exists(self.hot_threads_file):
            try:
                with open(self.hot_threads_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError, OSError) as e:
                logger.error(f"加载热帖数据失败: {e}")
        return {}
    
    def _load_stats(self) -> Dict:
        """加载统计数据"""
        default_stats = {
            "daily_posts": {},
            "forum_activity": {}
        }
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # 确保返回的数据结构完整
                    for key in default_stats:
                        if key not in loaded:
                            loaded[key] = default_stats[key]
                    return loaded
            except (json.JSONDecodeError, IOError, OSError) as e:
                logger.error(f"加载统计数据失败: {e}")
        return default_stats
    
    def _save_hot_threads(self):
        """保存热帖数据"""
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.hot_threads_file, 'w', encoding='utf-8') as f:
                json.dump(self.hot_threads, f, ensure_ascii=False, indent=4)
        except (IOError, OSError, TypeError) as e:
            logger.error(f"保存热帖数据失败: {e}")

    def _save_stats(self):
        """保存统计数据"""
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=4)
        except (IOError, OSError, TypeError) as e:
            logger.error(f"保存统计数据失败: {e}")
    
    def check_hot_thread(
        self,
        thread_info: Dict,
        reply_threshold: int = 100,
        agree_threshold: int = 1000
    ) -> Optional[Dict]:
        """
        检查帖子是否成为热帖
        
        Args:
            thread_info: 帖子信息
            reply_threshold: 回复数阈值
            agree_threshold: 点赞数阈值
            
        Returns:
            热帖信息字典，如果不是热帖返回None
        """
        tid = str(thread_info.get("tid", ""))
        tieba_name = thread_info.get("tieba_name", "")
        reply_num = thread_info.get("reply_num", 0)
        agree_num = thread_info.get("agree", 0)
        
        # 检查是否达到热帖阈值
        is_hot = reply_num >= reply_threshold or agree_num >= agree_threshold
        
        if not is_hot:
            return None
        
        hot_key = f"{tieba_name}_{tid}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if hot_key in self.hot_threads:
            # 已记录的热帖，检查是否有显著更新
            old_data = self.hot_threads[hot_key]
            old_reply = old_data.get("reply_num", 0)
            old_agree = old_data.get("agree", 0)
            
            # 如果数据有显著变化（回复+100或点赞+1000），再次提醒
            if (reply_num >= old_reply + 100) or (agree_num >= old_agree + 1000):
                self.hot_threads[hot_key].update({
                    "reply_num": reply_num,
                    "agree": agree_num,
                    "last_update": now
                })
                self._save_hot_threads()
                
                return {
                    "type": "update",
                    "tid": thread_info.get("tid"),
                    "title": thread_info.get("title"),
                    "tieba_name": tieba_name,
                    "author_id": thread_info.get("author_id"),
                    "url": thread_info.get("url"),
                    "reply_num": reply_num,
                    "agree": agree_num,
                    "old_reply_num": old_reply,
                    "old_agree": old_agree,
                    "first_detected": old_data.get("first_detected", now)
                }
            return None
        else:
            # 新热帖
            self.hot_threads[hot_key] = {
                "tid": tid,
                "tieba_name": tieba_name,
                "title": thread_info.get("title", ""),
                "reply_num": reply_num,
                "agree": agree_num,
                "first_detected": now,
                "last_update": now
            }
            self._save_hot_threads()
            
            return {
                "type": "new",
                "tid": thread_info.get("tid"),
                "title": thread_info.get("title"),
                "tieba_name": tieba_name,
                "author_id": thread_info.get("author_id"),
                "url": thread_info.get("url"),
                "reply_num": reply_num,
                "agree": agree_num,
                "first_detected": now
            }
    
    async def update_stats(self, tieba_name: str, new_posts_count: int = 1):
        """
        更新统计数据 - 使用异步锁保护并发写入
        
        Args:
            tieba_name: 贴吧名称
            new_posts_count: 新帖子数量
        """
        async with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")
            
            # 更新每日发帖统计
            if today not in self.stats["daily_posts"]:
                self.stats["daily_posts"][today] = {}
            if tieba_name not in self.stats["daily_posts"][today]:
                self.stats["daily_posts"][today][tieba_name] = 0
            self.stats["daily_posts"][today][tieba_name] += new_posts_count
            
            # 更新贴吧活跃度
            if tieba_name not in self.stats["forum_activity"]:
                self.stats["forum_activity"][tieba_name] = {
                    "total_posts": 0,
                    "first_seen": today,
                    "last_post": today
                }
            self.stats["forum_activity"][tieba_name]["total_posts"] += new_posts_count
            self.stats["forum_activity"][tieba_name]["last_post"] = today
            
            self._save_stats()

    async def update_forum_activity(self, tieba_name: str):
        """
        更新贴吧活跃度（仅更新最后访问时间，不增加计数）- 使用异步锁保护

        Args:
            tieba_name: 贴吧名称
        """
        async with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")

            # 更新贴吧活跃度
            if tieba_name not in self.stats["forum_activity"]:
                self.stats["forum_activity"][tieba_name] = {
                    "total_posts": 0,
                    "first_seen": today,
                    "last_post": today
                }
            else:
                self.stats["forum_activity"][tieba_name]["last_post"] = today

            self._save_stats()

    def get_daily_stats(self, days: int = 7) -> Dict[str, Dict]:
        """
        获取最近N天的统计
        
        Args:
            days: 天数
            
        Returns:
            每日统计数据
        """
        result = {}
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            result[date] = self.stats["daily_posts"].get(date, {})
        return result
    
    def get_forum_ranking(self) -> List[Dict]:
        """
        获取贴吧活跃度排行
        
        Returns:
            贴吧活跃度列表
        """
        forums = []
        for name, data in self.stats["forum_activity"].items():
            forums.append({
                "name": name,
                "total_posts": data.get("total_posts", 0),
                "last_post": data.get("last_post", "")
            })
        return sorted(forums, key=lambda x: x["total_posts"], reverse=True)
    
    def get_hot_threads_list(self, limit: int = 10) -> List[Dict]:
        """
        获取最近的热帖列表
        
        Args:
            limit: 数量限制
            
        Returns:
            热帖列表
        """
        # 清理过期热帖数据
        self._cleanup_old_hot_threads()
        
        threads = list(self.hot_threads.values())
        # 按最后更新时间排序
        threads.sort(key=lambda x: x.get("last_update", ""), reverse=True)
        return threads[:limit]
    
    def _cleanup_old_hot_threads(self, max_age_days: int = 30):
        """清理过期热帖数据
        
        Args:
            max_age_days: 最大保留天数
        """
        cutoff = (datetime.now() - timedelta(days=max_age_days)).strftime("%Y-%m-%d %H:%M:%S")
        to_remove = [k for k, v in self.hot_threads.items() 
                     if v.get("last_update", "") < cutoff]
        for k in to_remove:
            del self.hot_threads[k]
        if to_remove:
            self._save_hot_threads()
            logger.info(f"清理了 {len(to_remove)} 条过期热帖数据")
