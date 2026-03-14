"""
测试插件是否能正常获取帖子
"""
import asyncio
import sys
import os
sys.path.insert(0, '/root/ai/astrbot/data/plugins/astrbot_plugin_ICanSeeTieba')

# 模拟 AstrBot 环境
class MockLogger:
    @staticmethod
    def info(msg):
        print(f'[INFO] {msg}')
    @staticmethod
    def error(msg):
        print(f'[ERROR] {msg}')
    @staticmethod
    def warning(msg):
        print(f'[WARN] {msg}')
    @staticmethod
    def debug(msg):
        print(f'[DEBUG] {msg}')

class MockStarTools:
    @staticmethod
    def get_data_dir(name):
        data_dir = f'/root/ai/astrbot/data/plugin_data/{name}'
        os.makedirs(data_dir, exist_ok=True)
        return data_dir

# 创建模拟模块
import types
astrbot = types.ModuleType('astrbot')
astrbot.api = types.ModuleType('astrbot.api')
astrbot.api.logger = MockLogger()
astrbot.api.star = types.ModuleType('astrbot.api.star')
astrbot.api.star.StarTools = MockStarTools
sys.modules['astrbot'] = astrbot
sys.modules['astrbot.api'] = astrbot.api
sys.modules['astrbot.api.star'] = astrbot.api.star

# 模拟其他 AstrBot 模块
astrbot.api.event = types.ModuleType('astrbot.api.event')
astrbot.api.event.filter = type('filter', (), {})()
astrbot.api.event.AstrMessageEvent = type('AstrMessageEvent', (), {})
sys.modules['astrbot.api.event'] = astrbot.api.event

astrbot.core = types.ModuleType('astrbot.core')
astrbot.core.config = types.ModuleType('astrbot.core.config')
astrbot.core.config.astrbot_config = types.ModuleType('astrbot.core.config.astrbot_config')
astrbot.core.config.astrbot_config.AstrBotConfig = type('AstrBotConfig', (), {})
sys.modules['astrbot.core'] = astrbot.core
sys.modules['astrbot.core.config'] = astrbot.core.config
sys.modules['astrbot.core.config.astrbot_config'] = astrbot.core.config.astrbot_config

astrbot.core.message = types.ModuleType('astrbot.core.message')
astrbot.core.message.message_event_result = types.ModuleType('astrbot.core.message.message_event_result')
astrbot.core.message.message_event_result.MessageChain = type('MessageChain', (), {})
sys.modules['astrbot.core.message'] = astrbot.core.message
sys.modules['astrbot.core.message.message_event_result'] = astrbot.core.message.message_event_result

from tieba_client import TiebaClient

async def test_get_threads():
    """测试获取贴吧帖子"""
    print("=" * 60)
    print("测试获取贴吧帖子")
    print("=" * 60)
    
    client = TiebaClient()
    
    # 测试几个贴吧
    test_forums = ["鸣潮", "原神内鬼", "asoul"]
    total_posts = 0
    
    for forum_name in test_forums:
        print(f"\n--- 测试贴吧: {forum_name} ---")
        try:
            threads = await client.get_threads(forum_name, retry=2, timeout=30)
            
            if threads:
                print(f"✅ 成功获取 {len(threads)} 条帖子")
                total_posts += len(threads)
                # 显示第一条帖子的信息
                if threads:
                    first = threads[0]
                    print(f"   标题: {first.get('title', 'N/A')}")
                    print(f"   作者: {first.get('author_id', 'N/A')}")
                    print(f"   回复: {