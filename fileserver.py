#!/usr/bin/env python3
"""
fileserver.py - Flask 文件服务，提供 REST API 管理服务器文件。
Phase 1: GET /ls, /read, /health, POST /mkdir
后续 Phase 扩展：写操作（/write, /upload）
"""

import os
import json
import stat
import logging
import mimetypes
import requests
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from functools import wraps
from difflib import SequenceMatcher
import jieba

# m3e 语义搜索 — 延迟加载（首次使用才加载模型，避免启动慢）
_st_model = None
_session_embeddings_cache = {}  # {session_id: {"embedding": ndarray, "uuid": "session_updated_hash"}}

def _get_st_model():
    """延迟加载 m3e-base 模型（~400MB，首次加载 ~10秒）"""
    global _st_model
    if _st_model is None:
        import os as _os
        _os.environ.setdefault('HTTP_PROXY', 'http://172.29.4.175:22222')
        _os.environ.setdefault('HTTPS_PROXY', 'http://172.29.4.175:22222')
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer('moka-ai/m3e-base', device='cpu')
        logging.info('[precise-search] m3e-base 模型已加载')
    return _st_model

def _build_session_abstract(sess):
    """从 session 构建可搜索摘要（标题 + 最近3条消息首行）"""
    parts = [sess.get('title', '')]
    msgs = sess.get('messages', [])
    for msg in msgs[-3:]:
        content = msg.get('content', '')
        if isinstance(content, list):
            content = ' '.join(str(c.get('text', '')) for c in content if isinstance(c, dict))
        content = str(content)[:200]
        if content.strip():
            parts.append(content)
    return '\n'.join(parts)

def _jieba_word_match(query, text, min_word_overlap=0.3):
    """jieba 词级别匹配：返回 (match, score, preview)"""
    if not text:
        return False, 0, ''
    text_str = str(text)[:1000]
    query_words = set(jieba.lcut(query))
    text_words = jieba.lcut(text_str)
    # 去停用词（简单版）
    stopwords = {'的', '了', '是', '在', '我', '有', '和', '与', '或', '不', '也', '就', '都', '要', '把', '被'}
    qw = query_words - stopwords
    # 精确词匹配 + 部分匹配（query词是text词的子串）
    matched = 0
    matched_positions = []
    for qword in qw:
        for i, tword in enumerate(text_words):
            if tword in stopwords:
                continue
            if qword.lower() == tword.lower() or qword.lower() in tword.lower() or tword.lower() in qword.lower():
                matched += 1
                matched_positions.append(i)
                break
    if not qw:
        # fallback: 空 query 词不匹配
        query_str = query.strip().lower()
        return query_str in text_str.lower(), 1.0 if query_str in text_str.lower() else 0.0, text_str[:80]
    score = matched / max(len(qw), 1)
    if score < min_word_overlap:
        return False, score, ''
    # 构建 preview
    if matched_positions:
        mid = matched_positions[len(matched_positions)//2]
        start_idx = max(0, mid - 3)
        end_idx = min(len(text_words), mid + 4)
        preview = ''.join(text_words[start_idx:end_idx])
        if start_idx > 0:
            preview = '…' + preview
        if end_idx < len(text_words):
            preview += '…'
    else:
        preview = text_str[:80]
    return True, score, preview
from flask import Flask, request, jsonify, send_file
from flask_sock import Sock

import bcrypt
import jwt

app = Flask(__name__)
sock = Sock(app)

# ---- 日志 ----
logging.basicConfig(level=logging.INFO, format="[fileserver] %(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---- 配置 ----
WHITELIST = [
    "/home/ubuntu/.openclaw/workspace-assistant",
    "/home/ubuntu/.openclaw/workspace-build-cat",
    "/home/ubuntu/.openclaw/user-files",
]


def _load_token():
    """从多个来源加载 API Token（优先级：环境变量 > Gateway 配置文件 > 占位符）。

    来源：
    1. FILESERVER_TOKEN 环境变量（最高优先级）
    2. ~/.openclaw/openclaw.json → gateway.auth.token（Gateway 统一 Token）
    3. 开发环境占位符（仅本地开发允许）
    """
    # 1. 环境变量（最高优先级，运维可手动覆盖）
    env_token = os.environ.get("FILESERVER_TOKEN")
    if env_token:
        logger.info("Token 来源: FILESERVER_TOKEN 环境变量")
        return env_token

    # 2. 从 Gateway 配置文件读取（与聊天 API 统一 Token）
    config_paths = [
        os.path.expanduser("~/.openclaw/openclaw.json"),
    ]
    for path in config_paths:
        try:
            if os.path.isfile(path):
                with open(path, "r") as f:
                    cfg = json.load(f)
                token = cfg.get("gateway", {}).get("auth", {}).get("token", "")
                if token:
                    logger.info(f"Token 来源: Gateway 配置文件 ({path})")
                    return token
        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.warning(f"读取 {path} 失败: {e}")
            continue

    # 3. 开发环境占位符（生产环境应配置上述来源之一）
    logger.warning("Token 未找到（环境变量 / Gateway 配置），使用开发占位符")
    return "dev-token-placeholder"

API_TOKEN = _load_token()

# ---- Gateway 配置 ----
GATEWAY_URL = "http://127.0.0.1:18789/v1/chat/completions"
GATEWAY_TOKEN = API_TOKEN  # 复用同一 Token
DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
CHAT_TIMEOUT = 120  # Gateway 调用超时（秒）

# ---- Session 存储配置 ----
SESSION_DIR = "/home/ubuntu/.openclaw/user-sessions"
USER_FILES_DIR = "/home/ubuntu/.openclaw/user-files"
USER_DATA_DIR = "/home/ubuntu/.openclaw/user-data"
USERS_FILE = os.path.join(USER_DATA_DIR, "users.json")
JWT_SECRET_FILE = "/home/ubuntu/.openclaw/jwt-secret"

# ---- JWT 密钥 ----
try:
    with open(JWT_SECRET_FILE, "r") as f:
        JWT_SECRET = f.read().strip()
    logger.info("JWT secret loaded")
except Exception:
    JWT_SECRET = os.urandom(32).hex()
    os.makedirs(os.path.dirname(JWT_SECRET_FILE), exist_ok=True)
    with open(JWT_SECRET_FILE, "w") as f:
        f.write(JWT_SECRET)
    os.chmod(JWT_SECRET_FILE, 0o600)
    logger.warning("JWT secret auto-generated")

JWT_EXPIRE_HOURS = 24
JWT_REMEMBER_HOURS = 168  # 7 days

# ---- 用户数据 ----
def _load_users() -> dict:
    try:
        if os.path.isfile(USERS_FILE) and os.path.getsize(USERS_FILE) > 0:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"users.json read failed: {e}")
    return {}

def _save_users(data: dict):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_person() -> str:
    """根据认证上下文返回当前用户标识（数据隔离）。
    JWT 认证 → 用 request.user.username，旧 Token → 用 person 参数。
    """
    if hasattr(request, 'user') and request.user.get('username'):
        return request.user['username']
    return request.args.get('person', '管理员').strip()


def make_token(user: dict, remember: bool = False) -> str:
    """签发 JWT"""
    exp_hours = JWT_REMEMBER_HOURS if remember else JWT_EXPIRE_HOURS
    payload = {
        "user": user["username"],
        "display_name": user["display_name"],
        "partner": user.get("partner", ""),
        "exp": datetime.utcnow() + timedelta(hours=exp_hours)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def auth_required(f):
    """JWT 认证中间件。解析 Bearer token → 注入 request.user"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = None

        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

        if not token:
            return jsonify({"ok": False, "error": "未登录或 token 缺失", "code": "UNAUTHORIZED"}), 401

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user = {
                "username": payload.get("user", ""),
                "display_name": payload.get("display_name", ""),
                "partner": payload.get("partner", "")
            }
        except jwt.ExpiredSignatureError:
            return jsonify({"ok": False, "error": "登录已过期，请重新登录", "code": "TOKEN_EXPIRED"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"ok": False, "error": "无效的 token", "code": "INVALID_TOKEN"}), 401

        return f(*args, **kwargs)
    return decorated


# ---- 认证 API ----

@app.route("/v1/api/auth/register", methods=["POST"])
def auth_register():
    """POST /v1/api/auth/register - 注册（需邀请码）"""
    data = request.get_json(silent=True)
    if not data or "username" not in data or "password" not in data:
        return jsonify({"ok": False, "error": "缺少用户名或密码"}), 400

    username = data["username"].strip().lower()
    password = data["password"].strip()

    if not username or not password:
        return jsonify({"ok": False, "error": "用户名和密码不能为空"}), 400
    if len(password) < 4:
        return jsonify({"ok": False, "error": "密码至少 4 位"}), 400
    if not username.isalnum():
        return jsonify({"ok": False, "error": "用户名只能包含字母和数字"}), 400

    users = _load_users()
    if username in users:
        return jsonify({"ok": False, "error": "用户已存在"}), 409

    # 邀请码校验
    invite_code = data.get("invite_code", "").strip()
    invites = _load_invites()
    if username != "admin":  # admin first user needs no invite
        valid = False
        for inv in invites.get("unused", []):
            if inv.get("code") == invite_code:
                valid = True
                invites["unused"].remove(inv)
                invites.setdefault("used", []).append(inv)
                _save_invites(invites)
                break
        if not valid:
            return jsonify({"ok": False, "error": "邀请码无效或已使用"}), 400

    salt = bcrypt.gensalt()
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    display_name = data.get("display_name", username).strip() or username
    # First user is admin
    if not users:
        partner = data.get("partner", "").strip()
        if not partner:
            partner = "partner"
        users[username] = {
            "password_hash": pw_hash,
            "display_name": display_name,
            "partner": partner,
            "created": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        }
        # Auto-create partner account
        partner_pw = os.urandom(8).hex()
        partner_hash = bcrypt.hashpw(partner_pw.encode("utf-8"), salt).decode("utf-8")
        users[partner] = {
            "password_hash": partner_hash,
            "display_name": "伴侣",
            "partner": username,
            "created": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        }
        _save_users(users)
        user_obj = {"username": username, "display_name": display_name, "partner": partner}
        token = make_token(user_obj)
        return jsonify({
            "ok": True, "token": token, "user": user_obj,
            "message": f"账号创建成功！伴侣账号: {partner}，密码: {partner_pw}（请告知伴侣尽快修改密码）",
            "partner_initial_password": partner_pw
        })
    else:
        users[username] = {
            "password_hash": pw_hash,
            "display_name": display_name,
            "partner": "",
            "created": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        }
        _save_users(users)
        user_obj = {"username": username, "display_name": display_name, "partner": ""}
        token = make_token(user_obj)
        return jsonify({"ok": True, "token": token, "user": user_obj, "message": "注册成功"})


@app.route("/v1/api/auth/login", methods=["POST"])
def auth_login():
    """POST /v1/api/auth/login - 登录"""
    data = request.get_json(silent=True)
    if not data or "username" not in data or "password" not in data:
        return jsonify({"ok": False, "error": "缺少用户名或密码"}), 400

    username = data["username"].strip().lower()
    password = data["password"].strip()
    remember = data.get("remember", False)

    users = _load_users()
    user = users.get(username)
    if not user:
        return jsonify({"ok": False, "error": "用户名或密码错误"}), 401

    stored_hash = user["password_hash"].encode("utf-8")
    if not bcrypt.checkpw(password.encode("utf-8"), stored_hash):
        return jsonify({"ok": False, "error": "用户名或密码错误"}), 401

    user_obj = {
        "username": username,
        "display_name": user.get("display_name", username),
        "partner": user.get("partner", "")
    }
    token = make_token(user_obj, remember=remember)
    return jsonify({
        "ok": True,
        "token": token,
        "user": user_obj,
        "expires_in": JWT_REMEMBER_HOURS * 3600 if remember else JWT_EXPIRE_HOURS * 3600
    })


@app.route("/v1/api/auth/me", methods=["GET"])
@auth_required
def auth_me():
    """GET /v1/api/auth/me - 获取当前用户信息"""
    partner_name = request.user.get("partner", "")
    partner_info = {}
    if partner_name:
        users = _load_users()
        partner = users.get(partner_name, {})
        partner_info = {
            "username": partner_name,
            "display_name": partner.get("display_name", partner_name)
        }
    return jsonify({"ok": True, "user": request.user, "partner": partner_info})


@app.route("/v1/api/auth/logout", methods=["POST"])
@auth_required
def auth_logout():
    """POST /v1/api/auth/logout - 退出登录"""
    return jsonify({"ok": True, "message": "已退出"})


# ---- 邀请码机制 ----

INVITES_FILE = os.path.join(USER_DATA_DIR, "invites.json")

def _load_invites() -> dict:
    try:
        if os.path.isfile(INVITES_FILE) and os.path.getsize(INVITES_FILE) > 0:
            with open(INVITES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"unused": [], "used": []}

def _save_invites(data: dict):
    os.makedirs(os.path.dirname(INVITES_FILE), exist_ok=True)
    with open(INVITES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/v1/api/auth/invites", methods=["GET", "POST"])
@auth_required
def auth_invites():
    """GET/POST /v1/api/auth/invites - 管理邀请码（管理员）"""
    if request.user.get("username") != "admin":
        return jsonify({"ok": False, "error": "仅管理员可操作"}), 403

    if request.method == "GET":
        invites = _load_invites()
        return jsonify({"ok": True, "unused": invites.get("unused", []), "used": invites.get("used", [])})

    if request.method == "POST":
        import secrets
        code = secrets.token_hex(4)
        invites = _load_invites()
        invites.setdefault("unused", []).append({
            "code": code,
            "generated_by": request.user.get("display_name", ""),
            "created": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        })
        _save_invites(invites)
        return jsonify({"ok": True, "invite_code": code, "message": "邀请码已生成"})

logger.info(f"fileserver 启动，白名单目录: {WHITELIST}")


# ---- 启动初始化 ----

def _ensure_directories():
    """确保用户文件目录和 Session 目录在启动时存在。

    创建：
    - /home/ubuntu/.openclaw/user-files/  用户上传/生成的文件
    - /home/ubuntu/.openclaw/user-sessions/  会话存储目录

    目录不存在时自动创建，已存在则跳过。
    """
    dirs = [USER_FILES_DIR, SESSION_DIR, USER_DATA_DIR]
    for d in dirs:
        try:
            p = Path(d)
            p.mkdir(parents=True, exist_ok=True)
            logger.info(f"目录已就绪: {d}")
        except Exception as e:
            logger.error(f"创建目录失败: {d}, 错误: {e}")


# ---- 工具函数 ----

def _resolve_path(rel_path: str) -> Path:
    """将请求路径解析为绝对路径，并进行安全校验（白名单 + 防路径穿越）。

    安全策略：
    1. 请求路径必须相对于白名单中的某个根目录
    2. 解析后的绝对路径必须在白名单根目录之内（含子目录）
    3. 拒绝 .. 路径穿越、拒绝符号链接逃逸
    """
    # 1. 清洗输入：去掉首尾斜杠
    clean = rel_path.strip("/")

    # 2. 拒绝显式路径穿越（.. 作为独立路径段）
    if ".." in clean.split("/"):
        raise ValueError("路径穿越被拒绝")

    # 2.5 当请求路径等于白名单根目录的 basename 时直接返回
    for base in WHITELIST:
        bp = Path(base).resolve()
        if clean == bp.name or str(bp) == clean or str(bp).endswith("/" + clean):
            if bp.is_dir():
                return bp

    # 2.6 当请求路径的第一段匹配某白名单根目录的 basename 时，直接在该根下解析子路径
    # 修复：/user-files/charts/temp.png 应解析到 user-files/ 而非 workspace-assistant/user-files/...
    parts = clean.split("/")
    if parts and parts[0]:
        for base in WHITELIST:
            bp = Path(base).resolve()
            if parts[0] == bp.name:
                try:
                    candidate = bp
                    for p in parts[1:]:
                        candidate = candidate / p
                    candidate = candidate.resolve()
                    candidate_str = str(candidate)
                    base_str = str(bp)
                    if candidate_str == base_str or candidate_str.startswith(base_str + os.sep):
                        return candidate
                except (ValueError, OSError):
                    continue

    # 3. 遍历白名单，尝试解析
    for base in WHITELIST:
        base_path = Path(base).resolve()
        try:
            # 构建候选路径并解析（resolve 会消解 .. 和符号链接）
            candidate = (base_path / clean).resolve()
            candidate_str = str(candidate)
            base_str = str(base_path)

            # 4. 围栏检查：候选路径必须在白名单根目录之内
            if candidate_str == base_str or candidate_str.startswith(base_str + os.sep):
                return candidate
        except (ValueError, OSError):
            continue

    raise ValueError("路径不在白名单范围内或路径穿越被拒绝")


def _check_read_access(target: Path) -> tuple[bool, str]:
    """检查目标是否有读取权限。"""
    if not target.exists():
        return False, "路径不存在"
    if not os.access(target, os.R_OK):
        return False, "无读取权限"
    return True, "ok"


def _check_write_access(target: Path, is_dir: bool = False) -> tuple[bool, str]:
    """检查是否允许在 target 位置写入。

    对于目录创建：检查父目录存在且可写，如果目录已存在则报错（避免幂等问题）。
    对于文件写入：检查父目录存在且可写。
    """
    parent = target if is_dir else target.parent
    if not parent.exists():
        return False, "父目录不存在"
    if not os.access(parent, os.W_OK):
        return False, "父目录无写入权限"
    if is_dir and target.exists():
        return False, "目录已存在"
    return True, "ok"


def error_response(message: str, code: int = 400, detail: str = None):
    """统一 JSON 错误格式（B9：API 错误处理标准化）。

    所有 API 端点使用此函数返回错误，确保一致的 JSON 结构：
    { "error": true, "message": "<人类可读>", "code": <HTTP 状态码>[, "detail": "<技术详情>"] }

    前端可据此统一解析和处理错误。
    """
    body = {"error": True, "message": message, "code": code}
    if detail:
        body["detail"] = detail
    return jsonify(body), code


def _list_directory(directory: Path) -> list[dict]:
    """列出目录内容，返回文件/目录信息列表。"""
    entries = []
    try:
        for entry in sorted(directory.iterdir()):
            info = {
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else 0,
                "modified": entry.stat().st_mtime,
            }
            # 如果是文件，附加 MIME 类型（用于前端图标判断）
            if entry.is_file():
                mime, _ = mimetypes.guess_type(entry.name)
                info["mime"] = mime or "application/octet-stream"
            entries.append(info)
    except PermissionError:
        pass
    return entries


# ---- 认证中间件 (B3: 完整实现) ----

def require_token(f):
    """Token 认证装饰器（双模式：JWT + 旧 API Token）。

    优先尝试 JWT Bearer Token → 注入 request.user 用于数据隔离。
    如 JWT 无效，回退到旧 API_TOKEN 比对（兼容过渡期）。
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = ""

        if not token:
            logger.warning(f"认证失败: 空 Token (path={request.path}, ip={request.remote_addr})")
            return error_response("缺少认证 Token", 401, "请在 Authorization 头中提供 Bearer Token")

        # 1. 尝试 JWT 认证（AU7: auth_required 逻辑内联）
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user = {
                "username": payload.get("user", ""),
                "display_name": payload.get("display_name", ""),
                "partner": payload.get("partner", "")
            }
            return f(*args, **kwargs)
        except jwt.ExpiredSignatureError:
            return jsonify({"ok": False, "error": "登录已过期", "code": "TOKEN_EXPIRED"}), 401
        except jwt.InvalidTokenError:
            pass  # Not a JWT, fall through to old token check

        # 2. 回退到旧 API Token 认证（AU9: 兼容过渡期）
        if token != API_TOKEN:
            logger.warning(f"认证失败: Token 不匹配 (path={request.path}, ip={request.remote_addr})")
            return error_response("认证失败", 401, "Token 无效")

        return f(*args, **kwargs)
    return decorated


# ---- 路由 ----

@app.route("/v1/files/health", methods=["GET"])
def health():
    """健康检查端点（无需认证）。

    检查所有白名单根目录是否存在且可读，返回整体健康状态和各根目录详情。
    systemd 可通过此端点做 watch dog 触发自动重启。
    """
    root_status = {}
    all_ok = True
    for root in WHITELIST:
        rp = Path(root)
        if not rp.exists():
            root_status[root] = "missing"
            all_ok = False
        elif not rp.is_dir():
            root_status[root] = "not_a_directory"
            all_ok = False
        elif not os.access(rp, os.R_OK):
            root_status[root] = "unreadable"
            all_ok = False
        else:
            root_status[root] = "ok"

    status_code = 200 if all_ok else 503
    return jsonify({
        "status": "ok" if all_ok else "degraded",
        "service": "fileserver",
        "roots": root_status,
    }), status_code


@app.route("/v1/files/ls", methods=["GET"])
@require_token
def list_files():
    """GET /v1/files/ls?path=<relative-path> - 列出目录内容。"""
    path_arg = request.args.get("path", "")
    try:
        target = _resolve_path(path_arg)
    except (ValueError, OSError) as e:
        return error_response(f"路径解析失败: {e}", 400)

    ok, msg = _check_read_access(target)
    if not ok:
        return error_response(msg, 403)

    if target.is_file():
        # 返回文件信息
        info = {
            "name": target.name,
            "type": "file",
            "size": target.stat().st_size,
            "modified": target.stat().st_mtime,
        }
        return jsonify({"path": str(target), "entries": [info]})

    if target.is_dir():
        entries = _list_directory(target)
        return jsonify({"path": str(target), "entries": entries})

    return error_response("未知文件类型", 500)


@app.route("/v1/files/read", methods=["GET"])
@require_token
def read_file():
    """GET /v1/files/read?path=<relative-path> - 读取文件内容。"""
    path_arg = request.args.get("path", "")
    try:
        target = _resolve_path(path_arg)
    except (ValueError, OSError) as e:
        return error_response(f"路径解析失败: {e}", 400)

    ok, msg = _check_read_access(target)
    if not ok:
        return error_response(msg, 403)

    if not target.is_file():
        return error_response("路径不是文件", 400)

    # 大文件策略：
    # - 有 Range 请求头：允许任意大小（流式读取，只传输请求的范围）
    # - 无 Range 请求头：限制 10MB（避免全量读取超大文件阻塞服务）
    has_range = "Range" in request.headers
    if not has_range and target.stat().st_size > 10 * 1024 * 1024:
        return error_response("文件过大（>10MB），请使用 Range 请求或 download 接口", 413)

    return send_file(target, mimetype=mimetypes.guess_type(target.name)[0] or "text/plain")


@app.route("/v1/files/download", methods=["GET"])
@require_token
def download_file():
    """GET /v1/files/download?path=<relative-path> - 下载文件。

    与 /read 不同，此端点：
    - 设置 Content-Disposition: attachment 头，触发浏览器下载而非内联显示
    - 对大文件流式传输（超过 10MB 也允许，不限制上限）
    """
    path_arg = request.args.get("path", "")
    try:
        target = _resolve_path(path_arg)
    except (ValueError, OSError) as e:
        return error_response(f"路径解析失败: {e}", 400)

    ok, msg = _check_read_access(target)
    if not ok:
        return error_response(msg, 403)

    if not target.is_file():
        return error_response("路径不是文件", 400)

    mime, _ = mimetypes.guess_type(target.name)
    if not mime:
        mime = "application/octet-stream"

    return send_file(
        target,
        mimetype=mime,
        as_attachment=True,
        download_name=target.name,
    )


# ---- Session 管理 (Phase 5) ----

@app.route("/v1/sessions/new", methods=["POST"])
@require_token
def create_session():
    """POST /v1/sessions/new - 创建新 Session，自动生成标题。

    请求体 JSON（可选）: {"title": "可选标题"}
    返回 201: {"id": "sess_...", "title": "...", "created": "...", "updated": "...", "messages": []}

    会话文件存储在 SESSION_DIR/{id}.json，目录不存在时自动创建。
    """
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)
    session_id = f"sess_{now.strftime('%Y%m%d_%H%M%S')}"

    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    if not title:
        title = f"新对话 {now.strftime('%m月%d日 %H:%M')}"

    session_dir = Path(SESSION_DIR)
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"创建 Session 目录失败: {SESSION_DIR}, 错误: {e}")
        return error_response("创建 Session 存储目录失败", 500)

    session = {
        "id": session_id,
        "title": title,
        "created": now.isoformat(),
        "updated": now.isoformat(),
        "messages": [],
    }

    session_file = session_dir / f"{session_id}.json"
    try:
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
        logger.info(f"Session 创建成功: {session_id} ({title})")
        return jsonify(session), 201
    except OSError as e:
        logger.error(f"Session 写入失败: {session_file}, 错误: {e}")
        return error_response("Session 创建失败", 500)


