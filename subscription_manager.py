"""
订阅管理模块
支持两种模式：
1. forum_groups: 贴吧对应群（默认）- {贴吧名: [群号列表]}
2. group_forums: 群对应贴吧 - {群号: [贴吧名列表]}
"""

import json
import os
from typing import Dict, List, Set, Optional
from filelock import FileLock


class SubscriptionManager:
    """订阅管理器"""
    
    # 订阅模式
    MODE_FORUM_GROUPS = "forum_groups"  # 贴吧对应群
    MODE_GROUP_FORUMS = "group_forums"  # 群对应贴吧
    
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.config_file = os.path.join(data_dir, "config.json")
        self.lock = FileLock(os.path.join(data_dir, "config.lock"))
        
        # 数据存储
        self._forum_groups: Dict[str, List[str]] = {}  # {贴吧: [群列表]}
        self._group_forums: Dict[str, List[str]] = {}  # {群: [贴吧列表]}
        self._mode: str = self.MODE_FORUM_GROUPS  # 当前模式
        
        self._load()
    
    def _load(self):
        """加载配置"""
        with self.lock:
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 加载模式
                    self._mode = data.get("subscription_mode", self.MODE_FORUM_GROUPS)
                    
                    # 加载forum_groups格式
                    self._forum_groups = data.get("forum_groups", {})
                    
                    # 加载group_forums格式
                    self._group_forums = data.get("group_forums", {})
                    
                    # 如果只有一种数据，自动转换另一种
                    if not self._group_forums and self._forum_groups:
                        self._sync_to_group_forums()
                    elif not self._forum_groups and self._group_forums:
                        self._sync_to_forum_groups()
                    
                except Exception as e:
                    print(f"加载订阅配置失败: {e}")
    
    def _save(self):
        """保存配置"""
        with self.lock:
            try:
                # 先读取现有配置
                config = {}
                if os.path.exists(self.config_file):
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                
                # 更新订阅相关配置
                config["subscription_mode"] = self._mode
                config["forum_groups"] = self._forum_groups
                config["group_forums"] = self._group_forums
                
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                return True
            except Exception as e:
                print(f"保存订阅配置失败: {e}")
                return False
    
    def _sync_to_group_forums(self):
        """将forum_groups同步到group_forums"""
        self._group_forums = {}
        for forum, groups in self._forum_groups.items():
            for group in groups:
                if group not in self._group_forums:
                    self._group_forums[group] = []
                if forum not in self._group_forums[group]:
                    self._group_forums[group].append(forum)
    
    def _sync_to_forum_groups(self):
        """将group_forums同步到forum_groups"""
        self._forum_groups = {}
        for group, forums in self._group_forums.items():
            for forum in forums:
                if forum not in self._forum_groups:
                    self._forum_groups[forum] = []
                if group not in self._forum_groups[forum]:
                    self._forum_groups[forum].append(group)
    
    def _sync(self):
        """双向同步两种格式的数据"""
        if self._mode == self.MODE_FORUM_GROUPS:
            self._sync_to_group_forums()
        else:
            self._sync_to_forum_groups()
    
    # ========== 模式相关 ==========
    
    @property
    def mode(self) -> str:
        """获取当前模式"""
        return self._mode
    
    def set_mode(self, mode: str) -> bool:
        """切换模式
        
        Args:
            mode: MODE_FORUM_GROUPS 或 MODE_GROUP_FORUMS
        
        Returns:
            是否成功
        """
        if mode not in [self.MODE_FORUM_GROUPS, self.MODE_GROUP_FORUMS]:
            return False
        
        if mode != self._mode:
            self._mode = mode
            self._sync()
            return self._save()
        return True
    
    def get_mode_display(self) -> str:
        """获取模式显示名称"""
        if self._mode == self.MODE_FORUM_GROUPS:
            return "贴吧对应群"
        return "群对应贴吧"
    
    # ========== 订阅操作 ==========
    
    def subscribe(self, forum: str, group: str) -> bool:
        """订阅贴吧到群
        
        Args:
            forum: 贴吧名
            group: 群号
        
        Returns:
            是否成功
        """
        # 更新forum_groups
        if forum not in self._forum_groups:
            self._forum_groups[forum] = []
        if group not in self._forum_groups[forum]:
            self._forum_groups[forum].append(group)
        
        # 更新group_forums
        if group not in self._group_forums:
            self._group_forums[group] = []
        if forum not in self._group_forums[group]:
            self._group_forums[group].append(forum)
        
        return self._save()
    
    def unsubscribe(self, forum: str, group: str) -> bool:
        """取消订阅
        
        Args:
            forum: 贴吧名
            group: 群号
        
        Returns:
            是否成功
        """
        # 从forum_groups移除
        if forum in self._forum_groups and group in self._forum_groups[forum]:
            self._forum_groups[forum].remove(group)
            if not self._forum_groups[forum]:
                del self._forum_groups[forum]
        
        # 从group_forums移除
        if group in self._group_forums and forum in self._group_forums[group]:
            self._group_forums[group].remove(forum)
            if not self._group_forums[group]:
                del self._group_forums[group]
        
        return self._save()
    
    def remove_forum(self, forum: str) -> bool:
        """删除整个贴吧订阅"""
        if forum in self._forum_groups:
            # 从所有群的中移除
            for group in self._forum_groups[forum]:
                if group in self._group_forums and forum in self._group_forums[group]:
                    self._group_forums[group].remove(forum)
                    if not self._group_forums[group]:
                        del self._group_forums[group]
            del self._forum_groups[forum]
            return self._save()
        return False
    
    def remove_group(self, group: str) -> bool:
        """删除整个群的订阅"""
        if group in self._group_forums:
            # 从所有贴吧中移除
            for forum in self._group_forums[group]:
                if forum in self._forum_groups and group in self._forum_groups[forum]:
                    self._forum_groups[forum].remove(group)
                    if not self._forum_groups[forum]:
                        del self._forum_groups[forum]
            del self._group_forums[group]
            return self._save()
        return False
    
    # ========== 查询操作 ==========
    
    def get_forum_groups(self, forum: str) -> List[str]:
        """获取订阅某贴吧的所有群"""
        return self._forum_groups.get(forum, []).copy()
    
    def get_group_forums(self, group: str) -> List[str]:
        """获取某群订阅的所有贴吧"""
        return self._group_forums.get(group, []).copy()
    
    def get_all_forums(self) -> List[str]:
        """获取所有订阅的贴吧"""
        return list(self._forum_groups.keys())
    
    def get_all_groups(self) -> List[str]:
        """获取所有订阅的群"""
        return list(self._group_forums.keys())
    
    def is_subscribed(self, forum: str, group: str) -> bool:
        """检查是否已订阅"""
        return group in self._forum_groups.get(forum, [])
    
    def get_subscription_count(self) -> dict:
        """获取订阅统计"""
        return {
            "forum_count": len(self._forum_groups),
            "group_count": len(self._group_forums),
            "total_subscriptions": sum(len(groups) for groups in self._forum_groups.values())
        }
    
    # ========== 数据导出 ==========
    
    @property
    def forum_groups(self) -> Dict[str, List[str]]:
        """以forum_groups格式获取所有订阅（兼容旧代码）"""
        return self._forum_groups.copy()
    
    @property
    def group_forums(self) -> Dict[str, List[str]]:
        """以group_forums格式获取所有订阅"""
        return self._group_forums.copy()
