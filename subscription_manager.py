"""
订阅管理模块
支持 forum_groups 格式：{贴吧名: [群号列表]}
"""

import asyncio
import copy
import json
import os
from typing import Dict, List, Optional
from filelock import FileLock

from astrbot.api import logger


class SubscriptionManager:
    """订阅管理器"""
    
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.config_file = os.path.join(data_dir, "config.json")
        self._file_lock = FileLock(os.path.join(data_dir, "config.lock"))
        self._async_lock = asyncio.Lock()
        
        # 数据存储
        self._forum_groups: Dict[str, List[str]] = {}
        
        self._load()
    
    def _load_sync(self):
        """同步加载配置（在线程中执行）"""
        with self._file_lock:
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    return data
                except (json.JSONDecodeError, IOError, OSError) as e:
                    logger.error(f"加载订阅配置失败: {e}")
            return {}
    
    def _load(self):
        """加载配置"""
        data = self._load_sync()
        if data:
            # 加载forum_groups格式
            self._forum_groups = data.get("forum_groups", {})
    
    async def _load_async(self):
        """异步加载配置"""
        import asyncio
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, self._load_sync)
        if data:
            async with self._async_lock:
                self._forum_groups = data.get("forum_groups", {})
    
    def _save_sync(self) -> bool:
        """同步保存配置（在线程中执行）"""
        with self._file_lock:
            try:
                config = {}
                if os.path.exists(self.config_file):
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                
                config["forum_groups"] = self._forum_groups
                
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                return True
            except (IOError, OSError, TypeError) as e:
                logger.error(f"保存订阅配置失败: {e}")
                return False
    
    def _save(self):
        """保存配置"""
        return self._save_sync()
    
    async def _save_async(self) -> bool:
        """异步保存配置"""
        import asyncio
        loop = asyncio.get_event_loop()
        async with self._async_lock:
            return await loop.run_in_executor(None, self._save_sync)
    
    def subscribe(self, forum: str, group: str) -> bool:
        """订阅贴吧到群"""
        if forum not in self._forum_groups:
            self._forum_groups[forum] = []
        if group not in self._forum_groups[forum]:
            self._forum_groups[forum].append(group)
        
        return self._save()
    
    def unsubscribe(self, forum: str, group: str) -> bool:
        """取消订阅"""
        if forum in self._forum_groups and group in self._forum_groups[forum]:
            self._forum_groups[forum].remove(group)
            if not self._forum_groups[forum]:
                del self._forum_groups[forum]
        
        return self._save()
    
    def remove_forum(self, forum: str) -> bool:
        """删除整个贴吧订阅"""
        if forum in self._forum_groups:
            del self._forum_groups[forum]
            return self._save()
        return False
    
    def remove_group(self, group: str) -> bool:
        """删除整个群的订阅"""
        changed = False
        for forum in list(self._forum_groups.keys()):
            if group in self._forum_groups[forum]:
                self._forum_groups[forum].remove(group)
                if not self._forum_groups[forum]:
                    del self._forum_groups[forum]
                changed = True
        
        if changed:
            return self._save()
        return False
    
    def get_forum_groups(self, forum: str) -> List[str]:
        """获取订阅某贴吧的所有群"""
        return self._forum_groups.get(forum, []).copy()
    
    def get_group_forums(self, group: str) -> List[str]:
        """获取某群订阅的所有贴吧"""
        forums = []
        for forum, groups in self._forum_groups.items():
            if group in groups:
                forums.append(forum)
        return forums
    
    def get_all_forums(self) -> List[str]:
        """获取所有订阅的贴吧"""
        return list(self._forum_groups.keys())
    
    def get_all_groups(self) -> List[str]:
        """获取所有订阅的群"""
        groups = set()
        for gs in self._forum_groups.values():
            groups.update(gs)
        return list(groups)
    
    def is_subscribed(self, forum: str, group: str) -> bool:
        """检查是否已订阅"""
        return group in self._forum_groups.get(forum, [])
    
    def get_subscription_count(self) -> dict:
        """获取订阅统计"""
        total_subs = sum(len(groups) for groups in self._forum_groups.values())
        return {
            "forum_count": len(self._forum_groups),
            "group_count": len(self.get_all_groups()),
            "total_subscriptions": total_subs
        }
    
    @property
    def forum_groups(self) -> Dict[str, List[str]]:
        """获取所有订阅"""
        return copy.deepcopy(self._forum_groups)
    
    @property
    def group_forums(self) -> Dict[str, List[str]]:
        """兼容旧代码 - 以group_forums格式获取所有订阅"""
        result = {}
        for forum, groups in self._forum_groups.items():
            for group in groups:
                if group not in result:
                    result[group] = []
                if forum not in result[group]:
                    result[group].append(forum)
        return result