# UX3: AI 自动生成标题
@app.route("/v1/sessions/<session_id>/title", methods=["POST"])
@require_token
def generate_session_title(session_id):
    """POST /v1/sessions/{id}/title - 从第一条消息内容自动生成标题"""
    session_dir = Path(SESSION_DIR)
    session_file = session_dir / f"{session_id}.json"
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return error_response("Session 不存在", 404)

    messages = data.get("messages", [])
    if not messages:
        return jsonify({"ok": True, "title": data.get("title", "")})

    # 取第一条用户消息作为标题基础
    first_msg = messages[0].get("content", "")
    if isinstance(first_msg, list):
        first_msg = " ".join(str(c.get("text", "")) for c in first_msg if isinstance(c, dict))
    title = first_msg[:20].strip()
    if len(first_msg) > 20:
        title += "…"
    if not title:
        title = "新对话"

    data["title"] = title
    data["updated"] = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True, "title": title})


@app.route("/v1/sessions/list", methods=["GET"])
@require_token
def list_sessions():
    """GET /v1/sessions/list - 返回所有 Session 列表，按更新时间倒序排列。

    返回 200: {"sessions": [{...}, {...}]}

    从 SESSION_DIR 读取所有 {id}.json 文件，按 updated 字段排序。
    """
    session_dir = Path(SESSION_DIR)
    if not session_dir.is_dir():
        return jsonify({"sessions": []}), 200

    sessions = []
    try:
        for f in sorted(session_dir.glob("*.json")):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                # UX5: 过滤已软删除的 session
                if not data.get("deleted"):
                    sessions.append(data)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"跳过无效 Session 文件 {f.name}: {e}")
                continue

        sessions.sort(key=lambda s: s.get("updated", ""), reverse=True)
        resp = jsonify({"sessions": sessions})
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp, 200

    except OSError as e:
        logger.error(f"读取 Session 列表失败: {e}")
        return error_response("读取 Session 列表失败", 500)


@app.route("/v1/sessions/<session_id>", methods=["GET", "PATCH"])
@require_token
def get_session(session_id):
    """GET /v1/sessions/{id} - 返回指定 Session 的完整消息历史。

    参数：session_id (URL 路径参数)，对应 POST /v1/sessions/new 返回的 id。
    成功 200: 完整的 Session JSON（含 id、title、created、updated、messages 数组）
    失败 404: Session 不存在
    失败 400: Session ID 格式无效

    Session 文件存储在 SESSION_DIR/{id}.json。
    """
    # 安全校验：拒绝路径穿越字符和空 ID
    if not session_id or not session_id.strip():
        return error_response("Session ID 不能为空", 400)
    if "/" in session_id or "\\" in session_id or ".." in session_id:
        return error_response("Session ID 格式无效", 400)

    session_dir = Path(SESSION_DIR)
    session_file = session_dir / f"{session_id}.json"

    try:
        session_resolved = session_file.resolve()
        session_dir_resolved = session_dir.resolve()
        if str(session_resolved).startswith(str(session_dir_resolved) + os.sep) or session_resolved == session_dir_resolved:
            logger.info(f"Session 详情请求: {session_id}")
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # UX2: PATCH 更新 title 或 deleted 标记
            if request.method == "PATCH":
                body = request.get_json(silent=True)
                if not body:
                    return error_response("缺少请求体", 400)
                if "title" in body:
                    data["title"] = body["title"]
                if "deleted" in body:
                    data["deleted"] = body["deleted"]
                data["updated"] = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
                with open(session_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"Session 更新: {session_id}")
                return jsonify({"ok": True, "id": session_id, "title": data.get("title", "")}), 200

            resp = jsonify(data)
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return resp, 200
        else:
            logger.warning(f"Session 路径校验失败: {session_id} 解析到 {session_resolved}")
            return error_response("Session ID 无效", 400)
    except FileNotFoundError:
        return error_response("Session 不存在", 404)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"读取 Session 失败: {session_file}, 错误: {e}")
        return error_response(f"Session 读取失败: {e}", 500)




@app.route("/v1/sessions/<session_id>", methods=["DELETE"])
@require_token
def delete_session(session_id):
    """DELETE /v1/sessions/{id} - 删除指定 Session。

    参数：session_id (URL 路径参数)，对应 POST /v1/sessions/new 返回的 id。
    成功 200: {"message": "Session 已删除", "id": "..."}
    失败 404: Session 不存在
    失败 400: Session ID 格式无效

    Session 文件存储在 SESSION_DIR/{id}.json，删除操作不可逆。
    """
    # 安全校验：拒绝路径穿越字符和空 ID
    if not session_id or not session_id.strip():
        return error_response("Session ID 不能为空", 400)
    if "/" in session_id or "\\" in session_id or ".." in session_id:
        return error_response("Session ID 格式无效", 400)

    session_dir = Path(SESSION_DIR)
    session_file = session_dir / f"{session_id}.json"

    try:
        session_resolved = session_file.resolve()
        session_dir_resolved = session_dir.resolve()
        if not (str(session_resolved).startswith(str(session_dir_resolved) + os.sep) or session_resolved == session_dir_resolved):
            logger.warning(f"Session 路径校验失败: {session_id} 解析到 {session_resolved}")
            return error_response("Session ID 无效", 400)

        if not session_file.is_file():
            return error_response("Session 不存在", 404)

        session_file.unlink()
        logger.info(f"Session 已删除: {session_id}")
        return jsonify({"message": "Session 已删除", "id": session_id}), 200

    except FileNotFoundError:
        return error_response("Session 不存在", 404)
    except OSError as e:
        logger.error(f"删除 Session 失败: {session_file}, 错误: {e}")
        return error_response(f"Session 删除失败: {e}", 500)

# ---- Gateway 调用 ----

def _call_gateway(messages: list[dict]) -> dict:
    """调用 Gateway API，发送消息并获取回复。

    Args:
        messages: OpenAI 格式的 messages 数组

    Returns:
        {"role": "assistant", "content": "...", "time": "..."}

    Raises:
        RuntimeError: Gateway 调用失败、超时、或返回异常
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GATEWAY_TOKEN}",
    }
    payload = {
        "model": DEFAULT_MODEL,
        "messages": messages,
    }

    try:
        logger.info(f"调用 Gateway: {len(messages)} 条消息, model={DEFAULT_MODEL}")
        resp = requests.post(GATEWAY_URL, json=payload, headers=headers, timeout=CHAT_TIMEOUT)
        resp.raise_for_status()
        result = resp.json()

        if "choices" not in result or not result["choices"]:
            logger.error(f"Gateway 返回空 choices: {json.dumps(result, ensure_ascii=False)[:500]}")
            raise RuntimeError("Gateway 返回空响应")

        choice = result["choices"][0]
        content = choice.get("message", {}).get("content", "")
        finish_reason = choice.get("finish_reason", "unknown")
        if not content:
            logger.error(f"Gateway 返回空内容, finish_reason={finish_reason}")
            raise RuntimeError("Gateway 返回空内容")

        logger.info(f"Gateway 返回成功, 内容长度: {len(content)}, finish_reason={finish_reason}")

        tz = ZoneInfo("Asia/Shanghai")
        return {
            "role": "assistant",
            "content": content,
            "time": datetime.now(tz).isoformat(),
        }

    except requests.exceptions.Timeout:
        logger.error(f"Gateway 调用超时 ({CHAT_TIMEOUT}s)")
        raise RuntimeError("Gateway 响应超时，请稍后重试")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Gateway 连接失败: {e}")
        raise RuntimeError("无法连接到 Gateway 服务")
    except requests.exceptions.HTTPError as e:
        body = ""
        try:
            body = e.response.text[:500]
        except Exception:
            pass
        logger.error(f"Gateway HTTP 错误 {e.response.status_code if e.response else 'N/A'}: {body}")
        raise RuntimeError(f"Gateway 返回错误 (HTTP {e.response.status_code if e.response else 'N/A'})")
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Gateway 响应解析失败: {e}")
        raise RuntimeError("Gateway 响应格式异常")


# ---- 文件附件解析 ----

# 文本文件扩展名：这些文件的内容将被提取并注入给 Gateway
TEXT_EXTENSIONS: set[str] = {
    ".txt", ".md", ".markdown", ".rst",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".csv", ".tsv",
    ".sh", ".bash", ".zsh", ".fish",
    ".rs", ".go", ".java", ".kt", ".kts", ".scala",
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh",
    ".rb", ".php", ".sql", ".r", ".swift", ".m", ".mm",
    ".lua", ".pl", ".pm", ".tcl", ".el", ".clj", ".cljs", ".ex", ".exs",
    ".dart", ".groovy", ".jl", ".nim", ".v", ".vhdl", ".sv",
    ".vue", ".svelte",
    ".tf", ".tfvars", ".hcl",
}
MAX_TEXT_EXTRACT_SIZE = 100 * 1024  # 100KB，超过此大小的文本文件跳过内容提取
MAX_EXTRACT_CONTENT_LENGTH = 4000   # 注入 Gateway 的最大字符数
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10MB，超过此大小的文件附件拒绝注入，提示走文件浏览器


def _parse_file_attachment(file_path_str: str) -> dict:
    """解析文件附件：自动提取文本内容（txt/md/code）或标注文件类型+路径。

    规则：
    - 文本文件（扩展名在 TEXT_EXTENSIONS 中 + 大小 ≤ MAX_TEXT_EXTRACT_SIZE）：
      读取 UTF-8 内容，截断至 MAX_EXTRACT_CONTENT_LENGTH 字符，注入给 Gateway
    - 非文本文件 / 过大文件 / 解码失败：
      记录 MIME 类型、文件大小和路径

    Args:
        file_path_str: 文件路径字符串

    Returns:
        dict: {
            "path": 文件完整路径,
            "name": 文件名,
            "type": "text" | "binary" | "not_found",
            "summary": 用于注入给 Gateway 的文本描述
        }
    """
    file_path = Path(file_path_str)
    result: dict = {
        "path": str(file_path),
        "name": file_path.name,
    }

    # 检查文件是否存在
    if not file_path.exists():
        result["type"] = "not_found"
        result["summary"] = f"⚠️ 文件不存在: {file_path.name}"
        return result

    if not file_path.is_file():
        result["type"] = "not_found"
        result["summary"] = f"⚠️ 路径不是文件: {file_path.name}"
        return result

    # 获取文件大小
    try:
        file_size = file_path.stat().st_size
    except OSError:
        result["type"] = "binary"
        result["mime"] = "application/octet-stream"
        result["summary"] = f"⚠️ 无法读取文件元数据: {file_path.name}"
        return result

    # MIME 类型识别（所有文件都标注）
    mime_type, _ = mimetypes.guess_type(str(file_path))
    mime_desc = mime_type or "application/octet-stream"

    # 大小检查：>10MB 的文件附件拒绝注入，提示走文件浏览器
    if file_size > MAX_ATTACHMENT_SIZE:
        if file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f}KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f}MB"
        result["type"] = "too_large"
        result["mime"] = mime_desc
        result["size"] = file_size
        result["summary"] = (
            f"⚠️ 文件过大 ({size_str}): {file_path.name}\n"
            f"类型: {mime_desc}\n"
            f"请使用文件浏览器 (左侧目录树 → 找到文件 → 点击查看) 在独立窗口中打开此文件。"
        )
        return result

    ext = file_path.suffix.lower()

    # 尝试文本提取
    if ext in TEXT_EXTENSIONS and file_size <= MAX_TEXT_EXTRACT_SIZE:
        try:
            content = file_path.read_text(encoding="utf-8")
            result["type"] = "text"
            result["mime"] = mime_desc
            # 截断过长内容
            total_len = len(content)
            if total_len > MAX_EXTRACT_CONTENT_LENGTH:
                content = (
                    content[:MAX_EXTRACT_CONTENT_LENGTH]
                    + f"\n\n... (文件内容已截断，完整 {total_len} 字符)"
                )
            result["summary"] = (
                f"📄 文件: {file_path.name} ({mime_desc})\n"
                f"```\n{content}\n```"
            )
            return result
        except (UnicodeDecodeError, OSError):
            # 解码失败 → 降级为 binary 标注
            pass

    # 非文本文件 / 文件过大 → 仅标注类型和路径
    if file_size < 1024:
        size_str = f"{file_size}B"
    elif file_size < 1024 * 1024:
        size_str = f"{file_size / 1024:.1f}KB"
    else:
        size_str = f"{file_size / (1024 * 1024):.1f}MB"

    result["type"] = "binary"
    result["mime"] = mime_desc
    result["size"] = file_size
    result["summary"] = (
        f"📎 文件: {file_path.name} | 类型: {mime_desc} | 大小: {size_str} | 路径: {file_path}"
    )
    return result


def _build_gateway_messages(
    session_messages: list[dict],
    new_message: str,
    new_files: list[str] = None,
) -> list[dict]:
    """将 Session 消息历史 + 新消息拼接为 Gateway 所需的 messages 数组。

    历史消息中的文件附件会以系统消息形式注入上下文，
    让 Gateway（小助手）知道用户曾选择了哪些文件。

    Args:
        session_messages: Session 中已有的消息历史（不含本次新消息）
        new_message: 用户新发送的消息文本
        new_files: 用户本次选择的文件路径列表（可选）

    Returns:
        Gateway API 所需的 messages 数组（OpenAI 格式）
    """
    messages = []

    for msg in session_messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            # 透传 system 消息（如卡片 prompt、文件摘要）
            messages.append(msg)
        elif role == "user":
            files = msg.get("files", [])
            if files:
                summaries = [_parse_file_attachment(f)["summary"] for f in files]
                messages.append({
                    "role": "system",
                    "content": f"[历史消息] 用户当时选择了以下文件:\n\n" + "\n---\n".join(summaries),
                })
            messages.append({"role": "user", "content": content})

        elif role == "assistant":
            messages.append({"role": "assistant", "content": content})

    # 新消息的文件附件
    if new_files:
        summaries = [_parse_file_attachment(f)["summary"] for f in new_files]
        messages.append({
            "role": "system",
            "content": "用户选择了以下文件:\n\n" + "\n---\n".join(summaries),
        })

    messages.append({"role": "user", "content": new_message})

    return messages





# ---- Daily 卡片: 规则引擎 (apply_rules) ----

def _default_rules(card_id):
    """返回卡片的默认显示规则。"""
    defaults = {
        "todo": {"summary_template": "☑ {done}/{total} ({percent}%)", "limit": 5, "group_by": "date", "order": "desc"},
        "data": {"summary_template": "{fields_count} 项数据", "fields": ["weight", "water", "exercise"]},
        "recipe": {"summary_template": "今日: {today_meals}", "mode": "today"},
        "wishes": {"summary_template": "{total} 个心愿（{in_progress} 进行中）", "limit": 5, "order": "created", "filters": {}},
        "notes": {"summary_template": "{count} 条随手记", "limit": 3, "order": "created_desc"},
        "bookmarks": {"summary_template": "{count} 个收藏", "limit": 3, "order": "created_desc"},
        "photos": {"summary_template": "{count} 张照片", "limit": 4, "layout": "grid"},
        "shares": {"summary_template": "未读 {unread} 条", "limit": 5, "order": "created_desc"},
        "reminders": {"summary_template": "{pending} 项待提醒", "limit": 5, "order": "time_asc"},
        "habits": {"summary_template": "{today_done}/{today_total} 已完成", "layout": "calendar"},
    }
    return defaults.get(card_id, {"summary_template": "{count} 条", "limit": 5})


def _compute_display(card_id, data, rules):
    """根据数据和规则计算 display 内容。"""
    summary_tpl = rules.get("summary_template", "{count} 条")
    admin_data = data.get("管理员", [])

    if card_id == "todo":
        tasks = data.get("管理员", []) + data.get("伴侣", [])
        done = sum(1 for t in tasks if t.get("done"))
        total = len(tasks)
        percent = f"{int(done/total*100)}%" if total > 0 else "0%"
        summary = summary_tpl.format(done=done, total=total, percent=percent)
        limit = rules.get("limit", 5)
        sorted_tasks = sorted(tasks, key=lambda t: t.get("date", ""), reverse=True)[:limit]
        badge = {"text": f"{total-done} 条待办", "color": "orange"} if total > done else None
        return {"summary": summary, "badge": badge, "items": sorted_tasks, "total": total, "done": done}

    elif card_id == "data":
        total_fields = 0
        display_fields = rules.get("fields", [])
        field_data = {}
        for person, person_data in data.items():
            for f in display_fields:
                if f in person_data and person_data[f]:
                    items = sorted(person_data[f].items())
                    latest = items[-1]
                    field_data[person + "_" + f] = {"latest": latest[1], "date": latest[0], "person": person}
                    total_fields += 1
        summary = summary_tpl.format(fields_count=total_fields)
        return {"summary": summary, "fields": field_data}

    elif card_id == "recipe":
        if isinstance(data, dict):
            weekday_map = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            today = weekday_map[datetime.now().weekday()]
            today_data = data.get(today, {})
            meals = []
            if today_data.get("lunch"): meals.append(today_data["lunch"].get("name", "?"))
            if today_data.get("dinner"): meals.append(today_data["dinner"].get("name", "?"))
            today_meals = " / ".join(meals) if meals else "待定"
            summary = summary_tpl.format(today_meals=today_meals)
            return {"summary": summary, "today": today_data, "today_label": today}
        return {"summary": "无数据"}

    elif card_id == "wishes":
        wishes = data if isinstance(data, list) else []
        total = len(wishes)
        in_progress = sum(1 for w in wishes if w.get("status") not in ("done", "idea"))
        limit = rules.get("limit", 5)
        summary = summary_tpl.format(total=total, in_progress=in_progress)
        return {"summary": summary, "items": wishes[:limit], "total": total, "in_progress": in_progress}

    elif card_id == "notes":
        notes = admin_data if isinstance(admin_data, list) else []
        count = len(notes)
        limit = rules.get("limit", 3)
        summary = summary_tpl.format(count=count)
        sorted_notes = sorted(notes, key=lambda n: n.get("created", ""), reverse=True)[:limit]
        return {"summary": summary, "items": sorted_notes, "total": count}

    elif card_id == "bookmarks":
        bookmarks = admin_data if isinstance(admin_data, list) else []
        count = len(bookmarks)
        limit = rules.get("limit", 3)
        summary = summary_tpl.format(count=count)
        sorted_bm = sorted(bookmarks, key=lambda b: b.get("created", ""), reverse=True)[:limit]
        return {"summary": summary, "items": sorted_bm, "total": count}

    elif card_id == "photos":
        photos = admin_data if isinstance(admin_data, list) else []
        count = len(photos)
        limit = rules.get("limit", 4)
        summary = summary_tpl.format(count=count)
        latest = sorted(photos, key=lambda p: p.get("created", ""), reverse=True)[:limit]
        return {"summary": summary, "items": latest, "total": count, "layout": rules.get("layout", "grid")}

    elif card_id == "shares":
        sent = data.get("sent", [])
        received = data.get("received", [])
        unread = sum(1 for s in received if not s.get("read"))
        summary = summary_tpl.format(unread=unread)
        return {"summary": summary, "unread": unread, "sent_count": len(sent), "received_count": len(received)}

    elif card_id == "reminders":
        reminders = admin_data if isinstance(admin_data, list) else []
        pending = sum(1 for r in reminders if not r.get("done"))
        limit = rules.get("limit", 5)
        summary = summary_tpl.format(pending=pending)
        sorted_r = sorted(reminders, key=lambda r: (r.get("done", False), r.get("time", "23:59")))[:limit]
        return {"summary": summary, "items": sorted_r, "total": len(reminders), "pending": pending}

    elif card_id == "habits":
        habits_data = data.get("管理员", {}) if isinstance(data.get("管理员"), dict) else {}
        habits = habits_data.get("habits", [])
        logs = habits_data.get("logs", {})
        today_str = datetime.today().strftime("%Y-%m-%d")
        day_short = today_str[-5:]
        done = sum(1 for h in habits if logs.get(h.get("id"), {}).get(today_str))
        total = len(habits)
        summary = summary_tpl.format(today_done=done, today_total=total)
        return {"summary": summary, "habits": habits, "today_done": done, "today_total": total, "day": day_short}

    else:
        count = len(admin_data) if isinstance(admin_data, list) else len(data)
        return {"summary": summary_tpl.format(count=count), "items": admin_data[:rules.get("limit", 5)]}


def apply_rules(card_id):
    """通用规则引擎：读取 data.json + rules.json → 计算 → 写入 display.json。"""
    card_dir = os.path.join(USER_DATA_DIR, card_id)
    data_path = os.path.join(card_dir, "data.json")
    rules_path = os.path.join(card_dir, "rules.json")
    display_path = os.path.join(card_dir, "display.json")

    data = {}
    # 数据追踪卡片特殊处理：从 PROFILES_DIR 合并多人文件
    if card_id == "data":
        if os.path.isdir(PROFILES_DIR):
            for fn in sorted(os.listdir(PROFILES_DIR)):
                if fn.endswith(".json"):
                    person = fn[:-5]
                    pp = os.path.join(PROFILES_DIR, fn)
                    if os.path.isfile(pp) and os.path.getsize(pp) > 0:
                        with open(pp, "r", encoding="utf-8") as f:
                            try:
                                data[person] = json.load(f)
                            except json.JSONDecodeError:
                                pass
    elif os.path.isfile(data_path) and os.path.getsize(data_path) > 0:
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    rules = {}
    if os.path.isfile(rules_path) and os.path.getsize(rules_path) > 0:
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
    else:
        rules = _default_rules(card_id)

    display = _compute_display(card_id, data, rules)
    display["updated"] = datetime.now().isoformat()

    os.makedirs(card_dir, exist_ok=True)
    with open(display_path, "w", encoding="utf-8") as f:
        json.dump(display, f, ensure_ascii=False, indent=2)

    logger.info(f"apply_rules({card_id}): display.json 已更新")
    return display


@app.route("/v1/api/daily/apply-rules", methods=["POST"])
@require_token
def api_apply_rules():
    """POST /v1/api/daily/apply-rules — 对单张或多张卡片应用显示规则。"""
    req_data = request.get_json(silent=True)
    if not req_data:
        return error_response("缺少请求体", 400)

    card_ids = []
    if "card_id" in req_data:
        card_ids = [req_data["card_id"]]
    elif "card_ids" in req_data:
        card_ids = req_data["card_ids"]
    else:
        for d in sorted(os.listdir(USER_DATA_DIR)):
            dpath = os.path.join(USER_DATA_DIR, d)
            if os.path.isdir(dpath) and os.path.isfile(os.path.join(dpath, "data.json")):
                card_ids.append(d)

    results = {}
    for cid in card_ids:
        try:
            display = apply_rules(cid)
            results[cid] = {"ok": True, "summary": display.get("summary", "")}
        except Exception as e:
            results[cid] = {"ok": False, "error": str(e)}

    return jsonify({"ok": True, "results": results})



# ---- Daily 卡片: 操作 Prompt（升级版）----

def _build_card_prompt():
    """构建 Daily 卡片操作 prompt，注入到从命令行创建的特殊会话中。

    使用 replace 而非 format 避免 JSON 花括号冲突。
    """
    template = """你是 Daily 卡片助手。每张卡片有四层结构：数据 → 规则 → 显示 → 经验。

## 每张卡片的目录结构

user-data/{card_id}/
  data.json       ← 原始记录（你负责读写）
  rules.json      ← 显示准则（声明式 JSON，控制怎么展示）
  display.json    ← 实际显示内容（前端直接读，由 apply_rules 自动生成）
  prompt.json     ← 卡片专属经验（领域知识、最佳实践、用户偏好、示例）
  heartbeat.json  ← 心跳配置（cron 定时刷新，可选）

设计原则：
- 改数据内容 → 改 data.json → 然后调 apply_rules 刷新 display
- 改展示方式 → 改 rules.json → 然后调 apply_rules
- 改卡片行为经验 → 改 prompt.json（用户说「记住...」「以后别...」「经验是...」时修改）
- 改心跳频率 → 改 heartbeat.json
- 系统会自动注入涉及卡片的专属 prompt 消息，包含该卡片的领域知识和最佳实践

## 调 apply_rules 刷新 display

改完 data.json 或 rules.json 后，用 exec 执行（替换 card_id）：
  curl -s -X POST http://127.0.0.1:5050/v1/api/daily/apply-rules -H "Content-Type: application/json" -H "Authorization: Bearer e0fb40cef753818c92577e3c8fe2af53" -d '{"card_id": "替换为卡片id"}'

## 十二张卡片

