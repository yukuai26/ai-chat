#!/usr/bin/env python3
"""
fileserver.py — Flask 文件服务，提供 REST API 管理服务器文件。
Phase 1: 只读端点（GET /ls, /read, /health）
后续 Phase 扩展：写操作（/write, /upload, /mkdir）
"""

import os
import json
import stat
import mimetypes
from pathlib import Path
from functools import wraps
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# ---- 配置 ----
WHITELIST = [
    "/home/ubuntu/.openclaw/workspace-assistant",
    "/home/ubuntu/.openclaw/workspace-build-cat",
]
API_TOKEN = os.environ.get("FILESERVER_TOKEN", "dev-token-placeholder")

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


# ---- 认证中间件（B3 完善） ----

def require_token(f):
    """Token 认证装饰器（占位，B3 实现完整认证）。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if API_TOKEN and token != API_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ---- 路由 ----

@app.route("/v1/files/health", methods=["GET"])
def health():
    """健康检查端点。"""
    return jsonify({"status": "ok", "service": "fileserver"})


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
    """POST /v1/files/mkdir — 创建目录（后续 Phase 实现）。"""
    return jsonify({"error": "创建目录未开放（后续 Phase）"}), 405


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
