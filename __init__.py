"""
贴吧观察者插件
AstrBot 贴吧监控插件

版本: 1.0.0
"""

from ._version import __version__, __plugin_name__, __plugin_desc__, __author__
from .main import TiebaPlugin

__all__ = ["TiebaPlugin", "__version__", "__plugin_name__", "__plugin_desc__", "__author__"]