📋 Todo: __TODO_DIR__/
  data.json: {"管理员": [{"id": 1, "text": "xxx", "done": false, "type": "daily", "date": "YYYY-MM-DD"}], "伴侣": []}
  新增时 id 自增（最大 id + 1），type 默认 "daily"
  rules.json 字段: limit(条数), group_by(date/person), order(desc/priority)

📊 数据追踪: __DATA_DIR__/管理员.json 和 __DATA_DIR__/伴侣.json
  格式: {"weight": {"2026-05-28": 72}, "water": {...}, "exercise": {...}}
  字段自由定义。rules.json 字段: fields(["weight","water","exercise"])

🍽️ 食谱: __RECIPE_DIR__/data.json
  格式: {"周一": {"lunch": {"name": "沙拉", "calories": 200}}}
  rules.json 字段: mode(today/week)

💡 心愿: __WISHES_DIR__/data.json
  格式: [{"id": "w1", "title": "拍饭分析", "status": "idea", "tags": [], "createdBy": "管理员"}]
  状态: idea → discussing → designing → implementing → done
  rules.json 字段: limit, filters({"status":"designing"})

📝 随手记: __NOTES_DIR__/data.json
  格式: {"管理员": [{"id": "n1", "text": "...", "mood": "💡", "tags": [], "images": [], "created": "ISO8601"}]}
  rules.json 字段: limit(最新N条)

🔗 收藏: __BOOKMARKS_DIR__/data.json
  格式: {"管理员": [{"id": "b1", "url": "https://...", "title": "...", "tags": [], "created": "ISO8601"}]}
  rules.json 字段: limit, filter_tag

📸 照片: __PHOTOS_DIR__/data.json
  格式: {"管理员": [{"id": "p1", "image": "/user-files/...", "caption": "...", "likes": [], "comments": []}]}
  rules.json 字段: limit, layout(grid/masonry)

📤 分享: __SHARES_DIR__/data.json
  格式: {"sent": [{"id": "s1", "from": "管理员", "to": "伴侣", ...}], "received": []}

⏰ 提醒: __REMINDERS_DIR__/data.json
  格式: {"管理员": [{"id": "r1", "text": "下午3点开会", "time": "15:00", "date": "2026-05-28", "repeat": null, "done": false}]}

✅ 习惯: __HABITS_DIR__/data.json
  格式: {"管理员": {"habits": [{"id": "h1", "name": "运动", "icon": "🏃"}], "logs": {"h1": {"2026-05-28": true}}}}}

📰 新闻: __NEWS_DIR__/YYYY-MM-DD.json（每天 08:00 cron 自动爬取）

## 操作规则

