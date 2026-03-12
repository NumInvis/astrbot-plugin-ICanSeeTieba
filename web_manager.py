"""
贴吧观察者 - Web管理界面
用于可视化配置贴吧监控
支持双模式：贴吧对应群 / 群对应贴吧
"""

import hashlib
import json
import os
import secrets
from datetime import datetime
from functools import wraps
from typing import Dict, List, Optional, Tuple

from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from filelock import FileLock

from astrbot.api.star import StarTools

# 数据目录（必须在app配置之前定义）
DATA_DIR = str(StarTools.get_data_dir("astrbot_plugin_ICanSeeTieba"))
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
# 使用固定的secret_key（从文件读取或生成）
SECRET_KEY_FILE = os.path.join(DATA_DIR, ".secret_key")
if os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, 'r') as f:
        app.secret_key = f.read().strip()
else:
    app.secret_key = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, 'w') as f:
        f.write(app.secret_key)

# 配置session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30分钟
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
USER_FILE = os.path.join(DATA_DIR, "user.json")
CONFIG_LOCK = FileLock(os.path.join(DATA_DIR, "config.lock"))
USER_LOCK = FileLock(os.path.join(DATA_DIR, "user.lock"))

# 订阅模式
MODE_FORUM_GROUPS = "forum_groups"  # 贴吧对应群
MODE_GROUP_FORUMS = "group_forums"  # 群对应贴吧

# 默认账号
DEFAULT_USERNAME = "root"
DEFAULT_PASSWORD = "moning"


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """使用PBKDF2哈希密码"""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return salt, hashed.hex()


def verify_password(password: str, salt: str, hashed: str) -> bool:
    """验证密码"""
    _, new_hash = hash_password(password, salt)
    return secrets.compare_digest(new_hash, hashed)


def load_user_config() -> Dict:
    """加载用户配置"""
    with USER_LOCK:
        if os.path.exists(USER_FILE):
            try:
                with open(USER_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError, OSError):
                pass
    
    # 首次使用，创建默认配置（密码已哈希）
    salt, hashed = hash_password(DEFAULT_PASSWORD)
    default_config = {
        "username": DEFAULT_USERNAME,
        "password_salt": salt,
        "password_hash": hashed,
        "first_login": True
    }
    save_user_config(default_config)
    return default_config


