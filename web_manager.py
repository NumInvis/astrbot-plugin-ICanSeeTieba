"""
贴吧观察者 - Web管理界面
用于可视化配置贴吧监控
"""

import json
import os
from datetime import datetime
from functools import wraps
from typing import Dict, List

from flask import Flask, render_template_string, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = 'tieba_manager_secret_key_change_in_production'

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
USER_FILE = os.path.join(DATA_DIR, "user.json")

# 默认账号
DEFAULT_USERNAME = "root"
DEFAULT_PASSWORD = "moning"


def load_user_config() -> Dict:
    """加载用户配置"""
    if os.path.exists(USER_FILE):
        try:
            with open(USER_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "username": DEFAULT_USERNAME,
        "password": DEFAULT_PASSWORD,
        "first_login": True
    }


def save_user_config(config: Dict):
    """保存用户配置"""
    try:
        with open(USER_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"保存用户配置失败: {e}")
        return False


def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def load_config() -> Dict:
    """加载配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载配置失败: {e}")
    return {
        "check_interval_seconds": 240,
        "threads_to_retrieve": 6,
        "hot_reply_threshold": 100,
        "hot_agree_threshold": 1000,
        "admin_users": [],
        "forum_groups": {}
    }


def save_config(config: Dict):
    """保存配置"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"保存配置失败: {e}")
        return False


LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>贴吧观察者 - 登录</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
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
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
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
                <input type="password" name="new_password" required>
            </div>
            <div class="form-group">
                <label>确认新密码</label>
                <input type="password" name="confirm_password" required>
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
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
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
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        .forum-item {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
        }
        .forum-name {
            font-weight: bold;
            color: #333;
            font-size: 1.1em;
            margin-bottom: 10px;
        }
        .group-list {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-bottom: 10px;
        }
        .group-tag {
            background: #667eea;
            color: white;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
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
            opacity: 0.9;
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
                    <div class="stat-value">{{ config.forum_groups|length }}</div>
                    <div class="stat-label">监控贴吧</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ total_groups }}</div>
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
                            <input type="number" name="check_interval" value="{{ config.check_interval_seconds }}" min="60">
                        </div>
                        <div class="form-group">
                            <label>获取帖子数</label>
                            <input type="number" name="threads_count" value="{{ config.threads_to_retrieve }}" min="1" max="20">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>热帖回复阈值</label>
                            <input type="number" name="hot_reply" value="{{ config.hot_reply_threshold }}" min="1">
                        </div>
                        <div class="form-group">
                            <label>热帖点赞阈值</label>
                            <input type="number" name="hot_agree" value="{{ config.hot_agree_threshold }}" min="1">
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
                        <input type="text" name="admin_qq" placeholder="输入QQ号码" required>
                    </div>
                    <button type="submit" class="btn btn-success">添加</button>
                </form>
                
                {% if config.admin_users %}
                    <div class="admin-list">
                        {% for admin in config.admin_users %}
                            <span class="admin-tag">
                                {{ admin }}
                                <a href="{{ url_for('remove_admin', qq=admin) }}" style="color: white; text-decoration: none;">×</a>
                            </span>
                        {% endfor %}
                    </div>
                {% else %}
                    <div class="empty-state">暂无管理员</div>
                {% endif %}
            </div>
        </div>

        <!-- 贴吧订阅管理 -->
        <div class="card">
            <h2>📋 贴吧订阅管理</h2>
            <form method="POST" action="{{ url_for('add_forum') }}" style="margin-bottom: 25px;">
                <div class="grid" style="grid-template-columns: 2fr 2fr 1fr; align-items: end;">
                    <div class="form-group">
                        <label>贴吧名称</label>
                        <input type="text" name="forum_name" placeholder="例如：鸣潮" required>
                    </div>
                    <div class="form-group">
                        <label>推送群号（多个用逗号分隔）</label>
                        <input type="text" name="group_ids" placeholder="例如：1087074883,661278084" required>
                    </div>
                    <div class="form-group">
                        <button type="submit" class="btn btn-success" style="width: 100%;">添加订阅</button>
                    </div>
                </div>
            </form>

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
                            <a href="{{ url_for('remove_forum', name=forum) }}" class="btn btn-danger">删除</a>
                        </div>
                    </div>
                {% endfor %}
            {% else %}
                <div class="empty-state">暂无订阅的贴吧</div>
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
        
        if username == user_config['username'] and password == user_config['password']:
            session['logged_in'] = True
            session['username'] = username
            
            if user_config.get('first_login', True):
                flash('首次登录，请修改默认密码！', 'warning')
                return redirect(url_for('change_password'))
            
            flash('登录成功！', 'success')
            return redirect(url_for('index'))
        else:
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
        
        if current_password != user_config['password']:
            flash('当前密码错误！', 'error')
        elif new_password != confirm_password:
            flash('两次输入的新密码不一致！', 'error')
        elif len(new_password) < 4:
            flash('新密码长度至少4位！', 'error')
        else:
            user_config['password'] = new_password
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
    
    # 计算总群组数
    total_groups = set()
    for groups in config.get("forum_groups", {}).values():
        total_groups.update(groups)
    
    return render_template_string(
        HTML_TEMPLATE,
        config=config,
        total_groups=len(total_groups),
        username=session.get('username', 'root')
    )


