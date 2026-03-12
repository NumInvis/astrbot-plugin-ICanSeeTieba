"""
贴吧客户端模块
封装 aiotieba 的调用
"""

import asyncio
import random
import re
from datetime import datetime
from typing import Dict, List, Optional

import aiotieba
from astrbot.api import logger


# 模块级别的正则表达式常量 - 避免重复编译
URL_PATTERN = re.compile(r'^https?://[^\s<>"{}|\\^`\[\]]+$')


class TiebaClient:
    """贴吧客户端"""

    def __init__(self):
        self._client: Optional[aiotieba.Client] = None

    async def _get_client(self) -> aiotieba.Client:
        """获取或创建客户端"""
        if self._client is None:
            self._client = aiotieba.Client()
        return self._client

    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.close()
            self._client = None

    def _is_valid_url(self, url: str) -> bool:
        """验证URL是否有效 - 使用模块级别的预编译正则表达式"""
        if not url or not isinstance(url, str):
            return False
        # 使用预编译的正则表达式，避免重复编译
        return bool(URL_PATTERN.match(url))

    async def get_threads(self, forum_name: str, retry: int = 3, timeout: int = 30) -> List[Dict]:
        """
        获取贴吧的最新帖子

        Args:
            forum_name: 贴吧名称
            retry: 重试次数
            timeout: 超时时间（秒）

        Returns:
            帖子列表
        """
        threads = []
        attempt = 0

        while attempt < retry:
            try:
                client = await self._get_client()

                # 获取帖子，按创建时间排序，添加超时控制
                raw_threads = await asyncio.wait_for(
                    client.get_threads(forum_name, sort=aiotieba.ThreadSortType.CREATE),
                    timeout=timeout
                )

                if raw_threads:
                    # 转换为标准格式
                    for thread in raw_threads:
                        try:
                            thread_info = self._convert_thread(thread, forum_name)
                            threads.append(thread_info)
                        except (AttributeError, TypeError) as conv_e:
                            logger.warning(f"转换帖子数据失败: {conv_e}")
                            continue

                    logger.info(f"成功获取贴吧[{forum_name}]的{len(threads)}条帖子")
                    return threads
                else:
                    # 如果没有获取到帖子，等待后重试
                    attempt += 1
                    if attempt < retry:
                        delay = random.uniform(1, 5)
                        logger.warning(
                            f"获取贴吧[{forum_name}]帖子为空，"
                            f"{delay:.1f}秒后进行第{attempt}次重试..."
                        )
                        await asyncio.sleep(delay)

            except asyncio.TimeoutError:
                attempt += 1
                logger.error(f"获取贴吧[{forum_name}]帖子超时(尝试{attempt}/{retry})")
                if attempt < retry:
                    await asyncio.sleep(random.uniform(2, 5))
            except aiotieba.TiebaError as e:
                attempt += 1
                logger.error(f"aiotieba错误 - 获取贴吧[{forum_name}]帖子失败(尝试{attempt}/{retry}): {e}")
                if attempt < retry:
                    await asyncio.sleep(random.uniform(1, 3))

        return threads

    def _convert_thread(self, thread, forum_name: str) -> Dict:
        """
        将 aiotieba 的帖子对象转换为标准字典格式

        Args:
            thread: aiotieba 帖子对象
            forum_name: 贴吧名称

        Returns:
            帖子信息字典
        """
        # 基础信息
        thread_info = {
            "tid": getattr(thread, "tid", 0),
            "title": getattr(thread, "title", None) or "无标题",
            "url": f"https://tieba.baidu.com/p/{getattr(thread, 'tid', 0)}",
            "create_time": "",
            "text": getattr(thread, "text", None) or "",
            "images": [],
            "tieba_name": forum_name,
        }

        # 作者信息
        try:
            if hasattr(thread, "user") and thread.user:
                author = getattr(thread.user, "nick_name_new", None) or \
                        getattr(thread.user, "user_name", None) or \
                        getattr(thread.user, "user_id", "未知用户")
                thread_info["author_id"] = author
            else:
                thread_info["author_id"] = "未知用户"
        except (AttributeError, TypeError):
            thread_info["author_id"] = "未知用户"

        # 时间转换
        try:
            create_time_ts = getattr(thread, "create_time", 0)
            if create_time_ts:
                thread_info["create_time"] = datetime.fromtimestamp(
                    create_time_ts
                ).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError, OverflowError) as e:
            logger.warning(f"时间转换失败: {e}")
            thread_info["create_time"] = ""

        # 热度数据
        thread_info["reply_num"] = getattr(thread, "reply_num", 0) or 0
        thread_info["agree"] = getattr(thread, "agree", 0) or 0
        thread_info["view_num"] = getattr(thread, "view_num", 0) or 0

        # 获取图片
        try:
            if hasattr(thread, "contents") and thread.contents:
                if hasattr(thread.contents, "imgs") and thread.contents.imgs:
                    images = []
                    for img in thread.contents.imgs:
                        if hasattr(img, "origin_src"):
                            img_url = img.origin_src
                            if self._is_valid_url(img_url):
                                images.append(img_url)
                    thread_info["images"] = images[:3]  # 最多3张图片
        except (AttributeError, TypeError) as img_e:
            logger.warning(f"获取帖子图片失败: {img_e}")
            thread_info["images"] = []

        return thread_info
