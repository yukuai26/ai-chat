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
            return jsonify({"error": "缺少认证 Token", "detail": "请在 Authorization 头中提供 Bearer Token"}), 401
        
        # Token 比对
        if token != API_TOKEN:
            logger.warning(f"认证失败: Token 不匹配 (path={request.path}, ip={request.remote_addr})")
            return jsonify({"error": "认证失败", "detail": "Token 无效"}), 401
        
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
        return jsonify({"error": f"路径解析失败: {e}"}), 400

    ok, msg = _check_read_access(target)
    if not ok:
        return jsonify({"error": msg}), 403

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

    return jsonify({"error": "未知文件类型"}), 500


@app.route("/v1/files/read", methods=["GET"])
@require_token
def read_file():
    """GET /v1/files/read?path=<relative-path> — 读取文件内容。"""
    path_arg = request.args.get("path", "")
    try:
        target = _resolve_path(path_arg)
    except (ValueError, OSError) as e:
        return jsonify({"error": f"路径解析失败: {e}"}), 400

    ok, msg = _check_read_access(target)
    if not ok:
        return jsonify({"error": msg}), 403

    if not target.is_file():
        return jsonify({"error": "路径不是文件"}), 400

    # 大文件限制：最大 10MB
    if target.stat().st_size > 10 * 1024 * 1024:
        return jsonify({"error": "文件过大（>10MB），请使用 download 接口"}), 413

    return send_file(target, mimetype=mimetypes.guess_type(target.name)[0] or "text/plain")


@app.route("/v1/files/write", methods=["POST"])
@require_token
def write_file():
    """POST /v1/files/write — 写入文件内容（后续 Phase 实现）。"""
    return jsonify({"error": "写操作未开放（Phase 2）"}), 405


@app.route("/v1/files/upload", methods=["POST"])
@require_token
def upload_file():
    """POST /v1/files/upload — 上传文件（后续 Phase 实现）。"""
    return jsonify({"error": "上传未开放（Phase 3）"}), 405


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
        return jsonify({"error": "缺少必填参数", "detail": "请求体需包含 path 字段"}), 400

    path_arg = data["path"]
    try:
        target = _resolve_path(path_arg)
    except (ValueError, OSError) as e:
        return jsonify({"error": f"路径解析失败: {e}"}), 400

    ok, msg = _check_write_access(target, is_dir=True)
    if not ok:
        if msg == "目录已存在":
            return jsonify({"error": msg}), 409
        return jsonify({"error": msg}), 403

    try:
        # 递归创建所有不存在的中间目录
        target.mkdir(parents=True)
        logger.info(f"目录创建成功: {target}")
        return jsonify({"ok": True, "path": str(target)})
    except OSError as e:
        logger.error(f"目录创建失败: {target}, 错误: {e}")
        return jsonify({"error": f"目录创建失败: {e}"}), 500


# ---- 错误处理 ----

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500


# ---- 入口 ----

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=port, debug=debug)