@app.route('/update_settings', methods=['POST'])
@login_required
def update_settings():
    """更新基础配置"""
    config = load_config()
    
    try:
        config['check_interval_seconds'] = int(request.form.get('check_interval', 240))
        config['threads_to_retrieve'] = int(request.form.get('threads_count', 6))
        config['hot_reply_threshold'] = int(request.form.get('hot_reply', 100))
        config['hot_agree_threshold'] = int(request.form.get('hot_agree', 1000))
        
        if save_config(config):
            flash('配置保存成功！', 'success')
        else:
            flash('配置保存失败！', 'error')
    except Exception as e:
        flash(f'配置保存失败：{e}', 'error')
    
    return redirect(url_for('index'))


@app.route('/add_admin', methods=['POST'])
@login_required
def add_admin():
    """添加管理员"""
    config = load_config()
    admin_qq = request.form.get('admin_qq', '').strip()
    
    if admin_qq:
        if 'admin_users' not in config:
            config['admin_users'] = []
        
        if admin_qq not in config['admin_users']:
            config['admin_users'].append(admin_qq)
            if save_config(config):
                flash(f'管理员 {admin_qq} 添加成功！', 'success')
            else:
                flash('添加失败！', 'error')
        else:
            flash('该管理员已存在！', 'error')
    
    return redirect(url_for('index'))


@app.route('/remove_admin/<qq>')
@login_required
def remove_admin(qq):
    """删除管理员"""
    config = load_config()
    
    if qq in config.get('admin_users', []):
        config['admin_users'].remove(qq)
        if save_config(config):
            flash(f'管理员 {qq} 已删除！', 'success')
        else:
            flash('删除失败！', 'error')
    
    return redirect(url_for('index'))


@app.route('/add_forum', methods=['POST'])
@login_required
def add_forum():
    """添加贴吧订阅"""
    config = load_config()
    forum_name = request.form.get('forum_name', '').strip()
    group_ids_str = request.form.get('group_ids', '').strip()
    
    if forum_name and group_ids_str:
        # 解析群号
        group_ids = [g.strip() for g in group_ids_str.split(',') if g.strip()]
        
        if 'forum_groups' not in config:
            config['forum_groups'] = {}
        
        config['forum_groups'][forum_name] = group_ids
        
        if save_config(config):
            flash(f'贴吧 {forum_name} 订阅成功！', 'success')
        else:
            flash('订阅失败！', 'error')
    
    return redirect(url_for('index'))


@app.route('/remove_forum/<name>')
@login_required
def remove_forum(name):
    """删除贴吧订阅"""
    config = load_config()
    
    if name in config.get('forum_groups', {}):
        del config['forum_groups'][name]
        if save_config(config):
            flash(f'贴吧 {name} 已取消订阅！', 'success')
        else:
            flash('取消订阅失败！', 'error')
    
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