1. 先读后写：改 data.json 或 rules.json 前先 read 读取当前文件内容
2. 改了必刷新：写完 data/rules 后立即 exec curl 调 apply_rules 刷新 display.json
3. 展示改 rules：用户说「多展示几条」「按优先级排序」「改成只显示进行中的」→ 改 rules.json
4. 数据改 data：用户说「记一下体重 72」「添加一个提醒」→ 改 data.json
5. 添加 TODO 时用 @todo 前缀更快（不走这个流程）
6. 简洁确认：只回复操作结果，如「已更新体重 72kg」「Todo 卡片现在展示 10 条」
7. 新增条目时不要覆盖已有数据，合并到现有列表
8. 经验改 prompt：用户说「以后记体重用kg」「记住我不吃辣」→ 读对应卡片的 prompt.json → 更新 domain_knowledge/best_practices/user_preferences → 写回
"""
    return (template
        .replace("__TODO_DIR__", TODO_DIR)
        .replace("__DATA_DIR__", PROFILES_DIR)
        .replace("__RECIPE_DIR__", RECIPE_DIR)
        .replace("__WISHES_DIR__", WISHES_DIR)
        .replace("__NOTES_DIR__", NOTES_DIR)
        .replace("__BOOKMARKS_DIR__", BOOKMARKS_DIR)
        .replace("__PHOTOS_DIR__", PHOTOS_DIR)
        .replace("__SHARES_DIR__", SHARES_DIR)
        .replace("__REMINDERS_DIR__", REMINDERS_DIR)
        .replace("__HABITS_DIR__", HABITS_DIR)
        .replace("__NEWS_DIR__", NEWS_DIR))


@app.route("/v1/sessions/<session_id>/messages", methods=["POST"])
@require_token
def append_messages(session_id):
    if not session_id or not session_id.strip():
        return error_response("Session ID cannot be empty", 400)
    if "/" in session_id or "\\" in session_id or ".." in session_id:
        return error_response("Session ID format invalid", 400)
    
    data = request.get_json(silent=True)
    if not data or "messages" not in data:
        return error_response("messages field required", 400)
    
    msgs = data["messages"]
    if not isinstance(msgs, list) or len(msgs) == 0:
        return error_response("messages must be a non-empty array", 400)
    
    session_dir = Path(SESSION_DIR)
    session_file = session_dir / f"{session_id}.json"
    
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            session = json.load(f)
    except FileNotFoundError:
        return error_response("Session not found", 404)
    except (json.JSONDecodeError, OSError) as e:
        return error_response("Session read failed", 500)
    
    tz = ZoneInfo("Asia/Shanghai")
    for msg in msgs:
        if "time" not in msg:
            msg["time"] = datetime.now(tz).isoformat()
        session["messages"].append(msg)
    session["updated"] = datetime.now(tz).isoformat()
    
    try:
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
    except OSError as e:
        return error_response("Session save failed", 500)
    
    return jsonify({"ok": True, "id": session_id, "msgCount": len(session["messages"])}), 200

@app.route("/v1/sessions/<session_id>/chat", methods=["POST"])
@require_token
def session_chat(session_id):
    """POST /v1/sessions/{id}/chat - 发送消息到对话，调用 Gateway 获取 AI 回复。

    请求体 JSON:
      {"message": "用户消息", "files": ["可选文件路径列表"]}

    流程:
      1. 解析请求参数
      2. 加载 Session 文件
      3. 拼装上下文消息（历史对话 + 文件附件）→ 调用 Gateway
      4. 保存用户消息 + AI 回复到 Session
      5. 返回更新后的完整 Session

    返回 200: 完整的 Session JSON（含新增消息）
    错误:
      400: 参数无效
      404: Session 不存在
      502: Gateway 调用失败
    """
    # 安全校验：拒绝路径穿越和空 ID
    if not session_id or not session_id.strip():
        return error_response("Session ID 不能为空", 400)
    if "/" in session_id or "\\" in session_id or ".." in session_id:
        return error_response("Session ID 格式无效", 400)

    # 解析请求体
    data = request.get_json(silent=True)
    if not data or "message" not in data:
        return error_response("缺少必填参数", 400, "请求体需包含 message 字段")

    message = data["message"]
    if not isinstance(message, str) or not message.strip():
        return error_response("消息内容不能为空", 400)

    files = data.get("files", [])
    if files is not None and not isinstance(files, list):
        return error_response("files 必须是数组", 400)

    # 加载 Session
    session_dir = Path(SESSION_DIR)
    session_file = session_dir / f"{session_id}.json"

    # 路径安全校验
    try:
        session_resolved = session_file.resolve()
        session_dir_resolved = session_dir.resolve()
        if not (
            str(session_resolved).startswith(str(session_dir_resolved) + os.sep)
            or session_resolved == session_dir_resolved
        ):
            logger.warning(f"Session 路径校验失败: {session_id} 解析到 {session_resolved}")
            return error_response("Session ID 无效", 400)
    except (ValueError, OSError) as e:
        logger.warning(f"Session 路径解析失败: {session_id}, 错误: {e}")
        return error_response("Session ID 无效", 400)

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            session = json.load(f)
    except FileNotFoundError:
        return error_response("Session 不存在", 404)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"读取 Session 失败: {session_file}, 错误: {e}")
        return error_response("Session 读取失败", 500)

    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)

    # 拼装上下文并调用 Gateway（先不写 Session，调用失败时保持数据完整）
    existing_messages = session.get("messages", [])
    gateway_messages = _build_gateway_messages(
        existing_messages,
        message.strip(),
        files or None,
    )

    try:
        assistant_msg = _call_gateway(gateway_messages)
    except RuntimeError as e:
        logger.error(f"Session chat Gateway 调用失败: {session_id}, 错误: {e}")
        return error_response(f"消息发送失败: {e}", 502)

    # Gateway 成功 → 追加用户消息 + AI 回复
    user_msg = {
        "role": "user",
        "content": message.strip(),
        "time": now.isoformat(),
    }
    if files:
        user_msg["files"] = files

    session["messages"].append(user_msg)
    session["messages"].append(assistant_msg)
    session["updated"] = datetime.now(tz).isoformat()

    # 保存 Session
    try:
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error(f"Session 保存失败: {session_file}, 错误: {e}")
        return error_response("Session 保存失败", 500)

    logger.info(
        f"Session chat 完成: {session_id}, "
        f"新消息: {message.strip()[:50]}..., "
        f"总数: {len(session['messages'])}"
    )
    return jsonify(session), 200


# ---- 文件写入 ----

@app.route("/v1/files/write", methods=["POST"])
@require_token
def write_file():
    """POST /v1/files/write - 写入文件内容。

    请求体 JSON: {"path": "<relative-path>", "content": "<文件内容>"}

    安全约束：
    - 路径必须在白名单范围内
    - 父目录必须存在且可写
    - 写入前不做备份（Phase 2 不记录变更日志）
    """
    data = request.get_json(silent=True)
    if not data or "path" not in data:
        return error_response("缺少必填参数", 400, "请求体需包含 path 和 content 字段")
    if "content" not in data:
        return error_response("缺少必填参数", 400, "请求体需包含 content 字段")

    path_arg = data["path"]
    content = data["content"]
    if not isinstance(content, str):
        return error_response("content 必须是字符串", 400)

    try:
        target = _resolve_path(path_arg)
    except (ValueError, OSError) as e:
        return error_response(f"路径解析失败: {e}", 400)

    ok, msg = _check_write_access(target)
    if not ok:
        return error_response(msg, 403)

    try:
        # 确保父目录存在
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"文件写入成功: {target}")
        return jsonify({"ok": True, "path": str(target), "size": target.stat().st_size})
    except OSError as e:
        logger.error(f"文件写入失败: {target}, 错误: {e}")
        return error_response(f"文件写入失败: {e}", 500)


MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


@app.route("/v1/files/upload", methods=["POST"])
@require_token
def upload_file():
    """POST /v1/files/upload - 上传文件（multipart/form-data）。

    请求参数：
    - path (form field): 目标目录路径（相对于白名单根目录）
    - file (file field): 上传的文件

    安全约束：
    - 路径必须在白名单范围内
    - 文件大小限制 50MB
    - 文件名只取 basename（防路径穿越）
    - 文件已存在时返回 409 冲突，需前端确认后才允许覆盖
    """
    path_arg = request.form.get("path", "")
    overwrite = request.form.get("overwrite", "false").lower() == "true"

    if "file" not in request.files:
        return error_response("缺少上传文件", 400, "请求需包含 file 字段")

    file = request.files["file"]
    if not file.filename or file.filename.strip() == "":
        return error_response("文件名为空", 400)

    # 只取 basename，忽略客户端路径
    safe_name = Path(file.filename).name
    if not safe_name:
        return error_response("无效文件名", 400)

    try:
        target_dir = _resolve_path(path_arg)
    except (ValueError, OSError) as e:
        return error_response(f"目标路径无效: {e}", 400)

    if not target_dir.is_dir():
        return error_response("目标路径不是目录", 400)

    ok, msg = _check_read_access(target_dir)
    if not ok:
        return error_response(msg, 403)

    target_file = target_dir / safe_name
    # 安全检查：确保解析后仍在白名单内
    try:
        target_resolved = target_file.resolve()
    except (ValueError, OSError):
        return error_response("文件名无效", 400)

    if not any(
        str(target_resolved) == str(Path(root).resolve())
        or str(target_resolved).startswith(str(Path(root).resolve()) + os.sep)
        for root in WHITELIST
    ):
        return error_response("路径不在白名单范围内", 403)

    # 检查写入权限
    ok, msg = _check_write_access(target_file)
    if not ok:
        return error_response(msg, 403)

    # 文件已存在且未允许覆盖
    if target_file.exists() and not overwrite:
        return error_response("文件已存在", 409, f"是否覆盖 {safe_name}？上传时设置 overwrite=true 以覆盖")

    # 写入文件（先读到内存检查大小）
    file_content = file.read()
    if len(file_content) > MAX_UPLOAD_SIZE:
        return error_response(f"文件过大，最大 {MAX_UPLOAD_SIZE // (1024*1024)}MB", 413)

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        with open(target_file, "wb") as f:
            f.write(file_content)
        logger.info(f"文件上传成功: {target_file} ({len(file_content)} bytes)")
        return jsonify({"ok": True, "name": safe_name, "size": len(file_content), "path": str(target_file)})
    except OSError as e:
        logger.error(f"文件上传失败: {target_file}, 错误: {e}")
        return error_response(f"文件上传失败: {e}", 500)


@app.route("/v1/files/mkdir", methods=["POST"])
@require_token
def make_directory():
    """POST /v1/files/mkdir - 创建目录。

    请求体 JSON: {"path": "<relative-path>"}
    安全约束：
    - 路径必须在白名单范围内
    - 父目录必须存在且可写
    - 目录已存在时返回 409 冲突
    - 支持递归创建（os.makedirs）
    """
    data = request.get_json(silent=True)
    if not data or "path" not in data:
        return error_response("缺少必填参数", 400, "请求体需包含 path 字段")

    path_arg = data["path"]
    try:
        target = _resolve_path(path_arg)
    except (ValueError, OSError) as e:
        return error_response(f"路径解析失败: {e}", 400)

    ok, msg = _check_write_access(target, is_dir=True)
    if not ok:
        if msg == "目录已存在":
            return error_response(msg, 409)
        return error_response(msg, 403)

    try:
        # 递归创建所有不存在的中间目录
        target.mkdir(parents=True)
        logger.info(f"目录创建成功: {target}")
        return jsonify({"ok": True, "path": str(target)})
    except OSError as e:
        logger.error(f"目录创建失败: {target}, 错误: {e}")
        return error_response(f"目录创建失败: {e}", 500)


# ---- 每日 Dashboard: 卡片注册表 (DB2) ----

# 默认卡片注册表结构
DEFAULT_CARD_REGISTRY = {
    "cards": [
        {
            "id": "news",
            "name": "📰 资讯",
            "width": "medium",
            "enabled": True,
            "api": "/v1/api/daily/news",
            "expandable": True,
            "refreshInterval": 3600
        },
        {
            "id": "todo",
            "name": "📋 Todo",
            "width": "medium",
            "enabled": True,
            "api": "/v1/api/daily/todos",
            "persons": ["管理员", "伴侣"],
            "expandable": True
        },
        {
            "id": "data",
            "name": "📊 数据",
            "width": "medium",
            "enabled": True,
            "api": "/v1/api/daily/data",
            "persons": ["管理员", "伴侣"],
            "expandable": True
        },
        {
            "id": "recipe",
            "name": "🍽️ 食谱",
            "width": "medium",
            "enabled": True,
            "api": "/v1/api/daily/recipe/today",
            "expandable": True
        },
        {
            "id": "wishes",
            "name": "💡 心愿",
            "width": "medium",
            "enabled": True,
            "api": "/v1/api/daily/wishes",
            "expandable": True
        },
        {
            "id": "notes",
            "name": "📝 随手记",
            "width": "medium",
            "enabled": True,
            "api": "/v1/api/daily/notes",
            "persons": ["管理员", "伴侣"],
            "expandable": True
        },
        {
            "id": "bookmarks",
            "name": "🔗 收藏夹",
            "width": "medium",
            "enabled": True,
            "api": "/v1/api/daily/bookmarks",
            "persons": ["管理员", "伴侣"],
            "expandable": True
        },
        {
            "id": "photos",
            "name": "📸 照片墙",
            "width": "wide",
            "enabled": True,
            "api": "/v1/api/daily/photos",
            "persons": ["管理员", "伴侣"],
            "expandable": True
        },
        {
            "id": "shares",
            "name": "💬 分享板",
            "width": "medium",
            "enabled": True,
            "api": "/v1/api/daily/shares",
            "persons": ["管理员", "伴侣"],
            "expandable": True
        },
        {
            "id": "reminders",
            "name": "⏰ 提醒",
            "width": "medium",
            "enabled": True,
            "api": "/v1/api/daily/reminders",
            "persons": ["管理员", "伴侣"],
            "expandable": True
        },
        {
            "id": "habits",
            "name": "✅ 习惯打卡",
            "width": "medium",
            "enabled": True,
            "api": "/v1/api/daily/habits",
            "persons": ["管理员", "伴侣"],
            "expandable": True
        }
    ],
    "layout": {
        "columns": 3,
        "order": ["news", "todo", "data", "recipe", "wishes", "notes", "bookmarks", "photos", "shares", "reminders", "habits"],
        "gap": 16
    },
    "commandPrefixes": [
        {"prefix": "@todo", "action": "add_todo", "api": "/v1/api/daily/todos", "method": "POST"},
        {"prefix": "@done", "action": "check_todo", "api": "/v1/api/daily/todos/{id}", "method": "PUT"},
        {"prefix": "@data", "action": "update_data", "api": "/v1/api/daily/data/{person}", "method": "POST"},
        {"prefix": "@news", "action": "query_news", "api": "/v1/api/daily/news", "method": "GET"},
        {"prefix": "@recipe", "action": "recipe", "api": "/v1/api/daily/recipe", "method": "GET"},
        {"prefix": "@schedule", "action": "schedule", "api": "/v1/api/daily/schedule", "method": "POST"},
        {"prefix": "@wish", "action": "add_wish", "api": "/v1/api/daily/wishes", "method": "POST"},
        {"prefix": "@sum", "action": "summary", "api": "/v1/api/daily/summary", "method": "GET"}
    ]
}

CARD_REGISTRY_PATH = os.path.join(USER_DATA_DIR, "card-registry.json")


def _load_card_registry():
    """读取卡片注册表，不存在或解析错误时返回默认结构。"""
    try:
        if os.path.isfile(CARD_REGISTRY_PATH) and os.path.getsize(CARD_REGISTRY_PATH) > 0:
            with open(CARD_REGISTRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"card-registry.json 读取失败: {e}，使用默认值")
    return DEFAULT_CARD_REGISTRY.copy()


def _save_card_registry(data: dict):
    """写入卡片注册表。"""
    os.makedirs(os.path.dirname(CARD_REGISTRY_PATH), exist_ok=True)
    with open(CARD_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("card-registry.json 已保存")


@app.route("/v1/api/daily/registry", methods=["GET"])
@require_token
def get_card_registry():
    """GET /v1/api/daily/registry - 读取卡片注册表。

    返回完整注册表（cards + layout + commandPrefixes）。
    若文件不存在则返回默认结构。
    """
    registry = _load_card_registry()
    return jsonify(registry)


@app.route("/v1/api/daily/registry", methods=["PUT"])
@require_token
def put_card_registry():
    """PUT /v1/api/daily/registry - 更新卡片注册表。

    请求体：完整注册表 JSON（覆盖写入）。
    验证：必须包含 cards 数组。
    """
    data = request.get_json(silent=True)
    if not data:
        return error_response("请求体必须是有效 JSON", 400)
    if "cards" not in data or not isinstance(data["cards"], list):
        return error_response("注册表必须包含 cards 数组", 400)

    try:
        _save_card_registry(data)
        return jsonify({"ok": True, "message": "卡片注册表已更新"})
    except IOError as e:
        return error_response(f"保存失败: {e}", 500)


@app.route("/v1/api/daily/registry/cards/<card_id>", methods=["PUT"])
@require_token
def put_card_by_id(card_id):
    """PUT /v1/api/daily/registry/cards/{id} - 更新单张卡片配置。

    支持局部更新：enabled、width、name 等字段。
    """
    patch = request.get_json(silent=True)
    if not patch:
        return error_response("请求体必须是有效 JSON", 400)

    registry = _load_card_registry()
    card_found = False
    for card in registry["cards"]:
        if card["id"] == card_id:
            card.update(patch)
            card_found = True
            break

    if not card_found:
        return error_response(f"卡片 '{card_id}' 不存在", 404)

    try:
        _save_card_registry(registry)
        return jsonify({"ok": True, "card_id": card_id, "message": "卡片配置已更新"})
    except IOError as e:
        return error_response(f"保存失败: {e}", 500)


# ---- 每日 Dashboard: 统一指令中枢 (DB3) ----

KNOWN_PERSONS = ["管理员", "伴侣"]
TODO_DIR = os.path.join(USER_DATA_DIR, "todo")
TODOS_PATH = os.path.join(TODO_DIR, "tasks.json")
RECIPE_DIR = os.path.join(USER_DATA_DIR, "recipe")
RECIPE_PATH = os.path.join(RECIPE_DIR, "weekly.json")
WISHES_DIR = os.path.join(USER_DATA_DIR, "wishes")
WISHES_PATH = os.path.join(WISHES_DIR, "list.json")
NOTES_DIR = os.path.join(USER_DATA_DIR, "notes")
NOTES_PATH = os.path.join(NOTES_DIR, "data.json")
BOOKMARKS_DIR = os.path.join(USER_DATA_DIR, "bookmarks")
BOOKMARKS_PATH = os.path.join(BOOKMARKS_DIR, "data.json")
PHOTOS_DIR = os.path.join(USER_DATA_DIR, "photos")
PHOTOS_PATH = os.path.join(PHOTOS_DIR, "data.json")
SHARES_DIR = os.path.join(USER_DATA_DIR, "shares")
SHARES_PATH = os.path.join(SHARES_DIR, "records.json")
REMINDERS_DIR = os.path.join(USER_DATA_DIR, "reminders")
REMINDERS_PATH = os.path.join(REMINDERS_DIR, "data.json")
HABITS_DIR = os.path.join(USER_DATA_DIR, "habits")
HABITS_PATH = os.path.join(HABITS_DIR, "data.json")


def _load_todos():
    """读取 Todo 文件，不存在或错误时返回空字典。"""
    try:
        if os.path.isfile(TODOS_PATH) and os.path.getsize(TODOS_PATH) > 0:
            with open(TODOS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"todos.json 读取失败: {e}")
    return {}


def _save_todos(data: dict):
    """写入 Todo 文件。"""
    os.makedirs(os.path.dirname(TODOS_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(TODOS_PATH), exist_ok=True)
    with open(TODOS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _dispatch_add_todo(person: str, text: str):
    """@todo 指令处理器：添加一条 Todo。"""
    if not person or not text:
        return {"ok": False, "message": "用法: @todo <管理员|伴侣> <内容>"}
    if person not in KNOWN_PERSONS:
        return {"ok": False, "message": f"未知用户: {person}，可用: {KNOWN_PERSONS}"}

    todos = _load_todos()
    if person not in todos:
        todos[person] = {}
    if "daily" not in todos[person]:
        todos[person]["daily"] = []

    tz = ZoneInfo("Asia/Shanghai")
    today = datetime.now(tz).strftime("%Y-%m-%d")
    new_id = 1
    for item in todos[person].get("daily", []):
        if item.get("id", 0) >= new_id:
            new_id = item["id"] + 1

    todo_item = {
        "id": new_id,
        "text": text,
        "done": False,
        "type": "daily",
        "date": today,
    }
    todos[person]["daily"].append(todo_item)
    _save_todos(todos)

    return {"ok": True, "message": f"已添加 {person} Todo: {text}", "todo": todo_item}


def _dispatch_done(person: str, todo_id_str: str):
    """@done 指令处理器：勾选一条 Todo。"""
    if not person or not todo_id_str:
        return {"ok": False, "message": "用法: @done <管理员|伴侣> <id>"}
    try:
        todo_id = int(todo_id_str)
    except ValueError:
        return {"ok": False, "message": "Todo ID 必须是数字"}

    todos = _load_todos()
    if person not in todos:
        return {"ok": False, "message": f"用户 {person} 无 Todo"}

    for category in ["daily", "weekly"]:
        for item in todos[person].get(category, []):
            if item["id"] == todo_id:
                item["done"] = True
                _save_todos(todos)
                return {"ok": True, "message": f"已完成 {person} Todo #{todo_id}: {item['text']}"}

    return {"ok": False, "message": f"未找到 {person} Todo #{todo_id}"}


def _parse_command(text: str) -> dict:
    """解析指令文本，提取前缀、用户、内容。

    Returns:
        {
            "prefix": "@todo" | None,
            "person": "管理员" | "伴侣" | None,
            "text": "买牛奶",
            "matched": True | False,
            "action": "add_todo" | None,
            "api": "/v1/api/daily/todos" | None
        }
    """
    text = text.strip()
    if not text or not text.startswith("@"):
        return {"prefix": None, "person": None, "text": text, "matched": False, "action": None, "api": None}

    # 从注册表加载指令前缀
    registry = _load_card_registry()
    prefixes = registry.get("commandPrefixes", [])

    # 找到第一个匹配的 @前缀
    for pf in sorted(prefixes, key=lambda x: -len(x["prefix"])):  # 长前缀优先
        prefix = pf["prefix"]
        if text.startswith(prefix + " ") or text == prefix:
            remaining = text[len(prefix):].strip()

            # 检查是否包含已知用户名
            person = None
            for p in KNOWN_PERSONS:
                if remaining.startswith(p + " ") or remaining == p:
                    person = p
                    remaining = remaining[len(p):].strip()
                    break

            return {
                "prefix": prefix,
                "person": person,
                "text": remaining,
                "matched": True,
                "action": pf.get("action", ""),
                "api": pf.get("api", ""),
            }

    # @ 开头但未匹配任何前缀 → 不改写，由 caller 决定回退
    return {"prefix": None, "person": None, "text": text, "matched": False, "action": None, "api": None}


# ---- 每日卡片: 卡片级 prompt 系统 ----

# 卡片关键词映射（用于从用户输入中检测目标卡片）
CARD_KEYWORDS = {
    "todo": ["todo", "待办", "任务", "待办事项", "干活", "要做", "列表"],
    "data": ["体重", "喝水", "运动", "记录", "追踪", "打卡", "指标", "数据", "公斤", "kg", "饮水量", "杯水", "步数"],
    "recipe": ["食谱", "菜单", "吃", "午饭", "晚饭", "早餐", "午餐", "晚餐", "饭", "卡路里", "热量", "做饭"],
    "wishes": ["心愿", "愿望", "想法", "想", "计划做", "梦想", "点子"],
    "notes": ["随手记", "笔记", "想法", "灵感", "记录", "心情", "memo", "备忘"],
    "bookmarks": ["收藏", "书签", "链接", "网址", "bookmark", "保存"],
    "photos": ["照片", "图片", "拍照", "相册", "截屏", "截图"],
    "shares": ["分享", "发送给", "发给", "共享", "share"],
    "reminders": ["提醒", "闹钟", "定时", "记得", "别忘了", "通知"],
    "habits": ["习惯", "坚持", "打卡", "签到", "每日", "habit"],
    "news": ["新闻", "资讯", "新闻", "热点", "消息"],
}


def _detect_card_from_text(text):
    """从用户输入中检测涉及哪些卡片。返回 [(card_id, score), ...] 按匹配度排序。"""
    text_lower = text.lower()
    results = {}
    for card_id, keywords in CARD_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in text_lower:
                score += len(kw)  # 长关键词权重更高
        if score > 0:
            results[card_id] = score
    sorted_cards = sorted(results.items(), key=lambda x: x[1], reverse=True)
    return sorted_cards


def _load_card_prompt(card_id):
    """加载卡片的专属 prompt。如果 prompt.json 不存在则创建默认模板。"""
    card_dir = os.path.join(USER_DATA_DIR, card_id)
    prompt_path = os.path.join(card_dir, "prompt.json")

    if not os.path.isfile(prompt_path) or os.path.getsize(prompt_path) == 0:
        _ensure_default_prompt(card_id)

    with open(prompt_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    domain = data.get("domain_knowledge", "")
    practices = data.get("best_practices", [])
    preferences = data.get("user_preferences", [])
    examples = data.get("examples", [])

    parts = [f"## {data.get('card_name', card_id)} 卡片专属经验\n"]

    if domain:
        parts.append(f"**领域知识**：{domain}\n")
    if practices:
        parts.append("**最佳实践**：")
        for p in practices:
            parts.append(f"- {p}")
        parts.append("")
    if preferences:
        parts.append("**用户偏好**：")
        for p in preferences:
            parts.append(f"- {p}")
        parts.append("")

    if examples:
        parts.append("**示例**：")
        for ex in examples:
            parts.append(f"- 输入：「{ex['in']}」→ 操作：{ex['out']}")
        parts.append("")

    return "\n".join(parts)


_CARD_PROMPT_DEFAULTS = {
    "todo": {
        "card_name": "Todo 待办",
        "domain_knowledge": "管理员习惯把大事拆成小任务，一个 Todo 描述一件事。工作类任务优先级最高。",
        "best_practices": [
            "id 用最大 id + 1，不要重复",
            "type 默认 'daily'，重要不紧急的事用 'work'",
            "同一件事不要拆成过多子任务（不超过 5 个）",
            "完成任务标记 done=true，不要删除"
        ],
        "user_preferences": [
            "优先级：工作 > 生活 > 娱乐",
            "每天新增不超过 10 条（避免积压）"
        ],
        "examples": [
            {"in": "今天要做三件事：写报告、开会、买菜", "out": "添加 3 条 Todo，id 递增，type=daily，done=false"},
            {"in": "明天要把 Phase 12 剩下的 3 个 TODO 做完", "out": "添加 1 条 Todo（概括为'完成 Phase 12 剩余 TODO'），type=work"}
        ]
    },
    "data": {
        "card_name": "数据追踪",
        "domain_knowledge": "管理员关注体重(kg)、饮水量(杯)、运动时长(分钟)三项核心指标。每天记录一次，多次记录时保留最后一次。",
        "best_practices": [
            "体重精确到 0.1kg（如 72.5），每天固定时间（早晨空腹）记录最准",
            "饮水量按杯计（1 杯 ≈ 250ml），日目标 8 杯",
            "运动时长用中文描述（如'跑步30min'、'游泳45min'），方便展示",
            "新增字段先在 data.json 的各人物文件中加顶层 key，再写当日值"
        ],
        "user_preferences": [
            "目标体重：68kg",
            "日饮水目标：8 杯（约 2L）",
            "日运动目标：30 分钟",
            "连续 3 天饮水不足需提醒"
        ],
        "examples": [
            {"in": "今天体重 72", "out": "读 管理员.json → 在 weight 字段加 {\"2026-05-28\": 72} → 写回 → curl apply_rules data"},
            {"in": "今天喝了 6 杯水", "out": "读 管理员.json → 在 water 字段加 {\"2026-05-28\": 6} → 写回 → curl apply_rules data"}
        ]
    },
    "recipe": {
        "card_name": "食谱",
        "domain_knowledge": "一周七天映射（周一~周日），每天有午餐(lunch)和晚餐(dinner)。每道菜记录名称和估算热量。",
        "best_practices": [
            "热量按道菜估算而非精确计算（快餐 600-800kcal，家常菜 300-500kcal）",
            "单日午餐+晚餐总量控制在 1000-1400kcal 为宜",
            "如果只设了午餐没设晚餐，不要自动补齐"
        ],
        "user_preferences": [
            "午餐偏好轻食（沙拉、三明治、便当）",
            "晚餐可以丰盛些",
            "周末可能不下厨（外卖/外食）"
        ],
        "examples": [
            {"in": "今天午饭吃沙拉", "out": "找到今天对应的星期，在 lunch 下写 {\"name\":\"沙拉\",\"calories\":250}"},
            {"in": "周三晚饭牛排 600kcal", "out": "在\"周三\"的 dinner 下写 {\"name\":\"牛排\",\"calories\":600}"}
        ]
    },
    "wishes": {
        "card_name": "心愿",
        "domain_knowledge": "心愿按成熟度分阶段：idea（想法阶段）→ discussing（讨论中）→ designing（设计）→ implementing（实施）→ done（完成）。管理员很少直接删除心愿，更多是归档。",
        "best_practices": [
            "新心愿默认 status='idea'，描述写清想要什么",
            "推进到下一阶段时更新 status 字段，不要新建一条",
            "心愿 id 格式 w + 数字（w1, w2...），新建时取最大 id + 1",
            "可以加 tags 分类（如 ['tech', 'home', 'travel']）"
        ],
        "user_preferences": [
            "偏好一次添加 1 个心愿（不批量添加）",
            "心愿没有截止日期，不设 deadline"
        ],
        "examples": [
            {"in": "我想做一个拍饭分析的小工具", "out": "创建新心愿 {\"id\":\"w1\",\"title\":\"拍饭分析小工具\",\"status\":\"idea\",\"tags\":[\"tech\"],\"createdBy\":\"管理员\"}"},
            {"in": "把 w3 推进到设计阶段", "out": "读 wishes/data.json → 找到 id=w3 → 改 status='designing' → 写回"}
        ]
    },
    "notes": {
        "card_name": "随手记",
        "domain_knowledge": "随手记录想法、灵感、心情。短则一句话，长可带图片。用 mood 表情标记心情。",
        "best_practices": [
            "id 格式 n + 数字，自增",
            "mood 用单个 emoji（💡/😊/😢/🤔/🔥/📝）",
            "tags 用数组，方便后续筛选",
            "images 存 /user-files/ 下的路径"
        ],
        "user_preferences": [
            "默认 mood: 💡",
            "不自动给 notes 加标签（让用户自然语言说明时再加）"
        ],
        "examples": [
            {"in": "记一下：今天发现一个好用的工具叫 foo", "out": "创建笔记 id=nX, text='今天发现一个好用的工具叫 foo', mood='💡'"},
            {"in": "心情不好，今天不想说话", "out": "创建笔记 mood='😢', text='心情不好，今天不想说话'"}
        ]
    },
    "bookmarks": {
        "card_name": "收藏",
        "domain_knowledge": "收藏网页链接、文章。记录 URL、标题、标签。",
        "best_practices": [
            "id 格式 b + 数字，自增",
            "url 必须是完整 URL（https:// 开头）",
            "用 tags 分类（如 ['技术','前端','工具']）"
        ],
        "user_preferences": [
            "管理员可能一次收藏多个链接"
        ],
        "examples": [
            {"in": "收藏这个链接 https://example.com 技术", "out": "创建收藏 id=bX, url='https://example.com', title='example', tags=['技术']"}
        ]
    },
    "photos": {
        "card_name": "照片",
        "domain_knowledge": "照片墙。图片存在 /user-files/ 下，这里只存元数据和路径。",
        "best_practices": [
            "id 格式 p + 数字，自增",
            "image 字段存 /user-files/ 下的相对路径",
            "caption 简洁（不超过 50 字）"
        ],
        "user_preferences": [],
        "examples": []
    },
    "shares": {
        "card_name": "分享",
        "domain_knowledge": "记录两个人之间互相分享的链接、笔记、照片等。sent 是发出去的，received 是收到的。",
        "best_practices": [
            "type 指分享类型：link/note/photo/file",
            "received 里的条目默认 read=false，读了要改"
        ],
        "user_preferences": [
            "管理员通常向「伴侣」分享"
        ],
        "examples": [
            {"in": "把这个发给伴侣", "out": "在 sent 数组添加新条目，from=管理员，to=伴侣"}
        ]
    },
    "reminders": {
        "card_name": "提醒",
        "domain_knowledge": "定时提醒。支持单次和重复（daily/weekly）。时间用 HH:MM 格式。",
        "best_practices": [
            "id 格式 r + 数字，自增",
            "time 用 HH:MM（24 小时制）",
            "repeat 为 null（单次）、'daily' 或 'weekly'",
            "过了时间的提醒不要自动删除，标记 done=true 就行"
        ],
        "user_preferences": [
            "默认提醒时间不要乱设（不要设凌晨），用户会指定时间"
        ],
        "examples": [
            {"in": "下午3点提醒我开会", "out": "创建提醒 time='15:00', date=今天, repeat=null, done=false"},
            {"in": "每天晚上9点提醒我喝水", "out": "创建提醒 time='21:00', repeat='daily'"}
        ]
    },
    "habits": {
        "card_name": "习惯",
        "domain_knowledge": "每日打卡习惯。habits 定义习惯列表，logs 记录每日完成情况。",
        "best_practices": [
            "id 格式 h + 数字，自增",
            "icon 用单个 emoji",
            "target 通常为 'daily'",
            "logs 格式 {\"h1\": {\"2026-05-28\": true}}"
        ],
        "user_preferences": [],
        "examples": [
            {"in": "加一个习惯：每天运动", "out": "在 habits 数组加 {\"id\":\"hX\",\"name\":\"运动\",\"icon\":\"🏃\",\"target\":\"daily\"}"},
            {"in": "今天运动了，打卡", "out": "在 logs 里设 logs['hX']['2026-05-28'] = true"}
        ]
    },
    "news": {
        "card_name": "新闻",
        "domain_knowledge": "每日自动爬取的新闻资讯。每天一个文件 YYYY-MM-DD.json，按分类组织。通常不需要手动修改。",
        "best_practices": [
            "新闻卡片是只读的（爬虫自动更新），一般不要手动改"
        ],
        "user_preferences": [],
        "examples": []
    }
}


def _ensure_default_prompt(card_id):
    """为卡片创建默认 prompt.json。"""
    card_dir = os.path.join(USER_DATA_DIR, card_id)
    prompt_path = os.path.join(card_dir, "prompt.json")
    os.makedirs(card_dir, exist_ok=True)

    default = _CARD_PROMPT_DEFAULTS.get(card_id, {
        "card_name": card_id,
        "domain_knowledge": "",
        "best_practices": [],
        "user_preferences": [],
        "examples": []
    })

    with open(prompt_path, "w", encoding="utf-8") as f:
        json.dump(default, f, ensure_ascii=False, indent=2)

    logger.info(f"已创建默认 prompt.json: {card_id}")
    return default


def _build_card_specific_messages(text):
    """检测文本涉及的卡片，返回额外的 system 消息（卡片专属 prompt）。"""
    detected = _detect_card_from_text(text)

    extra_messages = []
    added = set()
    for card_id, score in detected:
        if card_id in added:
            continue
        if score < 3:  # 太短的关键词忽略（如单字"吃"）
            continue
        card_prompt = _load_card_prompt(card_id)
        if card_prompt:
            extra_messages.append({"role": "system", "content": card_prompt})
            added.add(card_id)
            logger.info(f"注入卡片专属 prompt: {card_id} (score={score})")

    return extra_messages


# ---- API: 管理卡片 prompt ----

@app.route("/v1/api/daily/prompt/<card_id>", methods=["GET"])
@require_token
def get_card_prompt(card_id):
    """GET /v1/api/daily/prompt/todo — 读取卡片的专属 prompt。"""
    card_dir = os.path.join(USER_DATA_DIR, card_id)
    prompt_path = os.path.join(card_dir, "prompt.json")

    if not os.path.isfile(prompt_path):
        _ensure_default_prompt(card_id)

    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_data = json.load(f)

    return jsonify({"ok": True, "card_id": card_id, "prompt": prompt_data})


@app.route("/v1/api/daily/prompt/<card_id>", methods=["PUT"])
@require_token
def update_card_prompt(card_id):
    """PUT /v1/api/daily/prompt/todo — 更新卡片的专属 prompt。"""
    body = request.get_json(silent=True)
    if not body:
        return error_response("缺少请求体", 400)

    card_dir = os.path.join(USER_DATA_DIR, card_id)
    prompt_path = os.path.join(card_dir, "prompt.json")

    # 读取旧数据（可选合并）
    old = {}
    if os.path.isfile(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            try:
                old = json.load(f)
            except json.JSONDecodeError:
                pass

    # 合并：对新字段覆盖，老字段保留
    old.update(body)

    os.makedirs(card_dir, exist_ok=True)
    with open(prompt_path, "w", encoding="utf-8") as f:
        json.dump(old, f, ensure_ascii=False, indent=2)

    logger.info(f"卡片 prompt 已更新: {card_id}")
    return jsonify({"ok": True, "card_id": card_id, "prompt": old})

@app.route("/v1/api/daily/command", methods=["POST"])
@require_token
def daily_command():
    """POST /v1/api/daily/command - 统一指令中枢。

    请求体: {"text": "@todo 管理员 买牛奶"} 或 {"text": "今天天气怎么样"}

    流程:
      1. 解析 @前缀，匹配卡片注册表中的 commandPrefixes
      2. 匹配成功 → 分发到对应处理器
      3. 无匹配 → 回退为自然语言，调用 Gateway 处理

    返回:
      - 指令匹配: {"ok": true, "prefix": "@todo", "action": "add_todo", ...}
      - 自然语言: {"ok": true, "type": "chat", "content": "AI 回复..."}
    """
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return error_response("缺少必填参数", 400, "请求体需包含 text 字段")

    text = data["text"]
    if not isinstance(text, str) or not text.strip():
        return error_response("指令内容不能为空", 400)

    # 解析指令
    parsed = _parse_command(text)

    # 匹配到前缀 → 分发
    if parsed["matched"]:
        prefix = parsed["prefix"]
        person = parsed["person"]
        content = parsed["text"]

        logger.info(f"指令解析: prefix={prefix}, person={person}, text={content}")

        # @todo - 添加 Todo
        if prefix == "@todo":
            result = _dispatch_add_todo(person, content)
            result["prefix"] = prefix
            result["action"] = parsed["action"]
            return jsonify(result)

        # @done - 勾选 Todo
        if prefix == "@done":
            result = _dispatch_done(person, content)
            result["prefix"] = prefix
            result["action"] = parsed["action"]
            return jsonify(result)

        # 其他指令 - 返回解析结果（处理器在后续 Phase 实现）
        return jsonify({
            "ok": True,
            "prefix": prefix,
            "action": parsed["action"],
            "parsed": {"person": person, "text": content},
            "message": f"指令 {prefix} 已解析，处理器将在后续 Phase 实现",
        })

    # 未匹配前缀 → 回退自然语言：创建带卡片 prompt 的特殊会话
    logger.info(f"指令中枢 → 自然语言回退，创建 Daily 会话: {text[:80]}")
    try:
        import uuid, datetime

        # 创建新会话
        now = datetime.datetime.now()
        session_id = f"sess_daily_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        session_file = os.path.join(SESSION_DIR, f"{session_id}.json")

        # 构建会话：基础卡片 prompt + 卡片专属经验
        base_prompt = _build_card_prompt()
        card_messages = _build_card_specific_messages(text)

        session_data = {
            "id": session_id,
            "title": f"Daily 指令 {now.strftime('%m月%d日 %H:%M')}",
            "created": now.isoformat(),
            "updated": now.isoformat(),
            "messages": [
                {"role": "system", "content": base_prompt},
                *card_messages,
                {"role": "user", "content": text}
            ],
            "tags": ["daily"]
        }

        # 保存会话文件
        os.makedirs(SESSION_DIR, exist_ok=True)
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Daily 会话已创建: {session_id}")

        # 调用 Gateway 获取 AI 回复（基础 prompt + 卡片专属经验）
        messages = _build_gateway_messages(
            [{"role": "system", "content": base_prompt}] + card_messages,
            text,
            None,
        )
        assistant_msg = _call_gateway(messages)

        # 将 AI 回复追加到会话
        session_data["messages"].append({
            "role": "assistant",
            "content": assistant_msg.get("content", "")
        })
        session_data["updated"] = datetime.datetime.now().isoformat()
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)

        return jsonify({
            "ok": True,
            "type": "chat",
            "prefix": None,
            "session_id": session_id,
            "content": assistant_msg.get("content", ""),
            "time": assistant_msg.get("time", ""),
        })
    except RuntimeError as e:
        return error_response(f"指令处理失败: {e}", 502)


# ---- 每日 Dashboard: 面板配置 API (DB4) ----

DASHBOARD_CONFIG_PATH = os.path.join(USER_DATA_DIR, "dashboard-config.json")

DEFAULT_DASHBOARD_CONFIG = {
    "layout": {
        "columns": 3,
        "order": ["news", "todo", "data", "recipe", "wishes", "notes", "bookmarks", "photos", "shares", "reminders", "habits"],
        "gap": 16,
    },
    "disabledCards": [],
    "cardSettings": {},
}


def _load_dashboard_config():
    """读取面板配置，不存在或错误时返回默认值。"""
    try:
        if os.path.isfile(DASHBOARD_CONFIG_PATH) and os.path.getsize(DASHBOARD_CONFIG_PATH) > 0:
            with open(DASHBOARD_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"dashboard-config.json 读取失败: {e}")
    return DEFAULT_DASHBOARD_CONFIG.copy()


def _save_dashboard_config(data: dict):
    """写入面板配置。"""
    os.makedirs(os.path.dirname(DASHBOARD_CONFIG_PATH), exist_ok=True)
    with open(DASHBOARD_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("dashboard-config.json 已保存")


@app.route("/v1/api/daily/config", methods=["GET"])
@require_token
def get_dashboard_config():
    """GET /v1/api/daily/config - 读取面板完整配置。

    合并卡片注册表与用户布局配置，返回：
      - cards: 注册表中所有卡片（含 enabled/disabled 状态）
      - layout: 用户布局偏好
      - cardSettings: 各卡片自定义设置

    若文件不存在则返回默认配置。
    """
    registry = _load_card_registry()
    config = _load_dashboard_config()

    # 合并 enabled 状态到每张卡片
    cards_with_status = []
    for card in registry.get("cards", []):
        card_info = dict(card)
        card_info["enabled"] = card["id"] not in config.get("disabledCards", [])
        # 合并卡片级设置
        card_settings = config.get("cardSettings", {}).get(card["id"], {})
        card_info["settings"] = card_settings
        cards_with_status.append(card_info)

    return jsonify({
        "cards": cards_with_status,
        "layout": config.get("layout", {}),
        "commandPrefixes": registry.get("commandPrefixes", []),
    })


@app.route("/v1/api/daily/config", methods=["PUT"])
@require_token
def put_dashboard_config():
    """PUT /v1/api/daily/config - 更新面板配置。

    请求体：部分或完整配置（layout、disabledCards、cardSettings）。
    支持增量更新：只传 layout 则只改布局。
    """
    body = request.get_json(silent=True)
    if not body:
        return error_response("请求体必须是有效 JSON", 400)

    current = _load_dashboard_config()

    # 合并 layout（增量更新）
    if "layout" in body:
        current["layout"] = {**current["layout"], **body["layout"]}

    # 替换 disabledCards
    if "disabledCards" in body:
        current["disabledCards"] = body["disabledCards"]

    # 合并 cardSettings
    if "cardSettings" in body:
        current["cardSettings"] = {
            **current.get("cardSettings", {}),
            **body["cardSettings"],
        }

    try:
        _save_dashboard_config(current)
        return jsonify({"ok": True, "message": "面板配置已更新"})
    except IOError as e:
        return error_response(f"保存失败: {e}", 500)


@app.route("/v1/api/daily/config/cards/<card_id>", methods=["PUT"])
@require_token
def put_card_config(card_id):
    """PUT /v1/api/daily/config/cards/{id} - 启用/禁用/设置单张卡片。

    请求体:
      {"enabled": true/false}  - 启用或禁用
      {"settings": {"width": "large"}}  - 更新卡片设置
      {"order": 0}  - 调整排序位置

    卡片必须存在于注册表中。
    """
    registry = _load_card_registry()
    card_exists = any(c["id"] == card_id for c in registry.get("cards", []))
    if not card_exists:
        return error_response(f"卡片 '{card_id}' 不存在", 404)

    body = request.get_json(silent=True)
    if not body:
        return error_response("请求体必须是有效 JSON", 400)

    config = _load_dashboard_config()
    changes = []

    # 启用/禁用
    if "enabled" in body:
        disabled = config.get("disabledCards", [])
        if body["enabled"]:
            if card_id in disabled:
                disabled.remove(card_id)
                changes.append(f"已启用")
        else:
            if card_id not in disabled:
                disabled.append(card_id)
                changes.append(f"已禁用")
        config["disabledCards"] = disabled

    # 排序调整
    if "order" is not None and "order" in body:
        order = body["order"]
        current_order = config.get("layout", {}).get("order", [])
        if card_id in current_order:
            current_order.remove(card_id)
        current_order.insert(max(0, min(order, len(current_order))), card_id)
        config.setdefault("layout", {})["order"] = current_order
        changes.append(f"顺序调整到 #{order}")

    # 卡片设置
    if "settings" in body:
        settings = config.get("cardSettings", {})
        settings[card_id] = {**settings.get(card_id, {}), **body["settings"]}
        config["cardSettings"] = settings
        changes.append("设置已更新")

    if not changes:
        return error_response("没有可更新的字段", 400, "支持的字段: enabled, order, settings")

    try:
        _save_dashboard_config(config)
        return jsonify({"ok": True, "card_id": card_id, "changes": changes})
    except IOError as e:
        return error_response(f"保存失败: {e}", 500)


# ============================================================
#  新闻 API (DB5)
# ============================================================

NEWS_DIR = os.path.join(USER_DATA_DIR, "news")
DEFAULT_SOURCES_PATH = os.path.join(NEWS_DIR, "sources.json")

DEFAULT_NEWS_SOURCES = [
    {"name": "36氪", "url": "https://36kr.com", "type": "rss", "enabled": True, "category": "科技"},
    {"name": "知乎日报", "url": "https://daily.zhihu.com", "type": "rss", "enabled": True, "category": "综合"},
    {"name": "财新网", "url": "https://www.caixin.com", "type": "rss", "enabled": True, "category": "财经"},
    {"name": "豆瓣电影", "url": "https://movie.douban.com", "type": "rss", "enabled": True, "category": "娱乐"},
]


def _load_news_sources() -> list:
    """读取新闻源配置，不存在时使用默认值。"""
    try:
        if os.path.isfile(DEFAULT_SOURCES_PATH) and os.path.getsize(DEFAULT_SOURCES_PATH) > 0:
            with open(DEFAULT_SOURCES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"news/sources.json 读取失败: {e}")
    return DEFAULT_NEWS_SOURCES[:]


def _today_news_path(tz: str = "Asia/Shanghai") -> str:
    """返回今日新闻缓存文件路径。"""
    today = datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d")
    return os.path.join(NEWS_DIR, f"{today}.json")


def _load_today_news_cache() -> dict:
    """读取今日新闻缓存，不存在或损坏时返回空结构。"""
    path = _today_news_path()
    try:
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"新闻缓存读取失败: {e}")
    return {
        "date": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d"),
        "updated": None,
        "categories": {},
        "total": 0,
    }


@app.route("/v1/api/daily/news", methods=["GET"])
@require_token
def get_news():
    """GET /v1/api/daily/news - 读取今日新闻。

    可选查询参数:
      - category: 按分类过滤（如 ?category=科技）
      - limit:   最大返回条数（如 ?limit=5）

    返回:
      { "date": "2026-05-27", "total": 12, "categories": { ... } }
    """
    cache = _load_today_news_cache()
    category_filter = request.args.get("category", "").strip()
    limit_str = request.args.get("limit", "")
    limit = int(limit_str) if limit_str.isdigit() else None

    if category_filter and category_filter in cache.get("categories", {}):
        items = cache["categories"][category_filter][:limit] if limit else cache["categories"][category_filter]
        return jsonify({
            "ok": True,
            "date": cache["date"],
            "category": category_filter,
            "items": items,
            "total": len(items),
        })

    categories = cache.get("categories", {})
    total = cache.get("total", sum(len(v) for v in categories.values()))

    return jsonify({
        "ok": True,
        "date": cache.get("date"),
        "updated": cache.get("updated"),
        "categories": categories,
        "total": total,
    })


@app.route("/v1/api/daily/news/refresh", methods=["POST"])
@require_token
def refresh_news():
    """POST /v1/api/daily/news/refresh - 触发新闻爬虫刷新。

    执行 scripts/news_crawler.py 抓取最新新闻并写入缓存。
    返回 {"ok": true, "count": 新增条数, "sources": 抓取的源数}

    若爬虫脚本不存在则返回提示。
    """
    crawler_path = os.path.join(os.path.dirname(__file__), "scripts", "news_crawler.py")

    if not os.path.isfile(crawler_path):
        return jsonify({
            "ok": True,
            "count": 0,
            "sources": 0,
            "message": "新闻爬虫脚本尚未就绪，将在 Phase 6b (DB8) 实现",
        })

    try:
        result = subprocess.run(
            ["python3", crawler_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            logger.error(f"新闻爬虫执行失败: {result.stderr[:200]}")
            return jsonify({
                "ok": False,
                "error": "新闻抓取失败",
                "detail": result.stderr[:200],
            }), 500

        # 尝试解析爬虫输出 JSON
        try:
            output = json.loads(result.stdout.strip().split("\n")[-1])
            return jsonify({
                "ok": True,
                "count": output.get("count", 0),
                "sources": output.get("sources", 0),
                "date": output.get("date"),
            })
        except (json.JSONDecodeError, IndexError):
            return jsonify({
                "ok": True,
                "count": 0,
                "sources": 0,
                "message": "爬虫已执行，但输出格式异常",
            })

    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "新闻抓取超时"}), 500
    except Exception as e:
        logger.error(f"新闻爬虫异常: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


def _save_news_sources(sources: list) -> None:
    """将新闻源列表持久化到 sources.json。"""
    os.makedirs(NEWS_DIR, exist_ok=True)
    with open(DEFAULT_SOURCES_PATH, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)


@app.route("/v1/api/daily/news/sources", methods=["GET", "PUT"])
@require_token
def news_sources():
    """GET/PUT /v1/api/daily/news/sources - 新闻源管理。

    GET    → 返回所有新闻源列表
    PUT    → 批量更新新闻源（替换全部）
             请求体: [{"name":"36氪","url":"...","enabled":true,"category":"科技"}, ...]

    返回: {"ok": true, "sources": [...]}
    """
    if request.method == "GET":
        sources = _load_news_sources()
        enabled_count = sum(1 for s in sources if s.get("enabled", True))
        return jsonify({
            "ok": True,
            "sources": sources,
            "total": len(sources),
            "enabled_count": enabled_count,
        })

    if request.method == "PUT":
        data = request.get_json(silent=True)
        if not isinstance(data, list):
            return error_response("请求体必须是新闻源数组", 400)

        # 基本校验
        cleaned = []
        seen_names = set()
        for i, src in enumerate(data):
            if not isinstance(src, dict) or "name" not in src:
                return error_response(f"第 {i+1} 项缺少必填字段 name", 400)
            name = src["name"].strip()
            if not name:
                return error_response(f"第 {i+1} 项名称为空", 400)
            if name in seen_names:
                return error_response(f"新闻源 {name} 重复", 400)
            seen_names.add(name)
            cleaned.append({
                "name": name,
                "url": src.get("url", "").strip(),
                "type": src.get("type", "rss"),
                "enabled": src.get("enabled", True),
                "category": src.get("category", "综合").strip() or "综合",
            })

        try:
            _save_news_sources(cleaned)
            return jsonify({
                "ok": True,
                "sources": cleaned,
                "total": len(cleaned),
                "enabled_count": sum(1 for s in cleaned if s["enabled"]),
                "message": f"已更新 {len(cleaned)} 个新闻源",
            })
        except IOError as e:
            return error_response(f"保存新闻源失败: {e}", 500)


# ============================================================
#  Todo CRUD API (DB9)
# ============================================================

VALID_TODO_TYPES = {"daily", "weekly"}


@app.route("/v1/api/daily/todos", methods=["GET", "POST"])
@require_token
def todos_list():
    """GET/POST /v1/api/daily/todos - Todo 列表和创建。

    GET 查询参数:
      - person: 按人员过滤（管理员/伴侣）
      - type:   按类型过滤（daily/weekly）
      - done:   按状态过滤（true/false/any）

    POST 请求体:
      {"person":"管理员", "text":"买牛奶", "type":"daily"}

    返回:
      GET  → {"ok":true, "todos": {...}, "total": N}
      POST → {"ok":true, "todo": {...}, "message": "已添加"}
    """
    if request.method == "GET":
        todos = _load_todos()
        person = _get_person()
        todo_type = request.args.get("type", "").strip()
        done_filter = request.args.get("done", "any").strip()

        # 按人员过滤
        if person:
            if person in todos:
                filtered = {person: todos[person]}
            else:
                filtered = {}
        else:
            filtered = todos

        # 按类型/状态过滤
        if todo_type or done_filter != "any":
            result = {}
            for p, cats in filtered.items():
                result[p] = {}
                for cat, items in cats.items():
                    if todo_type and cat != todo_type:
                        continue
                    if done_filter in ("true", "false"):
                        want_done = (done_filter == "true")
                        items = [i for i in items if i.get("done", False) == want_done]
                    result[p][cat] = items
            filtered = result

        total = sum(len(v) for cats in filtered.values() for v in cats.values())
        return jsonify({"ok": True, "todos": filtered, "total": total})

    if request.method == "POST":
        data = request.get_json(silent=True)
        if not data or "text" not in data:
            return error_response("缺少必填字段 text", 400)
        text = data["text"].strip()
        if len(text) < 2:
            return error_response("内容至少 2 个字符", 400)

        person = data.get("person", "").strip() or _get_person() or _get_person()
        if person not in KNOWN_PERSONS:
            return error_response(f"未知用户: {person}", 400)

        todo_type = data.get("type", "daily").strip()
        if todo_type not in VALID_TODO_TYPES:
            return error_response(f"无效类型: {todo_type}", 400)

        todos = _load_todos()
        todos.setdefault(person, {}).setdefault(todo_type, [])

        tz = ZoneInfo("Asia/Shanghai")
        today = datetime.now(tz).strftime("%Y-%m-%d")
        new_id = 1
        for item in todos[person].get(todo_type, []):
            if item.get("id", 0) >= new_id:
                new_id = item["id"] + 1

        todo_item = {"id": new_id, "text": text, "done": False, "type": todo_type, "date": today}
        todos[person][todo_type].append(todo_item)
        _save_todos(todos)

        return jsonify({"ok": True, "todo": todo_item, "message": f"已添加 Todo: {text}"})


@app.route("/v1/api/daily/todos/<int:todo_id>", methods=["PUT", "DELETE"])
@require_token
def todos_item(todo_id):
    """PUT/DELETE /v1/api/daily/todos/{id} - 更新/删除单个 Todo。

    PUT  请求体: {"person":"管理员", "done":true}  或 {"text":"新内容"}
    DELETE 无请求体，需 ?person= 参数。

    返回:
      PUT    → {"ok":true, "todo": {...}}
      DELETE → {"ok":true, "message": "已删除"}
    """
    todos = _load_todos()

    # 查找 Todo
    found = None
    found_person = None
    found_cat = None
    for p, cats in todos.items():
        for cat, items in cats.items():
            for item in items:
                if item.get("id") == todo_id:
                    found = item
                    found_person = p
                    found_cat = cat
                    break
            if found:
                break
        if found:
            break

    if not found:
        return error_response(f"Todo #{todo_id} 不存在", 404)

    if request.method == "DELETE":
        todos[found_person][found_cat] = [i for i in todos[found_person][found_cat] if i["id"] != todo_id]
        _save_todos(todos)
        return jsonify({"ok": True, "message": f"已删除 Todo #{todo_id}"})

    if request.method == "PUT":
        data = request.get_json(silent=True)
        if not data:
            return error_response("请求体不能为空", 400)

        changed = False

        if "done" in data:
            found["done"] = bool(data["done"])
            changed = True

        if "text" in data:
            new_text = data["text"].strip()
            if len(new_text) < 2:
                return error_response("内容至少 2 个字符", 400)
            found["text"] = new_text
            changed = True

        if "type" in data:
            new_type = data["type"].strip()
            if new_type not in VALID_TODO_TYPES:
                return error_response(f"无效类型: {new_type}", 400)
            if new_type != found_cat:
                # 移动到另一个分类
                todos[found_person][found_cat] = [i for i in todos[found_person][found_cat] if i["id"] != todo_id]
                found["type"] = new_type
                todos[found_person].setdefault(new_type, []).append(found)
            changed = True

        if not changed:
            return jsonify({"ok": True, "todo": found, "message": "无变更"})

        _save_todos(todos)
        _notify_partner(person if request.user else person or request.user, {"event": "todo_changed", "by": person})
        return jsonify({"ok": True, "todo": found, "message": f"已更新 Todo #{todo_id}"})


@app.route("/v1/api/daily/todos/summary", methods=["GET"])
@require_token
def todos_summary():
    """GET /v1/api/daily/todos/summary - 双人 Todo 统计摘要。

    返回各人员的每日/每周待办数。用于面板卡片摘要显示。

    返回:
      {"ok":true, "persons":
        {"管理员": {"daily": {"total":3,"done":1,"pending":2}, "weekly": {...}},
         "伴侣":   {...}}}
    """
    todos = _load_todos()
    persons = {}

    for person in KNOWN_PERSONS:
        data = todos.get(person, {})
        persons[person] = {}
        for cat in ("daily", "weekly"):
            items = data.get(cat, [])
            total = len(items)
            done = sum(1 for i in items if i.get("done"))
            persons[person][cat] = {
                "total": total,
                "done": done,
                "pending": total - done,
            }

    # 全局统计
    all_total = sum(p[cat]["total"] for p in persons.values() for cat in ("daily", "weekly"))
    all_done = sum(p[cat]["done"] for p in persons.values() for cat in ("daily", "weekly"))

    return jsonify({
        "ok": True,
        "persons": persons,
        "total": all_total,
        "done": all_done,
        "pending": all_total - all_done,
    })


@app.route("/v1/api/daily/todos/person/<person>", methods=["GET"])
@require_token
def todos_by_person(person):
    """GET /v1/api/daily/todos/person/<person> - 按人员查询 Todo。

    支持路径参数指定人员，方便前端直接请求某人 Todo。

    查询参数:
      - type: daily|weekly（可选）
      - done: true|false|any（可选）

    返回:
      {"ok":true, "person":"管理员", "todos": {...}, "total": N}
    """
    if person not in KNOWN_PERSONS:
        return error_response(f"未知用户: {person}，可用: {KNOWN_PERSONS}", 400)

    todos = _load_todos()
    data = todos.get(person, {})
    todo_type = request.args.get("type", "").strip()
    done_filter = request.args.get("done", "any").strip()

    result = {}
    for cat, items in data.items():
        if todo_type and cat != todo_type:
            continue
        if done_filter in ("true", "false"):
            want_done = (done_filter == "true")
            items = [i for i in items if i.get("done", False) == want_done]
        result[cat] = items

    total = sum(len(v) for v in result.values())
    return jsonify({
        "ok": True,
        "person": person,
        "todos": result,
        "total": total,
    })


def _current_week_key(tz="Asia/Shanghai") -> str:
    """返回当前 ISO 周标识（YYYY-Www）。"""
    now = datetime.now(ZoneInfo(tz))
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _is_in_week(date_str: str, week_key: str) -> bool:
    """判断日期字符串是否属于指定 ISO 周。"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}" == week_key
    except ValueError:
        return False


