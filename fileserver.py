#!/usr/bin/env python3
"""
fileserver.py — Flask 文件服务，提供 REST API 管理服务器文件。
Phase 1: GET /ls, /read, /health, POST /mkdir
后续 Phase 扩展：写操作（/write, /upload）
"""

import os
import json
import stat
import logging
import mimetypes
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from functools import wraps
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# ---- 日志 ----
logging.basicConfig(level=logging.INFO, format="[fileserver] %(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---- 配置 ----
WHITELIST = [
    "/home/ubuntu/.openclaw/workspace-assistant",
    "/home/ubuntu/.openclaw/workspace-build-cat",
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

logger.info(f"fileserver 启动，白名单目录: {WHITELIST}")


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
    """Token 认证装饰器。
    
    从 Authorization 头提取 Bearer Token，
    与 API_TOKEN（来自环境变量 / Gateway 配置文件）比对。
    
    安全特性：
    - 拒绝空 Token
    - 拒绝错误 Token
    - 记录认证失败日志（不含 Token 明文）
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        
        # 提取 Bearer Token
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = ""
        
        # 拒绝空 Token
        if not token:
            logger.warning(f"认证失败: 空 Token (path={request.path}, ip={request.remote_addr})")
            return error_response("缺少认证 Token", 401, "请在 Authorization 头中提供 Bearer Token")
        
        # Token 比对
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
    """GET /v1/files/ls?path=<relative-path> — 列出目录内容。"""
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
    """GET /v1/files/read?path=<relative-path> — 读取文件内容。"""
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
    """GET /v1/files/download?path=<relative-path> — 下载文件。

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
    """POST /v1/sessions/new — 创建新 Session，自动生成标题。

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


@app.route("/v1/sessions/list", methods=["GET"])
@require_token
def list_sessions():
    """GET /v1/sessions/list — 返回所有 Session 列表，按更新时间倒序排列。

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
                sessions.append(data)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"跳过无效 Session 文件 {f.name}: {e}")
                continue

        sessions.sort(key=lambda s: s.get("updated", ""), reverse=True)
        return jsonify({"sessions": sessions}), 200

    except OSError as e:
        logger.error(f"读取 Session 列表失败: {e}")
        return error_response("读取 Session 列表失败", 500)


@app.route("/v1/sessions/<session_id>", methods=["GET"])
@require_token
def get_session(session_id):
    """GET /v1/sessions/{id} — 返回指定 Session 的完整消息历史。

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
            return jsonify(data), 200
        else:
            logger.warning(f"Session 路径校验失败: {session_id} 解析到 {session_resolved}")
            return error_response("Session ID 无效", 400)
    except FileNotFoundError:
        return error_response("Session 不存在", 404)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"读取 Session 失败: {session_file}, 错误: {e}")
        return error_response(f"Session 读取失败: {e}", 500)


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

        if role == "user":
            files = msg.get("files", [])
            if files:
                file_names = [Path(f).name for f in files]
                messages.append({
                    "role": "system",
                    "content": f"[历史消息] 用户当时选择了文件: {', '.join(file_names)}",
                })
            messages.append({"role": "user", "content": content})

        elif role == "assistant":
            messages.append({"role": "assistant", "content": content})

    # 新消息的文件附件
    if new_files:
        new_file_names = [Path(f).name for f in new_files]
        messages.append({
            "role": "system",
            "content": f"用户选择了以下文件: {', '.join(new_file_names)}",
        })

    messages.append({"role": "user", "content": new_message})

    return messages


@app.route("/v1/sessions/<session_id>/chat", methods=["POST"])
@require_token
def session_chat(session_id):
    """POST /v1/sessions/{id}/chat — 发送消息到对话，调用 Gateway 获取 AI 回复。

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
    """POST /v1/files/write — 写入文件内容。

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
    """POST /v1/files/upload — 上传文件（multipart/form-data）。
    
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
    """POST /v1/files/mkdir — 创建目录。
    
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
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=port, debug=debug)
