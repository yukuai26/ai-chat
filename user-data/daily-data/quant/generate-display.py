#!/usr/bin/env python3
"""quant 量化概览卡片 display 生成器。

定位：方案A（QuantDinger 完整功能用它自带 8888 网页）的"快捷方式+粗略信息"卡片。
- 数据：实时从本机 BFF (/v1/api/quant/*) 拉 QuantDinger 概览(策略/持仓/模拟单/回测任务)
- 展示：缩略=策略数/持仓数/最近回测；展开=明细 + "打开完整量化平台"按钮(走 /quant/url 动态地址)
- 不存自有数据；纯聚合展示。对话操作由卡片喵走 BFF。
"""
import json, os, sys, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

CARD_DIR = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime.now(TZ)
TOKEN = "e0fb40cef753818c92577e3c8fe2af53"
BFF = "http://127.0.0.1:5050/v1/api/quant"

def _get(path, timeout=15):
    req = urllib.request.Request(f"{BFF}{path}", headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"_error": str(e)}

def _arr(node):
    """从 QD {code,data,message} 取 data 数组。"""
    if isinstance(node, dict):
        d = node.get("data")
        if isinstance(d, list): return d
    return []

def main():
    health = _get("/health")
    qd_up = bool(health.get("ok")) and bool(health.get("token_configured"))
    urlinfo = _get("/url")
    qd_url = urlinfo.get("url", "") if isinstance(urlinfo, dict) else ""

    overview = _get("/overview")
    strategies = _arr(overview.get("strategies", {}))
    positions  = _arr(overview.get("positions", {}))
    paper      = _arr(overview.get("paper_orders", {}))
    jobs       = _arr(overview.get("jobs", {}))

    n_strat = len(strategies); n_pos = len(positions); n_paper = len(paper); n_job = len(jobs)

    # summary（缩略态）
    if not qd_up:
        summary = "📈 量化平台未就绪（QD 不可达或 token 未配）"
    else:
        summary = f"📈 策略 {n_strat} · 持仓 {n_pos} · 模拟单 {n_paper} · 回测 {n_job}"

    sections = []

    # 状态行
    status_txt = "🟢 在线" if qd_up else "🔴 离线"
    sections.append({"type": "kv", "title": "🔌 平台状态", "pairs": [
        {"key": "QuantDinger", "value": status_txt},
        {"key": "策略", "value": str(n_strat)},
        {"key": "持仓", "value": str(n_pos)},
        {"key": "模拟单", "value": str(n_paper)},
        {"key": "回测任务", "value": str(n_job)},
    ]})

    # 策略列表（最多5条）
    if strategies:
        rows = []
        for s in strategies[:5]:
            name = s.get("name") or s.get("strategy_name") or s.get("title") or f"#{s.get('id','')}"
            st = s.get("status") or s.get("state") or "—"
            rows.append({"cells": [{"text": str(name)}, {"text": str(st)}]})
        sections.append({"type": "table", "title": "🧠 策略", "header": [{"text": "名称"}, {"text": "状态"}], "rows": rows})

    # 持仓
    if positions:
        rows = []
        for p in positions[:5]:
            sym = p.get("symbol") or p.get("code") or "—"
            qty = p.get("qty") or p.get("quantity") or p.get("position") or "—"
            pnl = p.get("pnl") or p.get("unrealized_pnl") or p.get("profit") or ""
            rows.append({"cells": [{"text": str(sym)}, {"text": str(qty)}, {"text": str(pnl)}]})
        sections.append({"type": "table", "title": "💼 持仓(模拟)", "header": [{"text": "标的"}, {"text": "数量"}, {"text": "盈亏"}], "rows": rows})

    # 最近回测任务
    if jobs:
        rows = []
        for j in jobs[:5]:
            jt = j.get("type") or j.get("kind") or "回测"
            js = j.get("status") or j.get("state") or "—"
            jid = j.get("id") or j.get("job_id") or ""
            rows.append({"cells": [{"text": f"{jt} #{jid}"}, {"text": str(js)}]})
        sections.append({"type": "table", "title": "🧪 最近回测/任务", "header": [{"text": "任务"}, {"text": "状态"}], "rows": rows})

    # 空状态提示
    if qd_up and not (strategies or positions or jobs):
        sections.append({"type": "note", "title": "💡 提示",
            "text": "还没有策略/持仓/回测。可以在完整平台里建策略跑回测，或直接跟我说「帮我跑个均线回测」由卡片喵代为操作。"})

    # 打开完整平台按钮（link section）
    if qd_url:
        sections.append({"type": "link", "title": "🚀 完整平台",
            "text": "打开 QuantDinger 完整量化平台（回测 / 策略 / K线 / 模拟盘）",
            "url": qd_url, "label": "打开完整量化平台 →"})
    else:
        sections.append({"type": "note", "title": "🚀 完整平台",
            "text": "完整平台地址暂不可用（tunnel 未启动？运行 qd-tunnel.sh）。"})

    display = {
        "summary": summary,
        "sections": sections,
        "generated": NOW.isoformat(),
        "generated_date": NOW.strftime("%Y-%m-%d"),
    }
    json.dump(display, open(os.path.join(CARD_DIR, "display.json"), "w"), ensure_ascii=False, indent=2)
    print(f"✅ quant display: {summary}")

    # 通知前端
    if "--no-notify" not in sys.argv:
        try:
            req = urllib.request.Request("http://127.0.0.1:5050/v1/api/daily/notify-display-update",
                data=json.dumps({"card": "quant"}).encode(),
                headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5); print("  📡 已通知前端")
        except Exception as e:
            print(f"  (通知跳过: {e})")

if __name__ == "__main__":
    main()