@app.route("/v1/api/daily/todos/week", methods=["GET"])
@require_token
def todos_weekly_view():
    """GET /v1/api/daily/todos/week - 本周 Todo 视图。

    将 daily 和 weekly 两类 Todo 合并展示，便于面板周视图使用。

    查询参数:
      - week:   指定周（YYYY-Www，默认当前周）
      - person: 按人员过滤
      - done:   true|false|any

    返回:
      {"ok":true, "week":"2026-W22", "daily": [...], "weekly": [...], "total": N}
    """
    week = request.args.get("week", "").strip()
    if not week:
        week = _current_week_key()

    person = _get_person()
    done_filter = request.args.get("done", "any").strip()

    todos = _load_todos()
    daily_items = []
    weekly_items = []

    persons_to_check: list[str] = [person] if person else list(todos.keys())

    for p in persons_to_check:
        if p not in todos:
            continue

        # Daily: 按日期匹配
        for item in todos[p].get("daily", []):
            if _is_in_week(item.get("date", ""), week):
                daily_items.append({**item, "person": p})

        # Weekly: 全部显示（weekly todos 属于整周的）
        for item in todos[p].get("weekly", []):
            weekly_items.append({**item, "person": p})

    if done_filter in ("true", "false"):
        want_done = (done_filter == "true")
        daily_items = [i for i in daily_items if i.get("done", False) == want_done]
        weekly_items = [i for i in weekly_items if i.get("done", False) == want_done]

    total = len(daily_items) + len(weekly_items)
    return jsonify({
        "ok": True,
        "week": week,
        "daily": daily_items,
        "weekly": weekly_items,
        "total": total,
    })


# ============================================================
#  个人数据 API (DB12)
# ============================================================

PROFILES_DIR = os.path.join(USER_DATA_DIR, "data")
DATA_FIELDS = {"weight", "exercise", "water", "sleep", "journal", "fitness", "finance", "meal"}

DEFAULT_PERSON_DATA = {
    "weight": [],
    "exercise": [],
    "water": [],
    "sleep": [],
    "journal": [],
}


def _profile_path(person: str) -> str:
    """返回个人数据文件路径。"""
    safe_name = person.replace("/", "_").replace("\\", "_")
    return os.path.join(PROFILES_DIR, f"{safe_name}.json")


def _load_person_data(person: str) -> dict:
    """读取个人数据文件。"""
    path = _profile_path(person)
    try:
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"{person} 数据读取失败: {e}")
    # 初始化空数据
    return dict(DEFAULT_PERSON_DATA)


def _save_person_data(person: str, data: dict):
    """保存个人数据文件。"""
    os.makedirs(PROFILES_DIR, exist_ok=True)
    path = _profile_path(person)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/v1/api/daily/data/<person>", methods=["GET", "POST"])
@require_token
def get_person_data(person):
    """GET /v1/api/daily/data/{person} - 读取个人数据。

    查询参数:
      - fields: 逗号分隔的字段名，如 ?fields=weight,water
      - days:   最近 N 天（默认 30）
      - date:   指定日期 YYYY-MM-DD

    返回:
      {"ok":true, "person":"管理员", "data": {"weight": [...], ...}}
    """
    if person not in KNOWN_PERSONS:
        return error_response(f"未知用户: {person}", 400)

    data = _load_person_data(person)
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)

    # ===== GET =====
    if request.method == "GET":
        fields_str = request.args.get("fields", "").strip()
        days_str = request.args.get("days", "")
        date_str = request.args.get("date", "").strip()

        # 选择字段
        if fields_str:
            fields = [f.strip() for f in fields_str.split(",") if f.strip()]
            invalid = set(fields) - set(data.keys())
            if invalid:
                return error_response(f"无效字段: {', '.join(invalid)}, 可用: {', '.join(sorted(data.keys()))}", 400)
            filtered = {k: data.get(k, []) for k in fields}
        else:
            filtered = dict(data)

        # 按日期过滤（date 优先于 days）
        if date_str:
            for k in filtered:
                filtered[k] = [r for r in filtered[k] if r.get("date") == date_str]
        elif days_str and days_str.isdigit():
            cutoff = (now - timedelta(days=int(days_str))).strftime("%Y-%m-%d")
            for k in filtered:
                filtered[k] = [r for r in filtered[k] if r.get("date", "") >= cutoff]

        total_records = sum(len(v) for v in filtered.values())
        return jsonify({
            "ok": True,
            "person": person,
            "data": filtered,
            "total": total_records,
        })

    # — POST 处理 —
    if request.method == "POST":
        body = request.get_json(silent=True)
        if not body or "field" not in body:
            return error_response("缺少必填字段 field", 400)
        field = body["field"].strip()
        if field not in data:
            return error_response(f"无效字段: {field}, 可用: {', '.join(sorted(data.keys()))}", 400)

        # 按字段类型处理 value
        if field in ("weight",):
            # 数值类字段: {value: 70.5}
            value = body.get("value")
            if value is None and "weight_value" not in body:
                return error_response(f"{field} 字段需要 value", 400)
            entry = {
                "date": body.get("date", now.strftime("%Y-%m-%d")),
                "value": float(value) if value is not None else float(body.get("weight_value", 0)),
            }
        elif field == "water":
            cups = body.get("cups", body.get("value", 0))
            entry = {
                "date": body.get("date", now.strftime("%Y-%m-%d")),
                "cups": int(cups),
                "total_ml": int(cups) * 250,
            }
        elif field == "sleep":
            entry = {
                "date": body.get("date", now.strftime("%Y-%m-%d")),
                "hours": float(body.get("hours", body.get("value", 0))),
                "quality": body.get("quality", ""),
            }
        elif field == "exercise":
            entry = {
                "date": body.get("date", now.strftime("%Y-%m-%d")),
                "type": body.get("type", "运动"),
                "duration": int(body.get("duration", 0)),
                "calories": int(body.get("calories", body.get("value", 0))),
            }
        else:
            # 通用字段: 记录整个 body（排除 field 键）
            entry = {k: v for k, v in body.items() if k != "field"}
            entry.setdefault("date", now.strftime("%Y-%m-%d"))

        old = data[field][-1] if data[field] else None
        data[field].append(entry)

        try:
            _save_person_data(person, data)
            _notify_partner(request.user, {"event": "data_changed", "by": request.user, "field": field})
        except IOError as e:
            return error_response(f"保存失败: {e}", 500)

        return jsonify({
            "ok": True,
            "person": person,
            "field": field,
            "entry": entry,
            "old": old,
            "total": len(data[field]),
            "message": f"已记录 {person} {field} 数据",
        })


@app.route("/v1/api/daily/data/<person>/<field>", methods=["GET"])
@require_token
def get_person_field(person, field):
    """GET /v1/api/daily/data/{person}/{field} - 字段级数据查询。

    查询某人特定字段的历史记录，用于趋势图等场景。

    查询参数:
      - days:   最近 N 天（默认 90，用于趋势图）
      - limit:  最大返回条数
      - sort:   asc|desc（默认 desc，最新在前）

    返回:
      {"ok":true, "person":"管理员", "field":"weight",
       "data": [{"date":"2026-05-27","value":70.5}, ...], "total": N}
    """
    if person not in KNOWN_PERSONS:
        return error_response(f"未知用户: {person}", 400)
    if field not in DATA_FIELDS:
        return error_response(f"无效字段: {field}, 可用: {', '.join(sorted(DATA_FIELDS))}", 400)

    data = _load_person_data(person)
    records = data.get(field, [])

    days_str = request.args.get("days", "90")
    limit_str = request.args.get("limit", "")
    sort_order = request.args.get("sort", "desc").strip()

    # 按天数过滤
    if days_str.isdigit():
        tz = ZoneInfo("Asia/Shanghai")
        cutoff = (datetime.now(tz) - timedelta(days=int(days_str))).strftime("%Y-%m-%d")
        records = [r for r in records if r.get("date", "") >= cutoff]

    # 排序（默认最新在前）
    records = sorted(records, key=lambda r: r.get("date", ""), reverse=(sort_order != "asc"))

    # 截断
    if limit_str.isdigit():
        records = records[:int(limit_str)]

    return jsonify({
        "ok": True,
        "person": person,
        "field": field,
        "data": records,
        "total": len(records),
    })


# ============================================================
#  食谱 API (DB15)
# ============================================================

WEEKDAY_MAP = {
    "周一": 1, "周二": 2, "周三": 3, "周四": 4,
    "周五": 5, "周六": 6, "周日": 7,
    "星期一": 1, "星期二": 2, "星期三": 3, "星期四": 4,
    "星期五": 5, "星期六": 6, "星期日": 7,
}


def _load_recipe() -> dict:
    """读取食谱文件。"""
    try:
        if os.path.isfile(RECIPE_PATH) and os.path.getsize(RECIPE_PATH) > 0:
            with open(RECIPE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"recipe.json 读取失败: {e}")
    return {}


