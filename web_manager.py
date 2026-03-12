"""
贴吧观察者 - Web管理界面 (FastAPI版本)
用于可视化配置贴吧监控
支持双模式：贴吧对应群 / 群对应贴吧
"""

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from filelock import FileLock

from astrbot.api import logger
from astrbot.api.star import StarTools

# 数据目录（必须在app配置之前定义）
DATA_DIR = str(StarTools.get_data_dir("astrbot_plugin_ICanSeeTieba"))
os.makedirs(DATA_DIR, exist_ok=True)

# 模板目录
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(TEMPLATE_DIR, exist_ok=True)

# 创建FastAPI应用
app = FastAPI(title="贴吧观察者管理后台")

# 使用固定的secret_key（从文件读取或生成）
SECRET_KEY_FILE = os.path.join(DATA_DIR, ".secret_key")
if os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, 'r') as f:
        SECRET_KEY = f.read().strip()
else:
    SECRET_KEY = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, 'w') as f:
        f.write(SECRET_KEY)

# 添加session中间件
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=1800  # 30分钟
)

# 配置模板
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# 配置文件路径
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


def generate_csrf_token() -> str:
    """生成CSRF Token"""
    return secrets.token_urlsafe(32)


def validate_csrf_token(request: Request, token: str) -> bool:
    """验证CSRF Token"""
    session_token = request.session.get('csrf_token')
    if not session_token:
        return False
    return secrets.compare_digest(session_token, token)


def load_user_config() -> Dict:
    """加载用户配置"""
    with USER_LOCK:
        if os.path.exists(USER_FILE):
            try:
                with open(USER_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError, OSError) as e:
                logger.error(f"加载用户配置失败: {e}")
        
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
            logger.error(f"保存用户配置失败: {e}")
            return False


def load_config() -> Dict:
    """加载配置"""
    with CONFIG_LOCK:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError, OSError) as e:
                logger.error(f"加载配置失败: {e}")
        
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
            logger.error(f"保存配置失败: {e}")
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


# ========== 依赖注入 ==========

async def get_current_user(request: Request) -> Optional[Dict]:
    """获取当前登录用户"""
    if not request.session.get('logged_in'):
        return None
    
    # 检查session是否过期
    last_activity = request.session.get('last_activity')
    if last_activity:
        last_time = datetime.fromisoformat(last_activity)
        if datetime.now() - last_time > timedelta(minutes=30):
            request.session.clear()
            return None
    
    # 更新活动时间
    request.session['last_activity'] = datetime.now().isoformat()
    return load_user_config()