def save_user_config(config: Dict):
    """保存用户配置"""
    with USER_LOCK:
        try:
            with open(USER_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            return True
        except (IOError, OSError, TypeError) as e:
            print(f"保存用户配置失败: {e}")
            return False


def login_required(f):
    """登录验证装饰器 - 强制登录"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 严格检查登录状态
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def load_config() -> Dict:
    """加载配置"""
    with CONFIG_LOCK:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError, OSError) as e:
                print(f"加载配置失败: {e}")
    
    return {
        "check_interval_seconds": 240,
        "threads_to_retrieve": 6,
        "hot_reply_threshold": 100,
        "hot_agree_threshold": 1000,
        "admin_users": [],
        "forum_groups": {},
        "group_forums": {},
        "subscription_mode": MODE_FORUM_GROUPS
    }


def save_config(config: Dict):
    """保存配置"""
    with CONFIG_LOCK:
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            return True
        except (IOError, OSError, TypeError) as e:
            print(f"保存配置失败: {e}")
            return False


def get_mode_display(mode: str) -> str:
    """获取模式显示名称"""
    return "贴吧对应群" if mode == MODE_FORUM_GROUPS else "群对应贴吧"


def validate_forum_name(name: str) -> bool:
    """验证贴吧名称格式"""
    import re
    return bool(re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_]{2,20}$', name))


def validate_qq(qq: str) -> bool:
    """验证QQ号格式"""
    import re
    return bool(re.match(r'^\d{5,11}$', qq))


def validate_group_ids(group_ids_str: str) -> Tuple[bool, List[str], str]:
    """验证群号列表"""
    if not group_ids_str:
        return False, [], "群号不能为空"
    
    group_ids = [g.strip() for g in group_ids_str.split(',') if g.strip()]
    
    if not group_ids:
        return False, [], "群号不能为空"
    
    invalid_groups = []
    for gid in group_ids:
        if not validate_qq(gid):
            invalid_groups.append(gid)
    
    if invalid_groups:
        return False, [], f"无效的群号: {', '.join(invalid_groups)}"
    
    return True, group_ids, ""


# ========== 订阅管理函数 ==========

def sync_forum_to_group(forum_groups: Dict) -> Dict:
    """将forum_groups转换为group_forums"""
    group_forums = {}
    for forum, groups in forum_groups.items():
        for group in groups:
            if group not in group_forums:
                group_forums[group] = []
            if forum not in group_forums[group]:
                group_forums[group].append(forum)
    return group_forums


def sync_group_to_forum(group_forums: Dict) -> Dict:
    """将group_forums转换为forum_groups"""
    forum_groups = {}
    for group, forums in group_forums.items():
        for forum in forums:
            if forum not in forum_groups:
                forum_groups[forum] = []
            if group not in forum_groups[forum]:
                forum_groups[forum].append(group)
    return forum_groups


def subscribe(forum: str, group: str, config: Dict) -> bool:
    """订阅贴吧到群"""
    # 更新forum_groups
    if "forum_groups" not in config:
        config["forum_groups"] = {}
    if forum not in config["forum_groups"]:
        config["forum_groups"][forum] = []
    if group not in config["forum_groups"][forum]:
        config["forum_groups"][forum].append(group)
    
    # 更新group_forums
    if "group_forums" not in config:
        config["group_forums"] = {}
    if group not in config["group_forums"]:
        config["group_forums"][group] = []
    if forum not in config["group_forums"][group]:
        config["group_forums"][group].append(forum)
    
    return save_config(config)


def unsubscribe(forum: str, group: str, config: Dict) -> bool:
    """取消订阅"""
    # 从forum_groups移除
    if forum in config.get("forum_groups", {}) and group in config["forum_groups"][forum]:
        config["forum_groups"][forum].remove(group)
        if not config["forum_groups"][forum]:
            del config["forum_groups"][forum]
    
    # 从group_forums移除
    if group in config.get("group_forums", {}) and forum in config["group_forums"][group]:
        config["group_forums"][group].remove(forum)
        if not config["group_forums"][group]:
            del config["group_forums"][group]
    
    return save_config(config)


LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>贴吧观察者 - 登录</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 400px;
        }
        .login-header {
            text-align: center;
            margin-bottom: 30px;
        }
        .login-header h1 {
            color: #333;
            font-size: 1.8em;
            margin-bottom: 10px;
        }
        .login-header p {
            color: #666;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
        }
        input[type="text"],
        input[type="password"] {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus,
        input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 500;
            transition: all 0.3s;
        }
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        .alert {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .alert-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .alert-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .alert-warning {
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h1>🎯 贴吧观察者</h1>
            <p>管理后台登录</p>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% if first_login %}
            <div class="alert alert-warning">
                <strong>首次登录！</strong><br>
                默认用户名: root<br>
                默认密码: moning<br>
                登录后请立即修改密码
            </div>
        {% endif %}

        <form method="POST" action="{{ url_for('login') }}">
            <div class="form-group">
                <label>用户名</label>
                <input type="text" name="username" required autofocus>
            </div>
            <div class="form-group">
                <label>密码</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-primary">登录</button>
        </form>
    </div>
</body>
</html>
"""


CHANGE_PASSWORD_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>贴吧观察者 - 修改密码</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 400px;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            color: #333;
            font-size: 1.8em;
            margin-bottom: 10px;
        }
        .header p {
            color: #666;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
        }
        input[type="password"] {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 500;
            transition: all 0.3s;
        }
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        .btn-secondary {
            background: #6c757d;
            color: white;
            margin-top: 10px;
        }
        .alert {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .alert-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .alert-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔐 修改密码</h1>
            <p>为了安全，请修改默认密码</p>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <form method="POST" action="{{ url_for('change_password') }}">
            <div class="form-group">
                <label>当前密码</label>
                <input type="password" name="current_password" required>
            </div>
            <div class="form-group">
                <label>新密码</label>
                <input type="password" name="new_password" required minlength="6">
            </div>
            <div class="form-group">
                <label>确认新密码</label>
                <input type="password" name="confirm_password" required minlength="6">
            </div>
            <button type="submit" class="btn btn-primary">修改密码</button>
            <a href="{{ url_for('logout') }}" class="btn btn-secondary" style="display: inline-block; text-align: center; text-decoration: none;">退出登录</a>
        </form>
    </div>
</body>
</html>
"""


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>贴吧观察者 - 管理后台</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: white;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 2.5em;
        }
        .header p {
            opacity: 0.9;
        }
        .user-menu {
            display: flex;
            gap: 15px;
            align-items: center;
        }
        .btn-logout {
            background: rgba(255,255,255,0.2);
            color: white;
            padding: 8px 16px;
            border-radius: 6px;
            text-decoration: none;
            transition: background 0.3s;
        }
        .btn-logout:hover {
            background: rgba(255,255,255,0.3);
        }
        .card {
            background: white;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }
        .card h2 {
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #555;
            font-weight: 500;
        }
        input[type="text"],
        input[type="number"] {
            width: 100%;
            padding: 10px 15px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus,
        input[type="number"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
            text-decoration: none;
            display: inline-block;
        }
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        .btn-danger {
            background: #e74c3c;
            color: white;
        }
        .btn-danger:hover {
            background: #c0392b;
        }
        .btn-success {
            background: #27ae60;
            color: white;
        }
        .btn-success:hover {
            background: #219a52;
        }
        .btn-warning {
            background: #f39c12;
            color: white;
        }
        .btn-warning:hover {
            background: #e67e22;
        }
        .btn-info {
            background: #17a2b8;
            color: white;
        }
        .btn-info:hover {
            background: #138496;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        .forum-item, .group-item {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
        }
        .forum-name, .group-name {
            font-weight: bold;
            color: #333;
            font-size: 1.1em;
            margin-bottom: 10px;
        }
        .group-list, .forum-list {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-bottom: 10px;
        }
        .group-tag, .forum-tag {
            background: #667eea;
            color: white;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
        }
        .forum-tag {
            background: #27ae60;
        }
        .admin-list {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        .admin-tag {
            background: #27ae60;
            color: white;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .empty-state {
            text-align: center;
            color: #999;
            padding: 40px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        .stat-value {
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }
        .stat-label {
            font-size: 0.9em;
        }
        .flash-messages {
            margin-bottom: 20px;
        }
        .flash-message {
            padding: 12px 20px;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        .flash-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .flash-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .form-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        .delete-form {
            display: inline;
        }
        .mode-badge {
            background: #ffc107;
            color: #333;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .tab {
            padding: 10px 20px;
            background: #e9ecef;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }
        .tab.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .tab:hover:not(.active) {
            background: #dee2e6;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>🎯 贴吧观察者</h1>
                <p>AstrBot 贴吧监控插件管理后台</p>
            </div>
            <div class="user-menu">
                <span class="mode-badge">{{ mode_display }}</span>
                <span>👤 {{ username }}</span>
                <a href="{{ url_for('change_password') }}" class="btn-logout">修改密码</a>
                <a href="{{ url_for('logout') }}" class="btn-logout">退出登录</a>
            </div>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="flash-message flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        <!-- 统计信息 -->
        <div class="card">
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value">{{ forum_count }}</div>
                    <div class="stat-label">监控贴吧</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ group_count }}</div>
                    <div class="stat-label">订阅群组</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ config.admin_users|length }}</div>
                    <div class="stat-label">管理员</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ config.check_interval_seconds }}s</div>
                    <div class="stat-label">检查间隔</div>
                </div>
            </div>
        </div>

        <div class="grid">
            <!-- 基础配置 -->
            <div class="card">
                <h2>⚙️ 基础配置</h2>
                <form method="POST" action="{{ url_for('update_settings') }}">
                    <div class="form-row">
                        <div class="form-group">
                            <label>检查间隔（秒）</label>
                            <input type="number" name="check_interval" value="{{ config.check_interval_seconds }}" min="60" max="3600">
                        </div>
                        <div class="form-group">
                            <label>获取帖子数</label>
                            <input type="number" name="threads_count" value="{{ config.threads_to_retrieve }}" min="1" max="20">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>热帖回复阈值</label>
                            <input type="number" name="hot_reply" value="{{ config.hot_reply_threshold }}" min="1" max="10000">
                        </div>
                        <div class="form-group">
                            <label>热帖点赞阈值</label>
                            <input type="number" name="hot_agree" value="{{ config.hot_agree_threshold }}" min="1" max="50000">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary">保存配置</button>
                </form>
            </div>

            <!-- 管理员管理 -->
            <div class="card">
                <h2>👤 管理员</h2>
                <form method="POST" action="{{ url_for('add_admin') }}" style="margin-bottom: 20px;">
                    <div class="form-group">
                        <label>添加管理员QQ</label>
                        <input type="text" name="admin_qq" placeholder="输入QQ号码" required pattern="\\d{5,11}">
                    </div>
                    <button type="submit" class="btn btn-success">添加</button>
                </form>
                
                {% if config.admin_users %}
                    <div class="admin-list">
                        {% for admin in config.admin_users %}
                            <span class="admin-tag">
                                {{ admin }}
                                <form method="POST" action="{{ url_for('remove_admin') }}" class="delete-form" onsubmit="return confirm('确定要删除管理员 {{ admin }} 吗？');">
                                    <input type="hidden" name="qq" value="{{ admin }}">
                                    <button type="submit" style="background: none; border: none; color: white; cursor: pointer; font-size: 16px;">×</button>
                                </form>
                            </span>
                        {% endfor %}
                    </div>
                {% else %}
                    <div class="empty-state">暂无管理员</div>
                {% endif %}
            </div>
        </div>

        <!-- 模式切换 -->
        <div class="card">
            <h2>🔄 订阅显示模式</h2>
            <p style="margin-bottom: 15px; color: #666;">当前模式：<strong>{{ mode_display }}</strong></p>
            <div style="display: flex; gap: 10px;">
                <form method="POST" action="{{ url_for('switch_mode') }}">
                    <input type="hidden" name="mode" value="forum_groups">
                    <button type="submit" class="btn btn-info {% if config.subscription_mode == 'forum_groups' %}active{% endif %}">
                        贴吧对应群
                    </button>
                </form>
                <form method="POST" action="{{ url_for('switch_mode') }}">
                    <input type="hidden" name="mode" value="group_forums">
                    <button type="submit" class="btn btn-info {% if config.subscription_mode == 'group_forums' %}active{% endif %}">
                        群对应贴吧
                    </button>
                </form>
            </div>
            <p style="margin-top: 15px; color: #999; font-size: 12px;">
                💡 贴吧对应群：显示每个贴吧推送到哪些群 | 群对应贴吧：显示每个群订阅了哪些贴吧
            </p>
        </div>

        <!-- 订阅管理 -->
        <div class="card">
            <h2>📋 订阅管理</h2>
            
            <!-- 添加订阅表单 -->
            <form method="POST" action="{{ url_for('add_subscription') }}" style="margin-bottom: 25px;">
                <div class="grid" style="grid-template-columns: 2fr 2fr 1fr; align-items: end;">
                    <div class="form-group">
                        <label>贴吧名称</label>
                        <input type="text" name="forum_name" placeholder="例如：鸣潮" required pattern="[\\u4e00-\\u9fa5a-zA-Z0-9_]{2,20}">
                    </div>
                    <div class="form-group">
                        <label>推送群号（多个用逗号分隔）</label>
                        <input type="text" name="group_ids" placeholder="例如：1087074883,661278084" required pattern="[\\d,]+">
                    </div>
                    <div class="form-group">
                        <button type="submit" class="btn btn-success" style="width: 100%;">添加订阅</button>
                    </div>
                </div>
            </form>

            <!-- 根据模式显示不同视图 -->
            {% if config.subscription_mode == 'forum_groups' %}
                <!-- 贴吧对应群模式 -->
                <h3 style="margin-bottom: 15px; color: #667eea;">📌 贴吧 → 群</h3>
                {% if config.forum_groups %}
                    {% for forum, groups in config.forum_groups.items() %}
                        <div class="forum-item">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <div class="forum-name">{{ forum }}吧</div>
                                    <div class="group-list">
                                        {% for group in groups %}
                                            <span class="group-tag">{{ group }}</span>
                                        {% endfor %}
                                    </div>
                                </div>
                                <form method="POST" action="{{ url_for('remove_forum') }}" class="delete-form" onsubmit="return confirm('确定要删除贴吧 {{ forum }} 的所有订阅吗？');">
                                    <input type="hidden" name="forum" value="{{ forum }}">
                                    <button type="submit" class="btn btn-danger">删除</button>
                                </form>
                            </div>
                        </div>
                    {% endfor %}
                {% else %}
                    <div class="empty-state">暂无订阅的贴吧</div>
                {% endif %}
            {% else %}
                <!-- 群对应贴吧模式 -->
                <h3 style="margin-bottom: 15px; color: #27ae60;">📌 群 → 贴吧</h3>
                {% if config.group_forums %}
                    {% for group, forums in config.group_forums.items() %}
                        <div class="group-item">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <div class="group-name">群 {{ group }}</div>
                                    <div class="forum-list">
                                        {% for forum in forums %}
                                            <span class="forum-tag">{{ forum }}吧</span>
                                        {% endfor %}
                                    </div>
                                </div>
                                <form method="POST" action="{{ url_for('remove_group') }}" class="delete-form" onsubmit="return confirm('确定要删除群 {{ group }} 的所有订阅吗？');">
                                    <input type="hidden" name="group" value="{{ group }}">
                                    <button type="submit" class="btn btn-danger">删除</button>
                                </form>
                            </div>
                        </div>
                    {% endfor %}
                {% else %}
                    <div class="empty-state">暂无订阅的群</div>
                {% endif %}
            {% endif %}
        </div>

        <div style="text-align: center; color: white; opacity: 0.8; margin-top: 30px;">
            <p>贴吧观察者 v1.0.0 | 作者：NumInvis</p>
        </div>
    </div>
</body>
</html>
"""


@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    user_config = load_user_config()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == user_config['username']:
            if 'password_hash' in user_config:
                password_valid = verify_password(password, user_config['password_salt'], user_config['password_hash'])
            else:
                password_valid = (password == user_config.get('password', ''))
                if password_valid:
                    salt, hashed = hash_password(password)
                    user_config['password_salt'] = salt
                    user_config['password_hash'] = hashed
                    del user_config['password']
                    save_user_config(user_config)
            
            if password_valid:
                session.clear()  # 清除旧session
                session['logged_in'] = True
                session['username'] = username
                session['last_activity'] = datetime.now().isoformat()  # 设置活动时间
                
                if user_config.get('first_login', True):
                    flash('首次登录，请修改默认密码！', 'warning')
                    return redirect(url_for('change_password'))
                
                flash('登录成功！', 'success')
                return redirect(url_for('index'))
        
        flash('用户名或密码错误！', 'error')
    
    return render_template_string(
        LOGIN_TEMPLATE,
        first_login=user_config.get('first_login', True)
    )


@app.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    flash('已退出登录！', 'success')
    return redirect(url_for('login'))


@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """修改密码"""
    user_config = load_user_config()
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if 'password_hash' in user_config:
            current_valid = verify_password(current_password, user_config['password_salt'], user_config['password_hash'])
        else:
            current_valid = (current_password == user_config.get('password', ''))
        
        if not current_valid:
            flash('当前密码错误！', 'error')
        elif new_password != confirm_password:
            flash('两次输入的新密码不一致！', 'error')
        elif len(new_password) < 6:
            flash('新密码长度至少6位！', 'error')
        elif new_password == DEFAULT_PASSWORD:
            flash('不能使用默认密码，请设置其他密码！', 'error')
        else:
            salt, hashed = hash_password(new_password)
            user_config['password_salt'] = salt
            user_config['password_hash'] = hashed
            if 'password' in user_config:
                del user_config['password']
            user_config['first_login'] = False
            
            if save_user_config(user_config):
                flash('密码修改成功！请使用新密码重新登录。', 'success')
                return redirect(url_for('logout'))
            else:
                flash('密码修改失败！', 'error')
    
    return render_template_string(CHANGE_PASSWORD_TEMPLATE)


@app.route('/')
@login_required
def index():
    """首页"""
    config = load_config()
    
    # 计算统计信息
    forum_count = len(config.get("forum_groups", {}))
    group_count = len(config.get("group_forums", {}))
    
    # 如果没有group_forums，从forum_groups计算
    if not group_count and config.get("forum_groups"):
        all_groups = set()
        for groups in config["forum_groups"].values():
            all_groups.update(groups)
        group_count = len(all_groups)
    
    mode_display = get_mode_display(config.get("subscription_mode", MODE_FORUM_GROUPS))
    
    return render_template_string(
        HTML_TEMPLATE,
        config=config,
        forum_count=forum_count,
        group_count=group_count,
        mode_display=mode_display,
        username=session.get('username', 'root')
    )


@app.route('/update_settings', methods=['POST'])
@login_required
def update_settings():
    """更新基础配置"""
    config = load_config()
    
    try:
        check_interval = int(request.form.get('check_interval', 240))
        threads_count = int(request.form.get('threads_count', 6))
        hot_reply = int(request.form.get('hot_reply', 100))
        hot_agree = int(request.form.get('hot_agree', 1000))
        
        if not (60 <= check_interval <= 3600):
            flash('检查间隔必须在60-3600秒之间！', 'error')
            return redirect(url_for('index'))
        
        if not (1 <= threads_count <= 20):
            flash('获取帖子数必须在1-20之间！', 'error')
            return redirect(url_for('index'))
        
        config['check_interval_seconds'] = check_interval
        config['threads_to_retrieve'] = threads_count
        config['hot_reply_threshold'] = hot_reply
        config['hot_agree_threshold'] = hot_agree
        
        if save_config(config):
            flash('配置保存成功！', 'success')
        else:
            flash('配置保存失败！', 'error')
    except ValueError:
        flash('配置参数格式错误！', 'error')
    except (IOError, OSError, TypeError) as e:
        flash(f'配置保存失败：{e}', 'error')
    
    return redirect(url_for('index'))


@app.route('/add_admin', methods=['POST'])
@login_required
def add_admin():
    """添加管理员"""
    config = load_config()
    admin_qq = request.form.get('admin_qq', '').strip()
    
    if not admin_qq:
        flash('QQ号不能为空！', 'error')
        return redirect(url_for('index'))
    
    if not validate_qq(admin_qq):
        flash(f'QQ号 {admin_qq} 格式无效！', 'error')
        return redirect(url_for('index'))
    
    if 'admin_users' not in config:
        config['admin_users'] = []
    
    if admin_qq in config['admin_users']:
        flash('该管理员已存在！', 'error')
        return redirect(url_for('index'))
    
    config['admin_users'].append(admin_qq)
    if save_config(config):
        flash(f'管理员 {admin_qq} 添加成功！', 'success')
    else:
        flash('添加失败！', 'error')
    
    return redirect(url_for('index'))


@app.route('/remove_admin', methods=['POST'])
@login_required
def remove_admin():
    """删除管理员"""
    config = load_config()
    qq = request.form.get('qq', '').strip()
    
    if not qq:
        flash('参数错误！', 'error')
        return redirect(url_for('index'))
    
    if qq in config.get('admin_users', []):
        config['admin_users'].remove(qq)
        if save_config(config):
            flash(f'管理员 {qq} 已删除！', 'success')
        else:
            flash('删除失败！', 'error')
    else:
        flash('管理员不存在！', 'error')
    
    return redirect(url_for('index'))


@app.route('/switch_mode', methods=['POST'])
@login_required
def switch_mode():
    """切换订阅模式"""
    config = load_config()
    mode = request.form.get('mode', '')
    
    if mode not in [MODE_FORUM_GROUPS, MODE_GROUP_FORUMS]:
        flash('无效的模式！', 'error')
        return redirect(url_for('index'))
    
    # 如果数据不完整，先同步
    if not config.get("group_forums") and config.get("forum_groups"):
        config["group_forums"] = sync_forum_to_group(config["forum_groups"])
    elif not config.get("forum_groups") and config.get("group_forums"):
        config["forum_groups"] = sync_group_to_forum(config["group_forums"])
    
    config['subscription_mode'] = mode
    
    if save_config(config):
        mode_display = get_mode_display(mode)
        flash(f'已切换到【{mode_display}】模式！', 'success')
    else:
        flash('模式切换失败！', 'error')
    
    return redirect(url_for('index'))


@app.route('/add_subscription', methods=['POST'])
@login_required
def add_subscription():
    """添加订阅"""
    config = load_config()
    forum_name = request.form.get('forum_name', '').strip()
    group_ids_str = request.form.get('group_ids', '').strip()
    
    if not forum_name:
        flash('贴吧名称不能为空！', 'error')
        return redirect(url_for('index'))
    
    if not validate_forum_name(forum_name):
        flash(f'贴吧名称 "{forum_name}" 格式无效！', 'error')
        return redirect(url_for('index'))
    
    valid, group_ids, error_msg = validate_group_ids(group_ids_str)
    if not valid:
        flash(error_msg, 'error')
        return redirect(url_for('index'))
    
    # 初始化数据结构
    if "forum_groups" not in config:
        config["forum_groups"] = {}
    if "group_forums" not in config:
        config["group_forums"] = {}
    
    # 添加订阅关系
    for group_id in group_ids:
        # 更新forum_groups
        if forum_name not in config["forum_groups"]:
            config["forum_groups"][forum_name] = []
        if group_id not in config["forum_groups"][forum_name]:
            config["forum_groups"][forum_name].append(group_id)
        
        # 更新group_forums
        if group_id not in config["group_forums"]:
            config["group_forums"][group_id] = []
        if forum_name not in config["group_forums"][group_id]:
            config["group_forums"][group_id].append(forum_name)
    
    if save_config(config):
        flash(f'贴吧 {forum_name} 订阅成功！', 'success')
    else:
        flash('订阅失败！', 'error')
    
    return redirect(url_for('index'))


@app.route('/remove_forum', methods=['POST'])
@login_required
def remove_forum():
    """删除贴吧订阅"""
    config = load_config()
    forum = request.form.get('forum', '').strip()
    
    if not forum:
        flash('参数错误！', 'error')
        return redirect(url_for('index'))
    
    if forum in config.get("forum_groups", {}):
        # 从所有群中移除该贴吧
        for group in config["forum_groups"][forum]:
            if group in config.get("group_forums", {}) and forum in config["group_forums"][group]:
                config["group_forums"][group].remove(forum)
                if not config["group_forums"][group]:
                    del config["group_forums"][group]
        
        del config["forum_groups"][forum]
        
        if save_config(config):
            flash(f'贴吧 {forum} 已删除！', 'success')
        else:
            flash('删除失败！', 'error')
    else:
        flash('贴吧不存在！', 'error')
    
    return redirect(url_for('index'))


@app.route('/remove_group', methods=['POST'])
@login_required
def remove_group():
    """删除群订阅"""
    config = load_config()
    group = request.form.get('group', '').strip()
    
    if not group:
        flash('参数错误！', 'error')
        return redirect(url_for('index'))
    
    if group in config.get("group_forums", {}):
        # 从所有贴吧中移除该群
        for forum in config["group_forums"][group]:
            if forum in config.get("forum_groups", {}) and group in config["forum_groups"][forum]:
                config["forum_groups"][forum].remove(group)
                if not config["forum_groups"][forum]:
                    del config["forum_groups"][forum]
        
        del config["group_forums"][group]
        
        if save_config(config):
            flash(f'群 {group} 的订阅已删除！', 'success')
        else:
            flash('删除失败！', 'error')
    else:
        flash('群不存在！', 'error')
    
    return redirect(url_for('index'))


def run_web_manager(port=5000):
    """运行Web管理界面"""
    print(f"🌐 贴吧观察者管理界面已启动")
    print(f"📍 访问地址: http://0.0.0.0:{port}")
    print(f"🔐 默认用户名: root")
    print(f"🔐 默认密码: moning")
    print(f"⚠️  请确保端口 {port} 已开放")
    app.run(host='0.0.0.0', port=port, debug=False)


if __name__ == '__main__':
    run_web_manager()
