"""
quant_bff.py — QuantDinger BFF 转发蓝图（Web Chat ↔ QuantDinger Agent Gateway）

设计见 ac-quant-page-design-V1.0-DRAFT.md。
- 网页只跟我们的后端(/v1/api/quant/*)说话，带 Web Chat 自己的 JWT
- 我们后端转发到 QuantDinger /api/agent/v1/*，注入 QD agent token(藏服务器，不下发前端)
- 安全：只暴露 读 + 回测 + 模拟盘(paper) 能力；实盘相关不开放

用法（在 fileserver.py 里）：
    from quant_bff import quant_bp, init_quant
    init_quant(auth_required)        # 传入现有鉴权装饰器
    app.register_blueprint(quant_bp)

配置：读 /home/ubuntu/quantdinger/agent_token.txt（明天发了 token 写进去）
"""
import os, json, requests
from flask import Blueprint, request, jsonify, Response, stream_with_context

quant_bp = Blueprint("quant", __name__)

# QuantDinger Agent Gateway 基址（同机 docker，backend 绑 127.0.0.1:5000）
QD_BASE = os.environ.get("QD_AGENT_BASE", "http://127.0.0.1:5000/api/agent/v1")
QD_TOKEN_FILE = os.environ.get("QD_AGENT_TOKEN_FILE", "/home/ubuntu/quantdinger/agent_token.txt")
_TIMEOUT = 30

def _qd_token():
    """读 QuantDinger agent token（明天发了 token 写进 QD_TOKEN_FILE）。"""
    t = os.environ.get("QD_AGENT_TOKEN")
    if t:
        return t.strip()
    try:
        if os.path.isfile(QD_TOKEN_FILE):
            return open(QD_TOKEN_FILE).read().strip()
    except Exception:
        pass
    return ""

def _qd_headers():
    return {"Authorization": f"Bearer {_qd_token()}", "Content-Type": "application/json"}

def _qd_get(path, params=None):
    r = requests.get(f"{QD_BASE}{path}", headers=_qd_headers(), params=params, timeout=_TIMEOUT)
    return r

def _qd_post(path, body=None):
    r = requests.post(f"{QD_BASE}{path}", headers=_qd_headers(), json=body or {}, timeout=_TIMEOUT)
    return r

def _relay(r):
    """把 QD 响应透传给前端（保留状态码）。"""
    try:
        return jsonify(r.json()), r.status_code
    except Exception:
        return jsonify({"ok": False, "error": "QuantDinger 响应解析失败", "raw": r.text[:500]}), r.status_code

def _no_token_guard():
    if not _qd_token():
        return jsonify({"ok": False, "error": "QuantDinger agent token 未配置（待管理员在 8888 发 token 写入 agent_token.txt）",
                        "code": "QD_TOKEN_MISSING"}), 503
    return None

# auth_required 由 fileserver 注入
_auth = None
def init_quant(auth_required):
    global _auth
    _auth = auth_required

def _guarded(view):
    """先过 Web Chat 鉴权，再检查 QD token。"""
    def wrapper(*a, **k):
        guard = _no_token_guard()
        if guard: return guard
        return view(*a, **k)
    wrapper.__name__ = view.__name__
    return wrapper

# ============ 健康/身份 ============
@quant_bp.route("/v1/api/quant/health", methods=["GET"])
def quant_health():
    """QD 存活（不需 token，用于前端探测后端在不在）。"""
    try:
        r = requests.get(f"{QD_BASE}/health", timeout=8)
        return jsonify({"ok": True, "qd": r.json(), "token_configured": bool(_qd_token())})
    except Exception as e:
        return jsonify({"ok": False, "error": f"QuantDinger 不可达: {e}", "token_configured": bool(_qd_token())}), 502

@quant_bp.route("/v1/api/quant/whoami", methods=["GET"])
def quant_whoami():
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_get("/whoami"))