def _save_recipe(data: dict):
    """保存食谱文件。"""
    os.makedirs(os.path.dirname(RECIPE_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(RECIPE_PATH), exist_ok=True)
    with open(RECIPE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _parse_recipe_text(text: str) -> dict:
    """解析食谱文本，提取每天的午/晚餐。

    示例: "周一 午餐:沙拉 晚餐:鱼 周二 午餐:面"

    返回:
      {"1": {"lunch": "沙拉", "dinner": "鱼"}, "2": {"lunch": "面", "dinner": ""}}
    """
    import re
    result: dict[str, dict] = {}
    current_day = None
    day_pattern = r"(周[一二三四五六日]|星期[一二三四五六日])"

    # 按自然语言分割
    # 策略: 找到每个"周X"标记，切分后续内容直到下一个"周X"
    parts = re.split(rf"(?=({day_pattern}))", text)
    buffer = ""
    for part in parts:
        m = re.match(rf"^{day_pattern}$", part)
        if m:
            # 保存上一个 day 的内容
            if current_day and buffer.strip():
                result[str(WEEKDAY_MAP[current_day])] = _parse_meal_spec(buffer)
            current_day = m.group(1)
            buffer = ""
        else:
            buffer += part

    # 最后一个 day
    if current_day and buffer.strip():
        result[str(WEEKDAY_MAP[current_day])] = _parse_meal_spec(buffer)

    return result


def _parse_meal_spec(spec: str) -> dict:
    """解析单日餐食描述。

    支持: "午餐:沙拉 晚餐:鱼" 或 "午餐: 沙拉, 晚餐: 鱼"
    """
    import re
    meals = {"lunch": "", "dinner": ""}
    meal_map = {"午餐": "lunch", "晚饭": "dinner", "晚餐": "dinner",
                "早饭": "breakfast", "早餐": "breakfast"}

    for cn, en in meal_map.items():
        m = re.search(rf"{cn}[：:，,\s]*([^\s]*?)(?=\s*(?:午餐|晚饭|晚餐|早饭|早餐|$))", spec)
        if m:
            meals[en] = m.group(1).strip().rstrip("，,。.")

    return meals


@app.route("/v1/api/daily/recipe/upload", methods=["POST"])
@require_token
def upload_recipe():
    """POST /v1/api/daily/recipe/upload - 上传/解析食谱。

    请求体: {"text": "周一 午餐:沙拉 晚餐:鱼 周二 午餐:面"}

    支持格式:
      - "周X 午餐:XXX 晚餐:XXX"（自然语言）
      - 每餐用空格或标点分隔

    返回: {"ok":true, "parsed": {"1":{"lunch":"沙拉","dinner":"鱼"}}, "count": 2}
    """
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return error_response("缺少必填字段 text", 400)
    text = data["text"].strip()
    if len(text) < 4:
        return error_response("食谱内容太短", 400)

    parsed = _parse_recipe_text(text)
    if not parsed:
        return error_response("未识别到任何周X标记，请使用格式：周一 午餐:XX 晚餐:XX", 400)

    # 合并到已有食谱
    current = _load_recipe()
    for day, meals in parsed.items():
        current.setdefault(day, {})
        for k, v in meals.items():
            if v:
                current[day][k] = v

    try:
        _save_recipe(current)
    except IOError as e:
        return error_response(f"保存食谱失败: {e}", 500)

    return jsonify({
        "ok": True,
        "parsed": parsed,
        "count": len(parsed),
        "days": sorted(parsed.keys()),
        "message": f"已更新 {len(parsed)} 天食谱",
    })




@app.route("/v1/api/daily/recipe/today", methods=["GET"])
@require_token
def get_today_recipe():
    """GET /v1/api/daily/recipe/today - 查询今日食谱。

    根据当前星期几，从 recipe.json 中读取今日午/晚餐。

    查询参数:
      - day: 覆盖星期几（1-7，Monday=1）

    返回:
      {"ok":true, "day":3, "dayName":"周三",
       "recipe": {"lunch":"沙拉","dinner":"鱼","breakfast":""}}
    """
    day_str = request.args.get("day", "")
    if day_str.isdigit():
        day_num = int(day_str)
        if day_num < 1 or day_num > 7:
            return error_response("day 参数必须为 1-7", 400)
    else:
        tz = ZoneInfo("Asia/Shanghai")
        day_num = datetime.now(tz).isoweekday()  # 1=Mon, 7=Sun

    day_names = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    recipe_data = _load_recipe()
    today_recipe = recipe_data.get(str(day_num), {})

    return jsonify({
        "ok": True,
        "day": day_num,
        "dayName": day_names[day_num],
        "recipe": {
            "breakfast": today_recipe.get("breakfast", ""),
            "lunch": today_recipe.get("lunch", ""),
            "dinner": today_recipe.get("dinner", ""),
        },
        "hasRecipe": any(v for v in today_recipe.values() if v),
    })





@app.route("/v1/api/daily/recipe/week", methods=["GET"])
@require_token
def get_week_recipe():
    """GET /v1/api/daily/recipe/week - 整周食谱。

    返回当前周全部 7 天的食谱数据。

    返回:
      {"ok":true, "days":
        {"1": {"dayName":"周一","lunch":"沙拉","dinner":"鱼"}, ...}}
    """
    recipe_data = _load_recipe()
    day_names = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    days = {}

    for d in range(1, 8):
        dk = str(d)
        raw = recipe_data.get(dk, {})
        days[dk] = {
            "dayName": day_names[d],
            "breakfast": raw.get("breakfast", ""),
            "lunch": raw.get("lunch", ""),
            "dinner": raw.get("dinner", ""),
        }

    filled = sum(1 for v in days.values() if any(x for x in [v["breakfast"], v["lunch"], v["dinner"]] if x))

    return jsonify({
        "ok": True,
        "days": days,
        "filledDays": filled,
    })





# ============================================================
#  心愿池 CRUD API (DB18)
# ============================================================

WISH_STATUSES = {"idea", "discussing", "designing", "implementing", "done", "archived"}

# 允许的状态流转
VALID_TRANSITIONS = {
    "idea":          {"discussing", "archived"},
    "discussing":    {"designing", "idea", "archived"},
    "designing":     {"implementing", "discussing", "archived"},
    "implementing":  {"done", "designing", "archived"},
    "done":          {"archived"},
    "archived":      {"idea"},
}

# 旧状态别名 → 新状态
STATUS_ALIASES = {
    "dreaming":     "idea",
    "planning":     "designing",
    "in_progress":  "implementing",
}


def _normalize_status(status: str) -> str:
    """将旧状态别名转换为新状态。"""
    return STATUS_ALIASES.get(status, status)


def _load_wishes() -> list:
    """读取心愿文件。"""
    try:
        if os.path.isfile(WISHES_PATH) and os.path.getsize(WISHES_PATH) > 0:
            with open(WISHES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"wishes.json 读取失败: {e}")
    return []


def _save_wishes(data: list):
    """保存心愿文件。"""
    os.makedirs(os.path.dirname(WISHES_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(WISHES_PATH), exist_ok=True)
    with open(WISHES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---- 随手记 Notes API ----

def _load_notes() -> dict:
    """读取随手记文件，不存在或错误时返回空字典。"""
    try:
        if os.path.isfile(NOTES_PATH) and os.path.getsize(NOTES_PATH) > 0:
            with open(NOTES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"notes.json 读取失败: {e}")
    return {}


def _save_notes(data: dict):
    """写入随手记文件。"""
    os.makedirs(os.path.dirname(NOTES_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(NOTES_PATH), exist_ok=True)
    with open(NOTES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/v1/api/daily/notes", methods=["GET", "POST"])
@require_token
def notes_list():
    """GET/POST /v1/api/daily/notes - 随手记列表和创建。

    GET 查询参数:
      - person: 按人员过滤（管理员/伴侣）

    POST 请求体:
      {"person":"管理员", "text":"内容", "mood":"💡", "tags":["工作","想法"]}

    返回:
      GET  → {"ok":true, "notes": [...], "total": N}
      POST → {"ok":true, "note": {...}, "message": "已保存"}
    """
    if request.method == "GET":
        notes = _load_notes()
        person = _get_person()

        if person:
            items = notes.get(person, [])
        else:
            items = []
            for person_notes in notes.values():
                if isinstance(person_notes, list):
                    items.extend(person_notes)
            items.sort(key=lambda x: x.get("created", ""), reverse=True)

        # Sort by created desc (newest first)
        if person:
            items = sorted(items, key=lambda x: x.get("created", ""), reverse=True)

        return jsonify({"ok": True, "notes": items, "total": len(items)})

    if request.method == "POST":
        data = request.get_json(silent=True)
        if not data or "text" not in data:
            return error_response("缺少必填字段 text", 400)
        text = data["text"].strip()
        if len(text) < 1:
            return error_response("内容不能为空", 400)

        person = data.get("person", "").strip() or _get_person() or _get_person()
        if person not in KNOWN_PERSONS:
            return error_response(f"未知用户: {person}", 400)

        notes = _load_notes()
        notes.setdefault(person, [])

        tz = ZoneInfo("Asia/Shanghai")
        now_str = datetime.now(tz).isoformat()

        new_id = 1
        for item in notes[person]:
            id_num = 0
            if isinstance(item.get("id"), str) and item["id"].startswith("n"):
                try:
                    id_num = int(item["id"][1:])
                except ValueError:
                    pass
            elif isinstance(item.get("id"), int):
                id_num = item["id"]
            if id_num >= new_id:
                new_id = id_num + 1

        note = {
            "id": f"n{new_id}",
            "text": text,
            "images": data.get("images", []),
            "mood": data.get("mood", ""),
            "tags": data.get("tags", []),
            "created": now_str,
        }
        notes[person].append(note)
        _save_notes(notes)

        return jsonify({"ok": True, "note": note, "message": "随手记已保存"})


@app.route("/v1/api/daily/notes/<note_id>", methods=["PUT", "DELETE"])
@require_token
def notes_item(note_id):
    """PUT/DELETE /v1/api/daily/notes/{id} - 编辑/删除随手记。

    PUT  请求体: {"text":"新内容", "mood":"😊", "tags":["新标签"]}
    DELETE 需要 ?person= 参数。
    """
    notes = _load_notes()

    # 查找 note
    found = None
    found_person = None
    for person, items in notes.items():
        for item in items:
            if str(item.get("id", "")) == str(note_id):
                found = item
                found_person = person
                break
        if found:
            break

    if not found:
        return error_response(f"随手记 {note_id} 不存在", 404)

    if request.method == "DELETE":
        notes[found_person] = [i for i in notes[found_person] if str(i.get("id", "")) != str(note_id)]
        _save_notes(notes)
        return jsonify({"ok": True, "message": f"已删除随手记 {note_id}"})

    if request.method == "PUT":
        data = request.get_json(silent=True)
        if not data:
            return error_response("请求体不能为空", 400)

        if "text" in data:
            found["text"] = data["text"].strip()
        if "mood" in data:
            found["mood"] = data["mood"]
        if "tags" in data:
            found["tags"] = data["tags"]

        _save_notes(notes)
        _notify_partner(request.user, {"event": "card_changed", "by": request.user, "card": "notes"})
        return jsonify({"ok": True, "note": found, "message": "已更新"})


@app.route("/v1/api/daily/notes/search", methods=["GET"])
@require_token
def notes_search():
    """GET /v1/api/daily/notes/search?q=关键词&person=管理员
    全文搜索随手记内容。
    """
    q = request.args.get("q", "").strip()
    if not q:
        return error_response("缺少搜索关键词 q", 400)

    person = _get_person()
    notes = _load_notes()
    results = []

    persons_to_search = [person] if person and person in notes else list(notes.keys())
    for p in persons_to_search:
        for item in notes.get(p, []):
            text = item.get("text", "")
            tags = " ".join(item.get("tags", []))
            if q.lower() in text.lower() or q.lower() in tags.lower():
                results.append(item)

    results.sort(key=lambda x: x.get("created", ""), reverse=True)
    return jsonify({"ok": True, "results": results, "total": len(results), "query": q})


# ---- 收藏夹 Bookmarks API ----

def _load_bookmarks() -> dict:
    """读取收藏夹文件。"""
    try:
        if os.path.isfile(BOOKMARKS_PATH) and os.path.getsize(BOOKMARKS_PATH) > 0:
            with open(BOOKMARKS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"bookmarks.json 读取失败: {e}")
    return {}


def _save_bookmarks(data: dict):
    """写入收藏夹文件。"""
    os.makedirs(os.path.dirname(BOOKMARKS_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(BOOKMARKS_PATH), exist_ok=True)
    with open(BOOKMARKS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/v1/api/daily/bookmarks", methods=["GET", "POST"])
@require_token
def bookmarks_list():
    """GET/POST /v1/api/daily/bookmarks - 收藏夹列表和新增。

    GET 查询参数:
      - person: 管理员/伴侣
      - tag: 按标签过滤

    POST 请求体:
      {"person":"管理员", "url":"https://...", "title":"标题", "tags":["技术"]}
    若未提供 title，服务端将抓取页面标题（B2）。

    收藏按 created 倒序排列。每个条目: {id, url, title, description, favicon, tags, created, read}
    """
    if request.method == "GET":
        bookmarks = _load_bookmarks()
        person = _get_person()
        tag_filter = request.args.get("tag", "").strip()

        if person:
            items = bookmarks.get(person, [])
        else:
            items = []
            for p_items in bookmarks.values():
                if isinstance(p_items, list):
                    items.extend(p_items)

        if tag_filter:
            items = [b for b in items if tag_filter in b.get("tags", [])]

        items = sorted(items, key=lambda x: x.get("created", ""), reverse=True)
        return jsonify({"ok": True, "bookmarks": items, "total": len(items)})

    if request.method == "POST":
        data = request.get_json(silent=True)
        if not data or "url" not in data:
            return error_response("缺少必填字段 url", 400)

        url = data["url"].strip()
        if not url.startswith("http"):
            return error_response("URL 必须以 http 开头", 400)

        person = data.get("person", "").strip() or _get_person() or _get_person()
        if person not in KNOWN_PERSONS:
            return error_response(f"未知用户: {person}", 400)

        bookmarks = _load_bookmarks()
        bookmarks.setdefault(person, [])

        tz = ZoneInfo("Asia/Shanghai")
        now_str = datetime.now(tz).isoformat()

        new_id = 1
        for item in bookmarks[person]:
            if isinstance(item.get("id"), int) and item["id"] >= new_id:
                new_id = item["id"] + 1

        title = data.get("title", "").strip()
        description = data.get("description", "").strip()
        favicon = data.get("favicon", "").strip()
        if not title:
            try:
                import requests as req_lib
                from bs4 import BeautifulSoup
                r = req_lib.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                r.encoding = r.apparent_encoding or "utf-8"
                soup = BeautifulSoup(r.text, "html.parser")
                # 标题
                tag_title = soup.find("title")
                title = tag_title.get_text(strip=True) if tag_title else url
                # 摘要
                if not description:
                    for meta in soup.find_all("meta"):
                        if meta.get("name", "").lower() in ("description", "og:description"):
                            desc = meta.get("content", "").strip()
                            if desc:
                                description = desc[:300]
                                break
                # favicon
                if not favicon:
                    icon_link = soup.find("link", rel=lambda v: v and "icon" in v)
                    if icon_link and icon_link.get("href"):
                        fav_url = icon_link["href"]
                        if fav_url.startswith("//"):
                            favicon = "https:" + fav_url
                        elif not fav_url.startswith("http"):
                            from urllib.parse import urljoin
                            favicon = urljoin(url, fav_url)
            except Exception:
                title = title or url

        bookmark = {
            "id": new_id,
            "url": url,
            "title": title,
            "description": description,
            "favicon": favicon,
            "tags": data.get("tags", []),
            "created": now_str,
            "read": False,
        }
        bookmarks[person].append(bookmark)
        _save_bookmarks(bookmarks)
        _notify_partner(request.user, {"event": "card_changed", "by": request.user, "card": "bookmarks"})
        return jsonify({"ok": True, "bookmark": bookmark, "message": f"已收藏: {title}"})


@app.route("/v1/api/daily/bookmarks/<int:bookmark_id>", methods=["PUT", "DELETE"])
@require_token
def bookmarks_item(bookmark_id):
    """PUT/DELETE /v1/api/daily/bookmarks/{id} - 编辑/删除收藏。

    PUT 请求体: {"title":"新标题", "tags":["新标签"], "read":true}
    DELETE 需要 ?person= 参数。
    """
    bookmarks = _load_bookmarks()

    found, found_person = None, None
    for person, items in bookmarks.items():
        for item in items:
            if item.get("id") == bookmark_id:
                found, found_person = item, person
                break
        if found:
            break

    if not found:
        return error_response(f"收藏 #{bookmark_id} 不存在", 404)

    if request.method == "DELETE":
        bookmarks[found_person] = [i for i in bookmarks[found_person] if i.get("id") != bookmark_id]
        _save_bookmarks(bookmarks)
        return jsonify({"ok": True, "message": f"已删除收藏 #{bookmark_id}"})

    if request.method == "PUT":
        data = request.get_json(silent=True)
        if not data:
            return error_response("请求体不能为空", 400)

        for field in ["title", "description", "favicon"]:
            if field in data:
                found[field] = data[field].strip() if isinstance(data[field], str) else data[field]
        if "tags" in data:
            found["tags"] = data["tags"]
        if "read" in data:
            found["read"] = bool(data["read"])

        _save_bookmarks(bookmarks)
        _notify_partner(request.user, {"event": "card_changed", "by": request.user, "card": "bookmarks"})
        return jsonify({"ok": True, "bookmark": found, "message": "已更新"})


@app.route("/v1/api/daily/bookmarks/fetch", methods=["POST"])
@require_token
def bookmarks_fetch():
    """POST /v1/api/daily/bookmarks/fetch - 抓取 URL 元数据。

    请求体: {"url": "https://..."}
    返回: {"ok": true, "data": {"title": "...", "description": "...", "favicon": "..."}}
    """
    data = request.get_json(silent=True)
    if not data or "url" not in data:
        return error_response("缺少必填字段 url", 400)

    url = data["url"].strip()
    if not url.startswith("http"):
        return error_response("URL 必须以 http 开头", 400)

    try:
        import requests as req_lib
        from bs4 import BeautifulSoup
        r = req_lib.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else url

        description = ""
        for meta in soup.find_all("meta"):
            if meta.get("name", "").lower() in ("description", "og:description"):
                description = meta.get("content", "").strip()[:300]
                break
            if meta.get("property", "").lower() == "og:description":
                description = meta.get("content", "").strip()[:300]
                break

        favicon = ""
        icon_link = soup.find("link", rel=lambda v: v and "icon" in v if v else False)
        if icon_link and icon_link.get("href"):
            from urllib.parse import urljoin
            fav_url = icon_link["href"]
            if fav_url.startswith("//"):
                favicon = "https:" + fav_url
            elif not fav_url.startswith("http"):
                favicon = urljoin(url, fav_url)
            else:
                favicon = fav_url

        return jsonify({"ok": True, "data": {"title": title, "description": description, "favicon": favicon}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502


# ---- 照片墙 Photos API ----

def _load_photos() -> dict:
    """读取照片元数据文件。"""
    try:
        if os.path.isfile(PHOTOS_PATH) and os.path.getsize(PHOTOS_PATH) > 0:
            with open(PHOTOS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"photos.json 读取失败: {e}")
    return {}


def _save_photos(data: dict):
    """写入照片元数据文件。"""
    os.makedirs(os.path.dirname(PHOTOS_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(PHOTOS_PATH), exist_ok=True)
    with open(PHOTOS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/v1/api/daily/photos", methods=["GET", "POST"])
@require_token
def photos_list():
    """GET/POST /v1/api/daily/photos - 照片列表和上传。

    GET 查询参数:
      - person: 管理员/伴侣（不传则返回全部）
      - tab: all / 管理员 / 伴侣（用于双人模式）

    POST (JSON): {"person":"管理员", "image":"/path/to/photo.jpg", "caption":"描述"}
    POST (form): 文件上传 multipart。
    """
    if request.method == "GET":
        photos = _load_photos()
        person = _get_person()
        tab = request.args.get("tab", "").strip()

        if tab and tab != "all":
            items = photos.get(tab, [])
        elif person:
            items = photos.get(person, [])
        else:
            items = []
            for p_items in photos.values():
                if isinstance(p_items, list):
                    items.extend(p_items)

        items = sorted(items, key=lambda x: x.get("created", ""), reverse=True)
        return jsonify({"ok": True, "photos": items, "total": len(items)})

    if request.method == "POST":
        # 文件上传
        if request.content_type and "multipart" in request.content_type:
            f = request.files.get("file")
            if not f or f.filename == "":
                return error_response("未选择文件", 400)
            person = request.form.get("person", "管理员").strip()
            if person not in KNOWN_PERSONS:
                return error_response(f"未知用户: {person}", 400)

            photos_dir = PHOTOS_DIR
            os.makedirs(photos_dir, exist_ok=True)
            tz = ZoneInfo("Asia/Shanghai")
            ts = datetime.now(tz).strftime("%Y%m%d_%H%M%S")
            safe_person = person
            ext = os.path.splitext(f.filename)[1] or ".jpg"
            filename = f"{safe_person}_{ts}{ext}"
            filepath = os.path.join(photos_dir, filename)
            f.save(filepath)

            # 生成缩略图（P2: Pillow 200px）
            thumbnail = ""
            try:
                from PIL import Image
                img = Image.open(filepath)
                img.thumbnail((200, 200), Image.LANCZOS)
                thumb_dir = os.path.join(photos_dir, "thumbnails")
                os.makedirs(thumb_dir, exist_ok=True)
                thumb_filename = f"thumb_{filename}"
                thumb_path = os.path.join(thumb_dir, thumb_filename)
                img.save(thumb_path, quality=85)
                thumbnail = f"/user-files/photos/thumbnails/{thumb_filename}"
            except ImportError:
                logger.warning("Pillow 未安装，跳过缩略图生成")
            except Exception as e:
                logger.warning(f"缩略图生成失败: {e}")

            rel_path = f"/user-files/photos/{filename}"
            caption = request.form.get("caption", "").strip()
            tags = request.form.get("tags", "").strip()
            tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

            photos = _load_photos()
            photos.setdefault(person, [])
            new_id = len(photos[person]) + 1
            # Find next available id
            ids = [item.get("id", 0) for item in photos[person] if isinstance(item.get("id"), int)]
            new_id = max(ids) + 1 if ids else 1

            record = {
                "id": new_id,
                "image": rel_path,
                "thumbnail": thumbnail,
                "caption": caption,
                "likes": [],
                "comments": [],
                "tags": tags_list,
                "created": datetime.now(tz).isoformat(),
            }
            photos[person].append(record)
            _save_photos(photos)
            return jsonify({"ok": True, "photo": record, "message": "上传成功"})

        # JSON 新增
        data = request.get_json(silent=True)
        if not data or "image" not in data:
            return error_response("缺少必填字段 image", 400)

        person = data.get("person", "").strip() or _get_person() or _get_person()
        if person not in KNOWN_PERSONS:
            return error_response(f"未知用户: {person}", 400)

        photos = _load_photos()
        photos.setdefault(person, [])
        ids = [item.get("id", 0) for item in photos[person] if isinstance(item.get("id"), int)]
        new_id = max(ids) + 1 if ids else 1

        record = {
            "id": new_id,
            "thumbnail": data.get("thumbnail", ""),
            "image": data["image"],
            "caption": data.get("caption", "").strip(),
            "likes": [],
            "comments": [],
            "tags": data.get("tags", []),
            "created": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        }
        photos[person].append(record)
        _save_photos(photos)
        _notify_partner(request.user, {"event": "photo_changed", "by": request.user})
        return jsonify({"ok": True, "photo": record, "message": "已添加"})


@app.route("/v1/api/daily/photos/<int:photo_id>", methods=["PUT", "DELETE"])
@require_token
def photos_item(photo_id):
    """PUT/DELETE /v1/api/daily/photos/{id} - 编辑/删除照片。"""
    photos = _load_photos()
    found, found_person = None, None
    for person, items in photos.items():
        for item in items:
            if item.get("id") == photo_id:
                found, found_person = item, person
                break
        if found:
            break
    if not found:
        return error_response(f"照片 #{photo_id} 不存在", 404)

    if request.method == "DELETE":
        photos[found_person] = [i for i in photos[found_person] if i.get("id") != photo_id]
        _save_photos(photos)
        return jsonify({"ok": True, "message": "已删除"})

    if request.method == "PUT":
        data = request.get_json(silent=True)
        if not data:
            return error_response("请求体不能为空", 400)
        if "caption" in data:
            found["caption"] = data["caption"].strip()
        if "tags" in data:
            found["tags"] = data["tags"]
        _save_photos(photos)
        _notify_partner(request.user, {"event": "photo_changed", "by": request.user})
        return jsonify({"ok": True, "photo": found, "message": "已更新"})


@app.route("/v1/api/daily/photos/<int:photo_id>/like", methods=["POST"])
@require_token
def photos_like(photo_id):
    """POST /v1/api/daily/photos/{id}/like - 点赞/取消点赞。

    请求体: {"person":"管理员"}
    若已在 likes 中则移除(取消)，否则添加。
    """
    data = request.get_json(silent=True) or {}
    person = data.get("person", "").strip() or _get_person() or _get_person()
    if person not in KNOWN_PERSONS:
        return error_response(f"未知用户: {person}", 400)

    photos = _load_photos()
    found = None
    found_person = None
    for p, items in photos.items():
        for item in items:
            if item.get("id") == photo_id:
                found, found_person = item, p
                break
        if found:
            break
    if not found:
        return error_response(f"照片 #{photo_id} 不存在", 404)

    likes = found.setdefault("likes", [])
    if person in likes:
        likes.remove(person)
        action = "unliked"
    else:
        likes.append(person)
        action = "liked"
    _save_photos(photos)
    return jsonify({"ok": True, "likes": likes, "action": action})


@app.route("/v1/api/daily/photos/<int:photo_id>/comment", methods=["POST"])
@require_token
def photos_comment(photo_id):
    """POST /v1/api/daily/photos/{id}/comment - 添加评论。

    请求体: {"author":"管理员", "text":"评论内容"}
    """
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return error_response("缺少评论内容", 400)

    author = data.get("author", "管理员").strip()
    if author not in KNOWN_PERSONS:
        return error_response(f"未知用户: {author}", 400)

    photos = _load_photos()
    found = None
    found_person = None
    for p, items in photos.items():
        for item in items:
            if item.get("id") == photo_id:
                found, found_person = item, p
                break
        if found:
            break
    if not found:
        return error_response(f"照片 #{photo_id} 不存在", 404)

    comment = {
        "author": author,
        "text": data["text"].strip(),
        "time": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
    }
    found.setdefault("comments", []).append(comment)
    _save_photos(photos)
    return jsonify({"ok": True, "comment": comment, "message": "评论成功"})


# ---- 分享板 Shares API ----

def _load_shares() -> dict:
    try:
        if os.path.isfile(SHARES_PATH) and os.path.getsize(SHARES_PATH) > 0:
            with open(SHARES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"shares.json 读取失败: {e}")
    return {}


def _save_shares(data: dict):
    os.makedirs(os.path.dirname(SHARES_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(SHARES_PATH), exist_ok=True)
    with open(SHARES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/v1/api/daily/shares", methods=["GET", "POST"])
@require_token
def shares_list():
    if request.method == "GET":
        shares = _load_shares()
        person = _get_person()
        mood = request.args.get("mood", "").strip()
        if person:
            items = shares.get(person, [])
        else:
            items = []
            for p_items in shares.values():
                if isinstance(p_items, list):
                    items.extend(p_items)
        if mood:
            items = [i for i in items if i.get("mood") == mood]
        items = sorted(items, key=lambda x: x.get("created", ""), reverse=True)
        return jsonify({"ok": True, "shares": items, "total": len(items)})

    if request.method == "POST":
        data = request.get_json(silent=True)
        if not data or "text" not in data:
            return error_response("缺少分享内容", 400)
        person = data.get("person", "").strip() or _get_person() or _get_person()
        if person not in KNOWN_PERSONS:
            return error_response(f"未知用户: {person}", 400)
        shares = _load_shares()
        shares.setdefault(person, [])
        ids = [i.get("id", 0) for i in shares[person] if isinstance(i.get("id"), int)]
        new_id = max(ids) + 1 if ids else 1
        record = {
            "id": new_id,
            "text": data["text"].strip(),
            "mood": data.get("mood", "😊").strip(),
            "tags": data.get("tags", []),
            "created": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        }
        shares[person].append(record)
        _save_shares(shares)
        return jsonify({"ok": True, "share": record, "message": "已分享"})


@app.route("/v1/api/daily/shares/<int:share_id>", methods=["DELETE"])
@require_token
def shares_item(share_id):
    shares = _load_shares()
    found, found_person = None, None
    for p, items in shares.items():
        for item in items:
            if item.get("id") == share_id:
                found, found_person = item, p
                break
        if found:
            break
    if not found:
        return error_response(f"分享 #{share_id} 不存在", 404)
    shares[found_person] = [i for i in shares[found_person] if i.get("id") != share_id]
    _save_shares(shares)
    return jsonify({"ok": True, "message": "已删除"})


# ---- 提醒 Reminders API ----

def _load_reminders() -> dict:
    try:
        if os.path.isfile(REMINDERS_PATH) and os.path.getsize(REMINDERS_PATH) > 0:
            with open(REMINDERS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"reminders.json 读取失败: {e}")
    return {}


def _save_reminders(data: dict):
    os.makedirs(os.path.dirname(REMINDERS_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(REMINDERS_PATH), exist_ok=True)
    with open(REMINDERS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/v1/api/daily/reminders", methods=["GET", "POST"])
@require_token
def reminders_list():
    if request.method == "GET":
        reminders = _load_reminders()
        person = _get_person()
        if person:
            items = reminders.get(person, [])
        else:
            items = []
            for p_items in reminders.values():
                if isinstance(p_items, list):
                    items.extend(p_items)
        items = sorted(items, key=lambda x: (not x.get("enabled", True), x.get("time", "")))
        return jsonify({"ok": True, "reminders": items, "total": len(items)})

    if request.method == "POST":
        data = request.get_json(silent=True)
        if not data or "text" not in data or "time" not in data:
            return error_response("缺少必填字段 text 和 time", 400)
        person = data.get("person", "").strip() or _get_person() or _get_person()
        if person not in KNOWN_PERSONS:
            return error_response(f"未知用户: {person}", 400)
        reminders = _load_reminders()
        reminders.setdefault(person, [])
        ids = [i.get("id", 0) for i in reminders[person] if isinstance(i.get("id"), int)]
        new_id = max(ids) + 1 if ids else 1
        record = {
            "id": new_id,
            "type": data.get("type", "once").strip(),
            "text": data["text"].strip(),
            "time": data["time"].strip(),
            "day": data.get("day", "").strip(),
            "date": data.get("date"),
            "enabled": data.get("enabled", True),
            "created": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        }
        reminders[person].append(record)
        _save_reminders(reminders)
        _notify_partner(request.user, {"event": "card_changed", "by": request.user, "card": "reminders"})
        return jsonify({"ok": True, "reminder": record, "message": "已创建"})


@app.route("/v1/api/daily/reminders/<int:reminder_id>", methods=["PUT", "DELETE"])
@require_token
def reminders_item(reminder_id):
    reminders = _load_reminders()
    found, found_person = None, None
    for p, items in reminders.items():
        for item in items:
            if item.get("id") == reminder_id:
                found, found_person = item, p
                break
        if found:
            break
    if not found:
        return error_response(f"提醒 #{reminder_id} 不存在", 404)

    if request.method == "DELETE":
        reminders[found_person] = [i for i in reminders[found_person] if i.get("id") != reminder_id]
        _save_reminders(reminders)
        return jsonify({"ok": True, "message": "已删除"})

    if request.method == "PUT":
        data = request.get_json(silent=True)
        if not data:
            return error_response("请求体不能为空", 400)
        if "text" in data:
            found["text"] = data["text"].strip()
        if "time" in data:
            found["time"] = data["time"].strip()
        if "type" in data:
            found["type"] = data["type"].strip()
        if "day" in data:
            found["day"] = data["day"].strip()
        if "date" in data:
            found["date"] = data["date"]
        if "enabled" in data:
            found["enabled"] = data["enabled"]
        _save_reminders(reminders)
        _notify_partner(request.user, {"event": "card_changed", "by": request.user, "card": "reminders"})
        return jsonify({"ok": True, "reminder": found, "message": "已更新"})


@app.route("/v1/api/daily/reminders/due", methods=["GET"])
@require_token
def reminders_due():
    """GET /v1/api/daily/reminders/due - 查询当前应触发的提醒（供 cron 调用）。"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    current_time = now.strftime("%H:%M")
    current_day = now.strftime("%A")
    weekday_map = {
        "Monday": "周一", "Tuesday": "周二", "Wednesday": "周三",
        "Thursday": "周四", "Friday": "周五", "Saturday": "周六", "Sunday": "周日"
    }
    current_day_cn = weekday_map.get(current_day, "")
    current_date = now.day

    reminders = _load_reminders()
    due = []
    for person, items in reminders.items():
        for item in items:
            if not item.get("enabled", True):
                continue
            rtype = item.get("type", "once")
            rtime = item.get("time", "")
            if rtime != current_time:
                continue
            matched = False
            if rtype == "once":
                matched = True
            elif rtype == "daily":
                matched = True
            elif rtype == "weekly":
                matched = item.get("day", "") == current_day_cn
            elif rtype == "monthly":
                matched = item.get("date") == current_date
            if matched:
                due.append({"person": person, "reminder": item})
    return jsonify({"ok": True, "due": due, "checked_at": now.isoformat()})


# ---- 习惯打卡 Habits API ----

def _load_habits() -> dict:
    try:
        if os.path.isfile(HABITS_PATH) and os.path.getsize(HABITS_PATH) > 0:
            with open(HABITS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"habits.json 读取失败: {e}")
    return {}


def _save_habits(data: dict):
    os.makedirs(os.path.dirname(HABITS_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(HABITS_PATH), exist_ok=True)
    with open(HABITS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _calc_streak(history: dict) -> int:
    """从 history (date→bool) 计算连续打卡天数。"""
    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    streak = 0
    check = today
    while history.get(check):
        streak += 1
        check = (datetime.strptime(check, "%Y-%m-%d").replace(tzinfo=ZoneInfo("Asia/Shanghai")) -
                 timedelta(days=1)).strftime("%Y-%m-%d")
    return streak


@app.route("/v1/api/daily/habits", methods=["GET", "POST"])
@require_token
def habits_list():
    if request.method == "GET":
        habits = _load_habits()
        person = _get_person()
        if person:
            items = habits.get(person, [])
        else:
            items = []
            for p_items in habits.values():
                if isinstance(p_items, list):
                    items.extend(p_items)
        # Update doneToday and streak for each habit
        today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
        for item in items:
            history = item.get("history", {})
            item["doneToday"] = history.get(today, False)
            item["streak"] = _calc_streak(history)
        return jsonify({"ok": True, "habits": items, "total": len(items)})

    if request.method == "POST":
        data = request.get_json(silent=True)
        if not data or "text" not in data:
            return error_response("缺少习惯名称", 400)
        person = data.get("person", "").strip() or _get_person() or _get_person()
        if person not in KNOWN_PERSONS:
            return error_response(f"未知用户: {person}", 400)
        habits = _load_habits()
        habits.setdefault(person, [])
        ids = [i.get("id", 0) for i in habits[person] if isinstance(i.get("id"), int)]
        new_id = max(ids) + 1 if ids else 1
        record = {
            "id": new_id,
            "text": data["text"].strip(),
            "history": {},
            "created": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        }
        habits[person].append(record)
        _save_habits(habits)
        _notify_partner(request.user, {"event": "card_changed", "by": request.user, "card": "habits"})
        return jsonify({"ok": True, "habit": record, "message": "已创建"})


@app.route("/v1/api/daily/habits/<int:habit_id>/toggle", methods=["POST"])
@require_token
def habits_toggle(habit_id):
    """POST /v1/api/daily/habits/{id}/toggle - 切换今日打卡状态。"""
    habits = _load_habits()
    found, found_person = None, None
    for p, items in habits.items():
        for item in items:
            if item.get("id") == habit_id:
                found, found_person = item, p
                break
        if found:
            break
    if not found:
        return error_response(f"习惯 #{habit_id} 不存在", 404)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    history = found.setdefault("history", {})
    if history.get(today):
        del history[today]
    else:
        history[today] = True
    _save_habits(habits)
    streak = _calc_streak(history)
    return jsonify({"ok": True, "doneToday": history.get(today, False), "streak": streak})


@app.route("/v1/api/daily/habits/<int:habit_id>", methods=["DELETE"])
@require_token
def habits_item(habit_id):
    habits = _load_habits()
    found, found_person = None, None
    for p, items in habits.items():
        for item in items:
            if item.get("id") == habit_id:
                found, found_person = item, p
                break
        if found:
            break
    if not found:
        return error_response(f"习惯 #{habit_id} 不存在", 404)
    habits[found_person] = [i for i in habits[found_person] if i.get("id") != habit_id]
    _save_habits(habits)
    return jsonify({"ok": True, "message": "已删除"})


# ---- 全局搜索 API (Phase 11 V2) ----

def _fuzzy_match(query, text, threshold=0.35):
    """使用 SequenceMatcher 做语义模糊匹配，返回 (matches, score, preview)"""
    if not text:
        return False, 0, ""
    text_clean = str(text).lower()
    query_lower = query.lower()
    # 快速路径：直接包含
    if query_lower in text_clean:
        idx = text_clean.index(query_lower)
        start = max(0, idx - 20)
        end = min(len(str(text)), idx + len(query) + 30)
        preview = str(text)[start:end]
        if start > 0:
            preview = "…" + preview
        if end < len(str(text)):
            preview = preview + "…"
        return True, 1.0, preview
    # 模糊匹配
    score = SequenceMatcher(None, query_lower, text_clean[:500]).ratio()
    if score >= threshold:
        return True, score, str(text)[:80] + ("…" if len(str(text)) > 80 else "")
    return False, 0, ""


def _get_card_registry():
    """动态读取卡片注册表，返回已启用卡片列表"""
    cards = []
    registry_path = os.path.join(USER_DATA_DIR, "card-registry.json")
    config_path = os.path.join(USER_DATA_DIR, "dashboard-config.json")
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
        cards = registry.get("cards", [])
    except Exception:
        pass
    # 如果注册表为空，从 config 获取已启用卡片列表
    if not cards:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            enabled = config.get("cards", config.get("enabledCards", []))
            cards = [{"id": c} if isinstance(c, str) else c for c in enabled]
        except Exception:
            pass
    return cards


def _search_card_data(query, card_id, person, limit=5):
    """搜索单个卡片的数据"""
    items = []
    ql = query.lower()
    try:
        if card_id == "todo":
            todos = _load_todos()
            for t in todos.get(person, []):
                ok, score, preview = _fuzzy_match(query, t.get("text", ""))
                if ok:
                    items.append({
                        "id": "todo_" + str(t.get("id", "")),
                        "title": t.get("text", "")[:80],
                        "subtitle": person + (" [已完成]" if t.get("done") else ""),
                        "match_preview": preview if preview != t.get("text","")[:80] else "",
                        "action": "open_daily_card", "action_data": {"card_type": "TodoCard", "view": "daily"},
                        "_score": score
                    })
        elif card_id == "notes":
            notes = _load_notes()
            for n in notes.get(person, []):
                ok, score, preview = _fuzzy_match(query, n.get("text", ""))
                if ok:
                    items.append({
                        "id": "note_" + str(n.get("id", "")),
                        "title": n.get("text", "")[:80],
                        "subtitle": person,
                        "match_preview": preview if preview != n.get("text","")[:80] else "",
                        "action": "open_daily_card", "action_data": {"card_type": "NotesCard"},
                        "_score": score
                    })
        elif card_id == "bookmarks":
            bm = _load_bookmarks()
            for b in bm.get(person, []):
                text = (b.get("title","") + " " + b.get("description","") + " " + b.get("url",""))
                ok, score, preview = _fuzzy_match(query, text)
                if ok:
                    items.append({
                        "id": "bm_" + str(b.get("id", "")),
                        "title": b.get("title","") or b.get("url",""),
                        "subtitle": ", ".join(b.get("tags", [])[:3]) or person,
                        "match_preview": preview if score < 1.0 else "",
                        "action": "open_daily_card", "action_data": {"card_type": "BookmarksCard"},
                        "_score": score
                    })
        elif card_id == "photos":
            photos = _load_photos()
            for p in photos.get(person, []):
                text = (p.get("caption","") + " " + " ".join(p.get("tags", [])))
                ok, score, preview = _fuzzy_match(query, text)
                if ok:
                    items.append({
                        "id": "photo_" + str(p.get("id", "")),
                        "title": p.get("caption","") or "照片 #" + str(p.get("id","")),
                        "subtitle": p.get("created","")[:16],
                        "match_preview": preview if score < 1.0 else "",
                        "action": "open_daily_card", "action_data": {"card_type": "PhotosCard"},
                        "_score": score
                    })
        elif card_id == "reminders":
            reminders = _load_reminders()
            for r in reminders.get(person, []):
                ok, score, preview = _fuzzy_match(query, r.get("text", ""))
                if ok:
                    items.append({
                        "id": "rem_" + str(r.get("id", "")),
                        "title": r.get("text", "")[:80],
                        "subtitle": r.get("time", ""),
                        "match_preview": preview if score < 1.0 else "",
                        "action": "open_daily_card", "action_data": {"card_type": "RemindersCard"},
                        "_score": score
                    })
        elif card_id == "habits":
            habits = _load_habits()
            for h in habits.get(person, []):
                ok, score, preview = _fuzzy_match(query, h.get("text", ""))
                if ok:
                    items.append({
                        "id": "hab_" + str(h.get("id", "")),
                        "title": h.get("text", "")[:80],
                        "subtitle": "🔥" + str(h.get("streak", 0)) + "天",
                        "match_preview": preview if score < 1.0 else "",
                        "action": "open_daily_card", "action_data": {"card_type": "HabitsCard"},
                        "_score": score
                    })
        elif card_id == "wishes":
            wishes = _load_wishes()
            for w in wishes.get(person, []):
                text = (w.get("title","") + " " + w.get("description","") + " " + " ".join(w.get("tags", [])))
                ok, score, preview = _fuzzy_match(query, text)
                if ok:
                    items.append({
                        "id": "wish_" + str(w.get("id", "")),
                        "title": w.get("title", "")[:80],
                        "subtitle": w.get("status", person),
                        "match_preview": preview if score < 1.0 else "",
                        "action": "open_daily_card", "action_data": {"card_type": "WishesCard"},
                        "_score": score
                    })
        elif card_id == "recipe":
            recipes = _load_recipe()
            for day, meals in recipes.get("week", {}).items():
                if isinstance(meals, dict):
                    for meal_type in ["lunch", "dinner"]:
                        text = str(meals.get(meal_type, ""))
                        ok, score, preview = _fuzzy_match(query, text)
                        if ok:
                            items.append({
                                "id": "recipe_" + day + "_" + meal_type,
                                "title": text[:80],
                                "subtitle": day + " " + meal_type,
                                "match_preview": "",
                                "action": "open_daily_card", "action_data": {"card_type": "RecipeCard", "day": day},
                                "_score": score
                            })
        elif card_id == "shares":
            shares = _load_shares()
            for s in shares.get("board", []):
                text = s.get("text", "")
                ok, score, preview = _fuzzy_match(query, text)
                if ok:
                    items.append({
                        "id": "share_" + str(s.get("id", "")),
                        "title": text[:80],
                        "subtitle": s.get("author", person) + " · " + (s.get("created","")[:16]),
                        "match_preview": preview if score < 1.0 else "",
                        "action": "open_daily_card", "action_data": {"card_type": "ShareCard"},
                        "_score": score
                    })
        elif card_id == "data":
            # Search personal data journal entries
            data_dir = os.path.join(USER_DATA_DIR, "profiles")
            for pname in os.listdir(data_dir):
                try:
                    dp = os.path.join(data_dir, pname + ".json")
                    if os.path.exists(dp):
                        with open(dp, "r", encoding="utf-8") as f:
                            pdata = json.load(f)
                        for entry in pdata.get("journal", []):
                            text = str(entry) if isinstance(entry, str) else entry.get("text", "")
                            ok, score, preview = _fuzzy_match(query, text)
                            if ok:
                                items.append({
                                    "id": "data_" + pname + "_" + (entry.get("date","") if isinstance(entry, dict) else ""),
                                    "title": text[:80],
                                    "subtitle": pname + " · 个人数据",
                                    "match_preview": preview if score < 1.0 else "",
                                    "action": "open_daily_card", "action_data": {"card_type": "DataCard", "person": pname},
                                    "_score": score
                                })
                except Exception:
                    pass
    except Exception:
        pass
    items.sort(key=lambda x: x["_score"], reverse=True)
    return items[:limit]


@app.route("/v1/api/search", methods=["GET"])
@require_token
def global_search():
    """GET /v1/api/search?q=关键词&limit=20&mode=precise — 跨所有数据源搜索"""
    query = request.args.get("q", "").strip()
    mode = request.args.get("mode", "fast")  # fast | precise
    limit = int(request.args.get("limit", "20") or "20")
    if not query:
        return jsonify({"ok": True, "results": [], "total": 0, "query": ""})

    person = _get_person()
    results = []
    SESSION_DIR_PATH = "/home/ubuntu/.openclaw/user-sessions"

    # 根据 mode 选择匹配函数
    if mode == "precise":
        _title_match_fn = lambda q, t, th: _jieba_word_match(q, t, min_word_overlap=0.3)[0]
        _msg_match_fn = lambda q, t: _jieba_word_match(q, t, min_word_overlap=0.25)
        _use_semantic = True
    else:
        _title_match_fn = lambda q, t, th: _fuzzy_match(q, t, th)[0]
        _msg_match_fn = lambda q, t: _fuzzy_match(q, str(t))
        _use_semantic = False
    tz = ZoneInfo("Asia/Shanghai")

    # 1. 对话 Session（含消息定位）
    try:
        conv_items = []
        all_abstracts = []
        all_sids = []
        session_map = {}
        for fn in sorted(os.listdir(SESSION_DIR_PATH), reverse=True):
            if not fn.endswith(".json") or fn == "session-index.json":
                continue
            fp = os.path.join(SESSION_DIR_PATH, fn)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    sess = json.load(f)
                title = sess.get("title", "") or fn
                title_ok = _title_match_fn(query, title, 0.4)
                msg_count = 0
                match_idx = -1
                msg_preview = ""
                best_score = 0.0
                for i, msg in enumerate(sess.get("messages", [])):
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
                    ok, score, preview = _msg_match_fn(query, str(content))
                    if ok and (match_idx < 0 or score > best_score):
                        match_idx = i
                        msg_preview = preview
                    msg_count += 1
                if title_ok or match_idx >= 0:
                    sid = fn.replace(".json", "")
                    item = {
                        "id": sid,
                        "title": title,
                        "subtitle": f"{msg_count} 条消息",
                        "match_preview": msg_preview if not title_ok else "",
                        "action": "open_session",
                        "action_data": {"session_id": sid, "message_index": match_idx if match_idx >= 0 else 0},
                        "_score": 1.0 if title_ok else best_score,
                        "_time": sess.get("updated", "")
                    }
                    conv_items.append(item)
                    if _use_semantic:
                        abstract = _build_session_abstract(sess)
                        if abstract.strip() and best_score < 0.9:
                            all_abstracts.append(abstract)
                            all_sids.append(sid)
                            session_map[sid] = item
            except Exception:
                pass
        # 精确模式：用 m3e 做语义补充
        if _use_semantic and all_abstracts:
            try:
                model = _get_st_model()
                if model:
                    q_emb = model.encode(query)
                    abs_embs = model.encode(all_abstracts)
                    from sklearn.metrics.pairwise import cosine_similarity
                    similarities = cosine_similarity([q_emb], abs_embs)[0]
                    for i, sid in enumerate(all_sids):
                        sim = float(similarities[i])
                        if sim > 0.5:
                            item = session_map.get(sid)
                            if item and sim > item.get("_score", 0):
                                item["_score"] = sim
                                if not item.get("match_preview"):
                                    item["match_preview"] = "🔮 语义匹配"
                    logging.info(f'[precise-search] semantic done: query="{query[:50]}", {len(all_sids)} sessions')
            except Exception as e:
                logging.warning(f'[precise-search] semantic failed: {e}')

        conv_items.sort(key=lambda x: (x.get("_score", 0), x.get("_time", "") or ""), reverse=True)
        if conv_items:
            for item in conv_items[:10]:
                item.pop("_score", None)
                item.pop("_time", None)
            results.append({"group": "对话", "icon": "💬", "items": conv_items[:10]})
    except Exception:
        pass

    # 2. 用户文件（模糊匹配）
    try:
        file_items = []
        for fn in os.listdir(USER_FILES_DIR):
            ok, score, _ = _fuzzy_match(query, fn)
            if ok:
                fp = os.path.join(USER_FILES_DIR, fn)
                fstat = os.stat(fp)
                mtime = datetime.fromtimestamp(fstat.st_mtime, tz).strftime("%Y-%m-%d")
                size_kb = fstat.st_size / 1024
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                file_items.append({
                    "id": fn, "title": fn,
                    "subtitle": f"{mtime} · {size_str}",
                    "match_preview": "",
                    "action": "open_file",
                    "action_data": {"path": "/" + fn},
                    "_score": score
                })
        file_items.sort(key=lambda x: x["_score"], reverse=True)
        if file_items:
            for item in file_items[:5]:
                del item["_score"]
            results.append({"group": "文件", "icon": "📁", "items": file_items[:5]})
    except Exception:
        pass

    # 3. Daily 卡片 — 动态枚举所有已有数据的卡片
    card_registry = _get_card_registry()
    card_ids = [c["id"] if isinstance(c, dict) else c for c in card_registry]
    if not card_ids:
        # 回退：搜所有已知卡片类型
        card_ids = ["todo", "notes", "bookmarks", "photos", "reminders", "habits",
                     "wishes", "recipe", "shares", "data"]

    for cid in card_ids:
        try:
            card_items = _search_card_data(query, cid, person, 3)
            if card_items:
                for item in card_items:
                    del item["_score"]
                # 卡片显示名映射
                card_names = {
                    "todo": "Todo", "notes": "随手记", "bookmarks": "收藏夹",
                    "photos": "照片", "reminders": "提醒", "habits": "习惯",
                    "wishes": "心愿", "recipe": "食谱", "shares": "分享板", "data": "数据"
                }
                card_icons = {
                    "todo": "✅", "notes": "📝", "bookmarks": "🔗",
                    "photos": "📸", "reminders": "⏰", "habits": "💪",
                    "wishes": "🎯", "recipe": "🍳", "shares": "📤", "data": "📊"
                }
                cname = card_names.get(cid, cid)
                prefix = "[" + cname + "] "
                for item in card_items:
                    if not item["title"].startswith(prefix):
                        item["title"] = prefix + item["title"]
                results.append({
                    "group": "Daily",
                    "icon": card_icons.get(cid, "📋"),
                    "group_label": cname,
                    "items": card_items
                })
        except Exception:
            pass

    total = sum(len(g["items"]) for g in results)
    return jsonify({"ok": True, "results": results, "total": total, "query": query})
# ---- 日历 API (Phase 14) ----

CALENDAR_PATH = os.path.join(USER_DATA_DIR, "calendar.json")

def _load_calendar() -> dict:
    if os.path.exists(CALENDAR_PATH):
        with open(CALENDAR_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"events": []}

def _save_calendar(data: dict):
    with open(CALENDAR_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _next_event_id(events: list) -> int:
    ids = [e.get("id", 0) for e in events if isinstance(e.get("id"), int)]
    return max(ids, default=0) + 1

# CL2: 日期汇聚
@app.route("/v1/api/calendar/<date>", methods=["GET"])
@require_token
def calendar_date(date: str):
    """GET /v1/api/calendar/{date} - 某日的所有汇聚数据"""
    person = _get_person()
    events = _load_calendar().get("events", [])
    date_events = [e for e in events if e.get("date") == date]

    # 查 Todo
    todos = _load_todos().get(person, [])
    date_todos = [t for t in todos if t.get("date") == date]

    # 查提醒
    reminders = _load_reminders().get(person, [])
    date_reminders = [r for r in reminders if r.get("time", "").startswith(date)]

    # 查食谱
    recipe = _load_recipe()
    dt_obj = datetime.fromisoformat(date)
    weekday = dt_obj.strftime("%A")
    day_recipes = recipe.get(weekday, {})

    # 查随手记
    notes = _load_notes().get(person, [])
    date_notes = [n for n in notes if (n.get("created", ""))[:10] == date]

    # 查照片
    photos = _load_photos().get(person, [])
    date_photos = [p for p in photos if (p.get("created", ""))[:10] == date]

    return jsonify({
        "ok": True,
        "date": date,
        "weekday": weekday,
        "events": date_events,
        "todos": date_todos,
        "reminders": date_reminders,
        "recipe": day_recipes,
        "notes": date_notes,
        "photos": date_photos,
    })

# CL3: 范围标记
@app.route("/v1/api/calendar/range", methods=["GET"])
@require_token
def calendar_range():
    """GET /v1/api/calendar/range?from=2026-06-01&to=2026-06-30"""
    from_date = request.args.get("from", "")
    to_date = request.args.get("to", "")
    person = _get_person()

    try:
        start = datetime.fromisoformat(from_date).date()
        end = datetime.fromisoformat(to_date).date()
    except Exception:
        return error_response("日期格式错误: YYYY-MM-DD", 400)

    # 加载所有数据
    events = _load_calendar().get("events", [])
    todos = _load_todos().get(person, [])
    reminders = _load_reminders().get(person, [])

    result = {}
    delta = (end - start).days
    for d in range(delta + 1):
        day = (start + timedelta(days=d)).isoformat()
        day_count = {"todos": 0, "reminders": 0, "events": [], "is_anniversary": False}

        # Todo 计数（未完成）
        for t in todos:
            if t.get("date") == day and not t.get("done"):
                day_count["todos"] += 1

        # 提醒计数
        for r in reminders:
            if (r.get("time", "")).startswith(day):
                day_count["reminders"] += 1

        # 事件
        for e in events:
            if e.get("date") == day:
                day_count["events"].append(e.get("title", "")[:8])
                if e.get("type") in ("anniversary", "birthday"):
                    day_count["is_anniversary"] = True

        result[day] = day_count

    return jsonify({"ok": True, "range": result, "from": from_date, "to": to_date})

# CL4: 未来事件
@app.route("/v1/api/calendar/upcoming", methods=["GET"])
@require_token
def calendar_upcoming():
    """GET /v1/api/calendar/upcoming - 未来 7 天的重要日期"""
    tz = ZoneInfo("Asia/Shanghai")
    today = datetime.now(tz).date()
    events = _load_calendar().get("events", [])
    upcoming = []
    for i in range(8):
        day = (today + timedelta(days=i)).isoformat()
        day_events = [e for e in events if e.get("date") == day]
        if day_events:
            upcoming.append({"date": day, "events": day_events})
    return jsonify({"ok": True, "upcoming": upcoming})

# CL1: 日历事件 CRUD
@app.route("/v1/api/calendar/events", methods=["GET", "POST"])
@require_token
def calendar_events():
    """GET: 所有事件 | POST: 创建事件"""
    data = _load_calendar()
    events = data.get("events", [])

    if request.method == "GET":
        return jsonify({"ok": True, "events": events})

    body = request.get_json(silent=True)
    if not body or "title" not in body or "date" not in body:
        return error_response("缺少 title 或 date", 400)

    event = {
        "id": _next_event_id(events),
        "title": body["title"].strip(),
        "date": body["date"],
        "type": body.get("type", "appointment"),
        "icon": body.get("icon", "📅"),
        "color": body.get("color", ""),
        "description": body.get("description", ""),
        "time": body.get("time", ""),
        "repeat": body.get("repeat", ""),
        "created_by": request.user,
    }
    events.append(event)
    data["events"] = events
    _save_calendar(data)
    _notify_partner(request.user, {"event": "calendar_changed", "by": request.user})
    return jsonify({"ok": True, "event": event})

@app.route("/v1/api/calendar/events/<int:event_id>", methods=["PUT", "DELETE"])
@require_token
def calendar_event_item(event_id):
    """PUT/DELETE 单个事件"""
    data = _load_calendar()
    events = data.get("events", [])
    idx = next((i for i, e in enumerate(events) if e.get("id") == event_id), None)
    if idx is None:
        return error_response("事件不存在", 404)

    if request.method == "DELETE":
        del events[idx]
        data["events"] = events
        _save_calendar(data)
        _notify_partner(request.user, {"event": "calendar_changed", "by": request.user})
        return jsonify({"ok": True, "message": "已删除"})

    body = request.get_json(silent=True)
    if not body:
        return error_response("缺少请求体", 400)
    e = events[idx]
    for f in ("title", "date", "type", "icon", "color", "description", "time", "repeat"):
        if f in body:
            e[f] = body[f]
    data["events"] = events
    _save_calendar(data)
    _notify_partner(request.user, {"event": "calendar_changed", "by": request.user})
    return jsonify({"ok": True, "event": e})

# CL5: calendar_changed event handler → already in _notify_partner above



# ---- WebSocket 实时同步 (Phase 13) ----

# {username: [ws1, ws2, ...]}
_ws_connections = {}

@sock.route('/v1/ws')
def ws_handler(ws):
    """WebSocket 连接 — JWT token 从 query param 传入"""
    token = request.args.get('token', '')
    username = None
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            username = payload.get('sub', '')
        except Exception:
            pass

    if not username:
        # 无有效 token — 发送错误并关闭
        ws.send(json.dumps({"event": "error", "message": "认证失败"}))
        return

    # 注册连接
    _ws_connections.setdefault(username, []).append(ws)

    try:
        ws.send(json.dumps({"event": "connected", "message": "WebSocket 已连接"}))
        # 保持连接，接收客户端心跳
        while True:
            msg = ws.receive()
            if msg is None:
                break
            # 心跳处理
            data = json.loads(msg) if isinstance(msg, str) else {}
            if data.get('type') == 'ping':
                ws.send(json.dumps({"type": "pong"}))
                continue

            # ---- AI 对话（通过 WebSocket 绕开 Cloudflare Tunnel 100s 超时） ----
            if data.get('type') == 'chat':
                chat_messages = data.get('messages', [])
                chat_user = data.get('user', '')
                chat_model = data.get('model', 'openclaw:assistant')
                req_id = data.get('request_id', '')

                try:
                    gateway_resp = requests.post(
                        'http://127.0.0.1:18789/v1/chat/completions',
                        json={
                            'model': chat_model,
                            'messages': chat_messages,
                            'user': chat_user,
                            'stream': True,
                        },
                        headers={'Authorization': f'Bearer {API_TOKEN}'},
                        stream=True,
                        timeout=(30, 600),
                    )

                    if gateway_resp.status_code != 200:
                        err_text = gateway_resp.text[:500] if gateway_resp.text else ''
                        ws.send(json.dumps({
                            'type': 'chat_error',
                            'message': f'Gateway 返回 {gateway_resp.status_code}: {err_text}',
                            'request_id': req_id,
                        }))
                        continue

                    for line in gateway_resp.iter_lines(decode_unicode=True):
                        if line and line.startswith('data: '):
                            data_str = line[6:]
                            if data_str.strip() == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk.get('choices', [{}])[0].get('delta', {}).get('content', '')
                                if delta:
                                    ws.send(json.dumps({
                                        'type': 'chat_delta',
                                        'content': delta,
                                        'request_id': req_id,
                                    }))
                            except json.JSONDecodeError:
                                pass

                    ws.send(json.dumps({
                        'type': 'chat_done',
                        'request_id': req_id,
                    }))

                except Exception as e:
                    ws.send(json.dumps({
                        'type': 'chat_error',
                        'message': str(e)[:500],
                        'request_id': req_id,
                    }))
                continue
    except Exception:
        pass
    finally:
        # 清理连接
        if username in _ws_connections:
            _ws_connections[username] = [s for s in _ws_connections[username] if s != ws]
            if not _ws_connections[username]:
                del _ws_connections[username]


def _broadcast(event: dict, exclude_user: str = None):
    """向所有在线用户广播事件"""
    for user, sockets in _ws_connections.items():
        if user == exclude_user:
            continue
        payload = json.dumps(event)
        for ws in sockets:
            try:
                ws.send(payload)
            except Exception:
                pass


def _notify_partner(sender_username: str, event: dict):
    """通知发送者的伴侣"""
    users = _load_users()
    partner_name = None
    for uname, uinfo in users.items():
        if isinstance(uinfo, dict) and uinfo.get('partner') == sender_username:
            partner_name = uname
            break
    if partner_name and partner_name in _ws_connections:
        payload = json.dumps(event)
        for ws in _ws_connections[partner_name]:
            try:
                ws.send(payload)
            except Exception:
                pass


def _next_wish_id(wishes: list) -> int:
    """生成下一个心愿 ID。"""
    if not wishes:
        return 1
    return max(w.get("id", 0) for w in wishes) + 1


@app.route("/v1/api/daily/wishes", methods=["GET", "POST"])
@require_token
def wishes_list():
    """GET/POST /v1/api/daily/wishes - 心愿池列表和创建。

    GET 查询参数:
      - status: 按状态过滤 (dreaming/planning/in_progress/done/archived)
      - tag:    按标签过滤
      - limit:  最大返回数

    POST 请求体:
      {"text": "去冰岛看极光", "status": "dreaming", "tags": ["旅行"]}
    """
    if request.method == "GET":
        wishes = _load_wishes()
        status = request.args.get("status", "").strip()
        tag = request.args.get("tag", "").strip()
        limit_str = request.args.get("limit", "")

        if status:
            if status not in WISH_STATUSES:
                return error_response(f"无效状态: {status}, 可用: {', '.join(sorted(WISH_STATUSES))}", 400)
            wishes = [w for w in wishes if w.get("status") == status]

        if tag:
            wishes = [w for w in wishes if tag in w.get("tags", [])]

        if limit_str.isdigit():
            wishes = wishes[:int(limit_str)]

        return jsonify({
            "ok": True,
            "wishes": wishes,
            "total": len(wishes),
        })

    # POST
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return error_response("缺少必填字段 text", 400)
    text = data["text"].strip()
    if len(text) < 2:
        return error_response("心愿内容至少 2 个字符", 400)

    wishes = _load_wishes()
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)

    new_wish = {
        "id": _next_wish_id(wishes),
        "text": text,
        "status": data.get("status", "dreaming").strip(),
        "tags": data.get("tags", []),
        "note": data.get("note", "").strip(),
        "link": data.get("link", "").strip(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    if new_wish["status"] not in WISH_STATUSES:
        return error_response(f"无效状态: {new_wish['status']}", 400)

    wishes.append(new_wish)
    try:
        _save_wishes(wishes)
    except IOError as e:
        return error_response(f"保存失败: {e}", 500)

    return jsonify({
        "ok": True,
        "wish": new_wish,
        "message": f"已添加心愿: {text}",
    })


@app.route("/v1/api/daily/wishes/<int:wish_id>", methods=["PUT", "DELETE"])
@require_token
def wishes_item(wish_id):
    """PUT/DELETE /v1/api/daily/wishes/{id} - 更新/删除心愿。

    PUT 请求体:
      {"status":"planning"}  或 {"text":"新的描述"} 或 {"tags":["旅行"]}

    DELETE 无请求体。
    """
    wishes = _load_wishes()
    idx = next((i for i, w in enumerate(wishes) if w.get("id") == wish_id), None)

    if idx is None:
        return error_response(f"心愿 #{wish_id} 不存在", 404)

    if request.method == "DELETE":
        removed = wishes.pop(idx)
        try:
            _save_wishes(wishes)
        except IOError as e:
            return error_response(f"保存失败: {e}", 500)
        return jsonify({
            "ok": True,
            "wish": removed,
            "message": f"已删除心愿: {removed.get('text', '')}",
        })

    # PUT
    data = request.get_json(silent=True)
    if not data:
        return error_response("请求体不能为空", 400)

    wish = wishes[idx]
    tz = ZoneInfo("Asia/Shanghai")
    changed = False

    if "text" in data:
        t = data["text"].strip()
        if len(t) < 2:
            return error_response("内容至少 2 个字符", 400)
        wish["text"] = t
        changed = True

    if "status" in data:
        s = data["status"].strip()
        if s not in WISH_STATUSES:
            return error_response(f"无效状态: {s}", 400)
        wish["status"] = s
        changed = True

    if "tags" in data:
        wish["tags"] = data["tags"] if isinstance(data["tags"], list) else []
        changed = True

    if "note" in data:
        wish["note"] = data["note"].strip()
        changed = True

    if "link" in data:
        wish["link"] = data["link"].strip()
        changed = True

    if not changed:
        return jsonify({"ok": True, "wish": wish, "message": "无变更"})

    wish["updated_at"] = datetime.now(tz).isoformat()
    try:
        _save_wishes(wishes)
    except IOError as e:
        return error_response(f"保存失败: {e}", 500)

    return jsonify({
        "ok": True,
        "wish": wish,
        "message": f"已更新心愿 #{wish_id}",
    })





@app.route("/v1/api/daily/wishes/<int:wish_id>/status", methods=["PATCH"])
@require_token
def wishes_status_transition(wish_id):
    """PATCH /v1/api/daily/wishes/{id}/status - 心愿状态流转。

    请求体: {"status": "discussing"}

    状态流转规则:
      idea → discussing → designing → implementing → done
      ↑                     ↓                     ↓
      └──── <回退允许> ────┘              archived ↔ idea
    """
    data = request.get_json(silent=True)
    if not data or "status" not in data:
        return error_response("缺少必填字段 status", 400)

    new_status = _normalize_status(data["status"].strip())
    if new_status not in WISH_STATUSES:
        return error_response(f"无效状态: {new_status}, 可用: {', '.join(sorted(WISH_STATUSES))}", 400)

    wishes = _load_wishes()
    idx = next((i for i, w in enumerate(wishes) if w.get("id") == wish_id), None)
    if idx is None:
        return error_response(f"心愿 #{wish_id} 不存在", 404)

    wish = wishes[idx]
    old_status = _normalize_status(wish.get("status", "idea"))

    # 检查流转是否合法
    allowed = VALID_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        return error_response(
            f"不允许从 {old_status} 流转到 {new_status}，"
            f"可从 {old_status} 流转到: {', '.join(sorted(allowed))}",
            400,
        )

    tz = ZoneInfo("Asia/Shanghai")
    wish["status"] = new_status
    wish["updated_at"] = datetime.now(tz).isoformat()

    # 记录流转历史
    history = wish.setdefault("history", [])
    history.append({
        "from": old_status,
        "to": new_status,
        "at": wish["updated_at"],
    })

    try:
        _save_wishes(wishes)
    except IOError as e:
        return error_response(f"保存失败: {e}", 500)

    return jsonify({
        "ok": True,
        "wish": wish,
        "from": old_status,
        "to": new_status,
        "message": f"心愿 #{wish_id}: {old_status} → {new_status}",
    })



# ============================================================
#  周统计汇总 API (DB20)
# ============================================================

@app.route("/v1/api/daily/summary/week", methods=["GET"])
@require_token
def weekly_summary():
    """GET /v1/api/daily/summary/week - 本周统计汇总。

    返回：
      - exercise_days: 本周运动天数 + 总运动时长
      - todo: 本周完成率（人数、完成/总计）
      - data_trends: 各人各字段最新值 + 本周趋势

    返回格式:
      {"ok":true,
       "week":"2026-W22",
       "exercise": {"days":3, "total_min":120},
       "todo": {"completion_rate":60.0, "done":6, "total":10, "persons":{...}},
       "data_trends": {"管理员": {"weight":[{"date":"...","value":70},...], ...}, ...}}
    """
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")
    week_key = _current_week_key()

    result = {
        "ok": True,
        "week": week_key,
        "generated_at": now.isoformat(),
    }

    # ---- 运动统计 ----
    all_exercise_dates: set[str] = set()
    all_exercise_min = 0
    for person in ["管理员", "伴侣"]:
        person_data = _load_person_data(person)
        for entry in person_data.get("exercise", []):
            if _is_in_week(entry.get("date", ""), week_key):
                all_exercise_dates.add(entry.get("date", ""))
                if isinstance(entry.get("duration"), str):
                    nums = re.findall(r"(\d+)", entry["duration"])
                    if nums:
                        all_exercise_min += int(nums[0])
                elif isinstance(entry.get("duration"), (int, float)):
                    all_exercise_min += int(entry["duration"])

    result["exercise"] = {
        "days": len(all_exercise_dates),
        "total_min": all_exercise_min,
    }

    # ---- Todo 统计 ----
    todos = _load_todos()
    week_done = 0
    week_total = 0
    persons_stats = {}
    for person, data in todos.items():
        p_done = 0
        p_total = 0
        for item in data.get("daily", []):
            if _is_in_week(item.get("date", ""), week_key):
                p_total += 1
                if item.get("done"):
                    p_done += 1
        for item in data.get("weekly", []):
            p_total += 1
            if item.get("done"):
                p_done += 1
        week_done += p_done
        week_total += p_total
        persons_stats[person] = {"done": p_done, "total": p_total}
    week_rate = round(week_done / week_total * 100, 1) if week_total > 0 else 0
    result["todo"] = {
        "completion_rate": week_rate,
        "done": week_done,
        "total": week_total,
        "persons": persons_stats,
    }

    # ---- 数据趋势 ----
    data_trends = {}
    fields_to_trend = ["weight", "water", "sleep", "exercise"]
    for person in ["管理员", "伴侣"]:
        person_data = _load_person_data(person)
        person_trends = {}
        for field in fields_to_trend:
            entries = person_data.get(field, [])
            # 只取本周数据
            week_entries = [e for e in entries if _is_in_week(e.get("date", ""), week_key)]
            week_entries.sort(key=lambda e: e.get("date", ""))

            simplified = []
            for e in week_entries:
                entry_summary = {"date": e.get("date", "")}
                if field == "weight":
                    entry_summary["value"] = e.get("value")
                elif field == "water":
                    entry_summary["cups"] = e.get("cups")
                elif field == "sleep":
                    entry_summary["hours"] = e.get("hours")
                elif field == "exercise":
                    entry_summary["type"] = e.get("type", "")
                    entry_summary["duration"] = e.get("duration", "")
                    entry_summary["calories"] = e.get("calories", 0)
                simplified.append(entry_summary)

            if simplified:
                person_trends[field] = simplified
        if person_trends:
            data_trends[person] = person_trends

    result["data_trends"] = data_trends

    return jsonify(result)


# ============================================================
#  月统计汇总 API (DB21)
# ============================================================

def _is_in_month(date_str: str, month_key: str) -> bool:
    """判断日期是否在指定月份内。month_key: YYYY-MM"""
    try:
        if len(date_str) >= 7:
            return date_str[:7] == month_key
        return False
    except Exception:
        return False


@app.route("/v1/api/daily/summary/month", methods=["GET"])
@require_token
def monthly_summary():
    """GET /v1/api/daily/summary/month - 本月统计汇总。

    查询参数:
      - month: 指定月份（YYYY-MM，默认当前月）

    返回:
      {"ok":true, "month":"2026-05",
       "exercise": {"days":12, "total_min":480},
       "todo": {"completion_rate":65.0, "done":18, "total":28, "persons":{...}},
       "data_trends": {...}}
    """
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)
    month_key = request.args.get("month", now.strftime("%Y-%m")).strip()

    result = {
        "ok": True,
        "month": month_key,
        "generated_at": now.isoformat(),
    }

    # ---- 运动统计 ----
    all_exercise_dates: set[str] = set()
    all_exercise_min = 0
    for person in ["管理员", "伴侣"]:
        person_data = _load_person_data(person)
        for entry in person_data.get("exercise", []):
            if _is_in_month(entry.get("date", ""), month_key):
                all_exercise_dates.add(entry.get("date", ""))
                if isinstance(entry.get("duration"), str):
                    nums = re.findall(r"(\d+)", entry["duration"])
                    if nums:
                        all_exercise_min += int(nums[0])
                elif isinstance(entry.get("duration"), (int, float)):
                    all_exercise_min += int(entry["duration"])

    result["exercise"] = {
        "days": len(all_exercise_dates),
        "total_min": all_exercise_min,
    }

    # ---- Todo 统计 ----
    todos = _load_todos()
    month_done = 0
    month_total = 0
    persons_stats = {}
    for person, data in todos.items():
        p_done = 0
        p_total = 0
        for item in data.get("daily", []):
            if _is_in_month(item.get("date", ""), month_key):
                p_total += 1
                if item.get("done"):
                    p_done += 1
        # Weekly todos also count for the month they were created
        for item in data.get("weekly", []):
            created = item.get("created_at", "")
            if created and _is_in_month(created, month_key):
                p_total += 1
                if item.get("done"):
                    p_done += 1
        month_done += p_done
        month_total += p_total
        persons_stats[person] = {"done": p_done, "total": p_total}
    month_rate = round(month_done / month_total * 100, 1) if month_total > 0 else 0
    result["todo"] = {
        "completion_rate": month_rate,
        "done": month_done,
        "total": month_total,
        "persons": persons_stats,
    }

    # ---- 数据趋势 ----
    data_trends = {}
    fields_to_trend = ["weight", "water", "sleep", "exercise"]
    for person in ["管理员", "伴侣"]:
        person_data = _load_person_data(person)
        person_trends = {}
        for field in fields_to_trend:
            entries = person_data.get(field, [])
            month_entries = [e for e in entries if _is_in_month(e.get("date", ""), month_key)]
            month_entries.sort(key=lambda e: e.get("date", ""))

            simplified = []
            for e in month_entries:
                entry_summary = {"date": e.get("date", "")}
                if field == "weight":
                    entry_summary["value"] = e.get("value")
                elif field == "water":
                    entry_summary["cups"] = e.get("cups")
                elif field == "sleep":
                    entry_summary["hours"] = e.get("hours")
                elif field == "exercise":
                    entry_summary["type"] = e.get("type", "")
                    entry_summary["duration"] = e.get("duration", "")
                    entry_summary["calories"] = e.get("calories", 0)
                simplified.append(entry_summary)

            if simplified:
                person_trends[field] = simplified
        if person_trends:
            data_trends[person] = person_trends

    result["data_trends"] = data_trends

    return jsonify(result)


# ---- 错误处理 ----

@app.errorhandler(400)
def bad_request(e):
    return error_response("请求格式错误", 400)

@app.errorhandler(403)
def forbidden(e):
    return error_response("禁止访问", 403)

@app.errorhandler(404)
def not_found(e):
    return error_response("Not found", 404)

@app.errorhandler(405)
def method_not_allowed(e):
    return error_response("方法不允许", 405)

@app.errorhandler(413)
def too_large(e):
    return error_response("请求体过大", 413)

@app.errorhandler(500)
def server_error(e):
    return error_response("服务器内部错误", 500)


# ---- 入口 ----

if __name__ == "__main__":
    _ensure_directories()
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=port, debug=debug, threaded=True)