async def require_login(request: Request):
    """要求登录的依赖"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


# ========== 路由 ==========

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """登录页面"""
    user_config = load_user_config()
    csrf_token = generate_csrf_token()
    request.session['csrf_token'] = csrf_token
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "first_login": user_config.get('first_login', True),
        "csrf_token": csrf_token
    })


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    """登录处理"""
    # 验证CSRF Token
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF验证失败")
    
    user_config = load_user_config()
    
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
            request.session.clear()
            request.session['logged_in'] = True
            request.session['username'] = username
            request.session['last_activity'] = datetime.now().isoformat()
            
            if user_config.get('first_login', True):
                return RedirectResponse(url="/change_password", status_code=302)
            
            return RedirectResponse(url="/", status_code=302)
    
    # 登录失败
    csrf_token = generate_csrf_token()
    request.session['csrf_token'] = csrf_token
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "用户名或密码错误",
        "first_login": user_config.get('first_login', True),
        "csrf_token": csrf_token
    })


@app.get("/logout")
async def logout(request: Request):
    """退出登录"""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@app.get("/change_password", response_class=HTMLResponse)
async def change_password_page(request: Request, user: Dict = Depends(require_login)):
    """修改密码页面"""
    csrf_token = generate_csrf_token()
    request.session['csrf_token'] = csrf_token
    
    return templates.TemplateResponse("change_password.html", {
        "request": request,
        "csrf_token": csrf_token
    })


@app.post("/change_password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
    user: Dict = Depends(require_login)
):
    """修改密码处理"""
    # 验证CSRF Token
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF验证失败")
    
    user_config = load_user_config()
    
    if 'password_hash' in user_config:
        current_valid = verify_password(current_password, user_config['password_salt'], user_config['password_hash'])
    else:
        current_valid = (current_password == user_config.get('password', ''))
    
    if not current_valid:
        csrf_token = generate_csrf_token()
        request.session['csrf_token'] = csrf_token
        return templates.TemplateResponse("change_password.html", {
            "request": request,
            "error": "当前密码错误",
            "csrf_token": csrf_token
        })
    
    if new_password != confirm_password:
        csrf_token = generate_csrf_token()
        request.session['csrf_token'] = csrf_token
        return templates.TemplateResponse("change_password.html", {
            "request": request,
            "error": "两次输入的新密码不一致",
            "csrf_token": csrf_token
        })
    
    if len(new_password) < 6:
        csrf_token = generate_csrf_token()
        request.session['csrf_token'] = csrf_token
        return templates.TemplateResponse("change_password.html", {
            "request": request,
            "error": "新密码长度至少6位",
            "csrf_token": csrf_token
        })
    
    if new_password == DEFAULT_PASSWORD:
        csrf_token = generate_csrf_token()
        request.session['csrf_token'] = csrf_token
        return templates.TemplateResponse("change_password.html", {
            "request": request,
            "error": "不能使用默认密码",
            "csrf_token": csrf_token
        })
    
    salt, hashed = hash_password(new_password)
    user_config['password_salt'] = salt
    user_config['password_hash'] = hashed
    if 'password' in user_config:
        del user_config['password']
    user_config['first_login'] = False
    
    if save_user_config(user_config):
        return RedirectResponse(url="/logout", status_code=302)
    else:
        csrf_token = generate_csrf_token()
        request.session['csrf_token'] = csrf_token
        return templates.TemplateResponse("change_password.html", {
            "request": request,
            "error": "密码修改失败",
            "csrf_token": csrf_token
        })


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: Dict = Depends(require_login)):
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
    
    csrf_token = generate_csrf_token()
    request.session['csrf_token'] = csrf_token
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "config": config,
        "forum_count": forum_count,
        "group_count": group_count,
        "mode_display": mode_display,
        "username": request.session.get('username', 'root'),
        "csrf_token": csrf_token
    })


@app.post("/update_settings")
async def update_settings(
    request: Request,
    check_interval: int = Form(...),
    threads_count: int = Form(...),
    hot_reply: int = Form(...),
    hot_agree: int = Form(...),
    csrf_token: str = Form(...),
    user: Dict = Depends(require_login)
):
    """更新基础配置"""
    # 验证CSRF Token
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF验证失败")
    
    config = load_config()
    
    if not (60 <= check_interval <= 3600):
        raise HTTPException(status_code=400, detail="检查间隔必须在60-3600秒之间")
    
    if not (1 <= threads_count <= 20):
        raise HTTPException(status_code=400, detail="获取帖子数必须在1-20之间")
    
    config['check_interval_seconds'] = check_interval
    config['threads_to_retrieve'] = threads_count
    config['hot_reply_threshold'] = hot_reply
    config['hot_agree_threshold'] = hot_agree
    
    if save_config(config):
        return RedirectResponse(url="/?success=配置保存成功", status_code=302)
    else:
        raise HTTPException(status_code=500, detail="配置保存失败")


@app.post("/add_admin")
async def add_admin(
    request: Request,
    admin_qq: str = Form(...),
    csrf_token: str = Form(...),
    user: Dict = Depends(require_login)
):
    """添加管理员"""
    # 验证CSRF Token
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF验证失败")
    
    config = load_config()
    admin_qq = admin_qq.strip()
    
    if not admin_qq:
        raise HTTPException(status_code=400, detail="QQ号不能为空")
    
    if not validate_qq(admin_qq):
        raise HTTPException(status_code=400, detail=f"QQ号 {admin_qq} 格式无效")
    
    if 'admin_users' not in config:
        config['admin_users'] = []
    
    if admin_qq in config['admin_users']:
        raise HTTPException(status_code=400, detail="该管理员已存在")
    
    config['admin_users'].append(admin_qq)
    if save_config(config):
        return RedirectResponse(url="/?success=管理员添加成功", status_code=302)
    else:
        raise HTTPException(status_code=500, detail="添加失败")


@app.post("/remove_admin")
async def remove_admin(
    request: Request,
    qq: str = Form(...),
    csrf_token: str = Form(...),
    user: Dict = Depends(require_login)
):
    """删除管理员"""
    # 验证CSRF Token
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF验证失败")
    
    config = load_config()
    qq = qq.strip()
    
    if qq in config.get('admin_users', []):
        config['admin_users'].remove(qq)
        if save_config(config):
            return RedirectResponse(url="/?success=管理员已删除", status_code=302)
    
    raise HTTPException(status_code=400, detail="管理员不存在或删除失败")


@app.post("/switch_mode")
async def switch_mode(
    request: Request,
    mode: str = Form(...),
    csrf_token: str = Form(...),
    user: Dict = Depends(require_login)
):
    """切换订阅模式"""
    # 验证CSRF Token
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF验证失败")
    
    config = load_config()
    
    if mode not in [MODE_FORUM_GROUPS, MODE_GROUP_FORUMS]:
        raise HTTPException(status_code=400, detail="无效的模式")
    
    # 如果数据不完整，先同步
    if not config.get("group_forums") and config.get("forum_groups"):
        # 从forum_groups同步到group_forums
        group_forums = {}
        for forum, groups in config["forum_groups"].items():
            for group in groups:
                if group not in group_forums:
                    group_forums[group] = []
                if forum not in group_forums[group]:
                    group_forums[group].append(forum)
        config["group_forums"] = group_forums
    elif not config.get("forum_groups") and config.get("group_forums"):
        # 从group_forums同步到forum_groups
        forum_groups = {}
        for group, forums in config["group_forums"].items():
            for forum in forums:
                if forum not in forum_groups:
                    forum_groups[forum] = []
                if group not in forum_groups[forum]:
                    forum_groups[forum].append(group)
        config["forum_groups"] = forum_groups
    
    config['subscription_mode'] = mode
    
    if save_config(config):
        mode_display = get_mode_display(mode)
        return RedirectResponse(url=f"/?success=已切换到【{mode_display}】模式", status_code=302)
    else:
        raise HTTPException(status_code=500, detail="模式切换失败")


@app.post("/add_subscription")
async def add_subscription(
    request: Request,
    forum_name: str = Form(...),
    group_ids: str = Form(...),
    csrf_token: str = Form(...),
    user: Dict = Depends(require_login)
):
    """添加订阅"""
    # 验证CSRF Token
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF验证失败")
    
    config = load_config()
    forum_name = forum_name.strip()
    
    if not forum_name:
        raise HTTPException(status_code=400, detail="贴吧名称不能为空")
    
    if not validate_forum_name(forum_name):
        raise HTTPException(status_code=400, detail=f"贴吧名称 '{forum_name}' 格式无效")
    
    valid, group_ids_list, error_msg = validate_group_ids(group_ids)
    if not valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # 初始化数据结构
    if "forum_groups" not in config:
        config["forum_groups"] = {}
    if "group_forums" not in config:
        config["group_forums"] = {}
    
    # 添加订阅关系
    for group_id in group_ids_list:
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
        return RedirectResponse(url=f"/?success=贴吧 {forum_name} 订阅成功", status_code=302)
    else:
        raise HTTPException(status_code=500, detail="订阅失败")


@app.post("/remove_forum")
async def remove_forum(
    request: Request,
    forum: str = Form(...),
    csrf_token: str = Form(...),
    user: Dict = Depends(require_login)
):
    """删除贴吧订阅"""
    # 验证CSRF Token
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF验证失败")
    
    config = load_config()
    forum = forum.strip()
    
    if forum in config.get("forum_groups", {}):
        # 从所有群中移除该贴吧
        for group in config["forum_groups"][forum]:
            if group in config.get("group_forums", {}) and forum in config["group_forums"][group]:
                config["group_forums"][group].remove(forum)
                if not config["group_forums"][group]:
                    del config["group_forums"][group]
        
        del config["forum_groups"][forum]
        
        if save_config(config):
            return RedirectResponse(url="/?success=贴吧已删除", status_code=302)
    
    raise HTTPException(status_code=400, detail="贴吧不存在或删除失败")


@app.post("/remove_group")
async def remove_group(
    request: Request,
    group: str = Form(...),
    csrf_token: str = Form(...),
    user: Dict = Depends(require_login)
):
    """删除群订阅"""
    # 验证CSRF Token
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF验证失败")
    
    config = load_config()
    group = group.strip()
    
    if group in config.get("group_forums", {}):
        # 从所有贴吧中移除该群
        for forum in config["group_forums"][group]:
            if forum in config.get("forum_groups", {}) and group in config["forum_groups"][forum]:
                config["forum_groups"][forum].remove(group)
                if not config["forum_groups"][forum]:
                    del config["forum_groups"][forum]
        
        del config["group_forums"][group]
        
        if save_config(config):
            return RedirectResponse(url="/?success=群订阅已删除", status_code=302)
    
    raise HTTPException(status_code=400, detail="群不存在或删除失败")


def run_web_manager(port=5000):
    """运行Web管理界面"""
    import uvicorn
    logger.info(f"🌐 贴吧观察者管理界面已启动")
    logger.info(f"📍 访问地址: http://0.0.0.0:{port}")
    logger.info(f"🔐 默认用户名: root")
    logger.info(f"🔐 默认密码: moning")
    logger.info(f"⚠️  请确保端口 {port} 已开放")
    uvicorn.run(app, host='0.0.0.0', port=port)


if __name__ == '__main__':
    run_web_manager()