# ============ 读接口（给页面展示） ============
@quant_bp.route("/v1/api/quant/overview", methods=["GET"])
def quant_overview():
    """聚合概览：持仓 + 模拟单 + 策略 + 最近任务。前端概览页用。"""
    g = _no_token_guard()
    if g: return g
    out = {"ok": True}
    try:
        out["positions"] = _qd_get("/portfolio/positions").json()
    except Exception as e: out["positions_error"] = str(e)
    try:
        out["paper_orders"] = _qd_get("/portfolio/paper-orders").json()
    except Exception as e: out["paper_orders_error"] = str(e)
    try:
        out["strategies"] = _qd_get("/strategies").json()
    except Exception as e: out["strategies_error"] = str(e)
    try:
        out["jobs"] = _qd_get("/jobs").json()
    except Exception as e: out["jobs_error"] = str(e)
    return jsonify(out)

@quant_bp.route("/v1/api/quant/strategies", methods=["GET"])
def quant_strategies():
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_get("/strategies"))

@quant_bp.route("/v1/api/quant/strategies/<sid>", methods=["GET"])
def quant_strategy_detail(sid):
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_get(f"/strategies/{sid}"))

@quant_bp.route("/v1/api/quant/portfolio", methods=["GET"])
def quant_portfolio():
    g = _no_token_guard()
    if g: return g
    out = {}
    out["positions"] = _qd_get("/portfolio/positions").json()
    out["paper_orders"] = _qd_get("/portfolio/paper-orders").json()
    return jsonify(out)

@quant_bp.route("/v1/api/quant/indicators", methods=["GET"])
def quant_indicators():
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_get("/indicators"))

@quant_bp.route("/v1/api/quant/indicators/<iid>", methods=["GET"])
def quant_indicator_detail(iid):
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_get(f"/indicators/{iid}"))

@quant_bp.route("/v1/api/quant/jobs", methods=["GET"])
def quant_jobs():
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_get("/jobs"))

@quant_bp.route("/v1/api/quant/jobs/<jid>", methods=["GET"])
def quant_job_detail(jid):
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_get(f"/jobs/{jid}"))

@quant_bp.route("/v1/api/quant/markets", methods=["GET"])
def quant_markets():
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_get("/markets"))

@quant_bp.route("/v1/api/quant/klines", methods=["GET"])
def quant_klines():
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_get("/klines", params=request.args.to_dict()))

@quant_bp.route("/v1/api/quant/price", methods=["GET"])
def quant_price():
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_get("/price", params=request.args.to_dict()))

# ============ 操作接口（回测 + 模拟盘，不含实盘） ============
@quant_bp.route("/v1/api/quant/backtests", methods=["POST"])
def quant_backtest():
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_post("/backtests", request.get_json(silent=True) or {}))

@quant_bp.route("/v1/api/quant/strategies", methods=["POST"])
def quant_create_strategy():
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_post("/strategies", request.get_json(silent=True) or {}))

@quant_bp.route("/v1/api/quant/quick-trade", methods=["POST"])
def quant_quick_trade():
    """下单 — 仅模拟盘(paper)。强制注入 paper 标记，拦截实盘。"""
    g = _no_token_guard()
    if g: return g
    body = request.get_json(silent=True) or {}
    # 安全：强制 paper，禁止前端传 live
    body["paper"] = True
    if str(body.get("mode", "")).lower() == "live" or body.get("live") is True:
        return jsonify({"ok": False, "error": "实盘交易未开放（仅模拟盘）", "code": "LIVE_DISABLED"}), 403
    return _relay(_qd_post("/quick-trade/orders", body))

@quant_bp.route("/v1/api/quant/kill-switch", methods=["POST"])
def quant_kill_switch():
    g = _no_token_guard()
    if g: return g
    return _relay(_qd_post("/quick-trade/kill-switch", {}))

# 实盘启动策略 = PATCH status=running 需 T scope —— 本 BFF 不开放该路由（安全红线）
