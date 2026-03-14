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


URL_PATTERN = re.compile(r'^https?://[^\s<>"{}|\\^`\[\]]+$')


class TiebaClient:
    """贴吧客户端"""

    async def get_threads(self, forum_name: str, retry: int = 3, timeout: int = 30) -> List[Dict]:
        """获取贴吧的最新帖子"""
        threads = []
        attempt = 0

        while attempt < retry:
            try:
                async with aiotieba.Client() as client:
                    raw_threads = await client.get_threads(
                        forum_name,
                        sort=aiotieba.ThreadSortType.CREATE
                    )

                    if len(raw_threads) == 0 and attempt < retry - 1:
                        attempt += 1
                        delay = random.uniform(1, 5)
                        logger.warning(
                            f"获取贴吧[{forum_name}]帖子为0条，"
                            f"{delay:.2f}秒后进行第{attempt}次重试..."
                        )
                        await asyncio.sleep(delay)
                        continue

                    for thread in raw_threads:
                        try:
                            thread_info = self._convert_thread(thread, forum_name)
                            threads.append(thread_info)
                        except (AttributeError, TypeError) as conv_e:
                            logger.warning(f"转换帖子数据失败: {conv_e}")
                            continue

                    logger.info(f"成功获取贴吧[{forum_name}]的{len(threads)}条帖子")
                    return threads

            except asyncio.TimeoutError:
                attempt += 1
                logger.error(f"获取贴吧[{forum_name}]帖子超时(尝试{attempt}/{retry})")
                if attempt < retry:
                    await asyncio.sleep(random.uniform(2, 5))
            except Exception as e:
                attempt += 1
                logger.error(f"获取贴吧[{forum_name}]帖子失败(尝试{attempt}/{retry}): {e}")
                if attempt < retry:
                    await asyncio.sleep(random.uniform(1, 3))

        return threads

    def _convert_thread(self, thread, forum_name: str) -> Dict:
        """将 aiotieba 的帖子对象转换为标准字典格式"""
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
                    thread_info["images"] = images[:3]
        except (AttributeError, TypeError) as img_e:
            logger.warning(f"获取帖子图片失败: {img_e}")
            thread_info["images"] = []

        return thread_info

    def _is_valid_url(self, url: str) -> bool:
        """验证URL是否有效"""
        if not url or not isinstance(url, str):
            return False
        return bool(URL_PATTERN.match(url))
