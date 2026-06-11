#!/usr/bin/env python3
"""todo 卡片 display 生成器。
按 rules.json：当日 / 逾期未完成(或今天刚勾) / 未来7天 三段，左右两栏(yukuai26 / gugugu)。
display 过滤靠 date + done_date，不靠单纯 done —— 当天勾的划线保留，隔天自然消失。
"""
import json, os, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CARD_DIR = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Asia/Shanghai")
TODAY = datetime.now(TZ).strftime("%Y-%m-%d")
USERS = [("yukuai26", "玩UKAI 26"), ("gugugu", "咕咕咕")]
TOKEN = "e0fb40cef753818c92577e3c8fe2af53"

def load(name, default):
    p = os.path.join(CARD_DIR, name)
    if os.path.isfile(p) and os.path.getsize(p) > 0:
        try: return json.load(open(p, encoding="utf-8"))
        except Exception: return default
    return default

def build_user_sections(items):
    """对单个用户的 todo 列表，按三段分类。返回 list of section。"""
    today_list, overdue_list, future_list = [], [], []
    future_limit = (datetime.now(TZ).date() + timedelta(days=7)).strftime("%Y-%m-%d")
    for it in items:
        d = it.get("date") or ""
        done = bool(it.get("done"))
        dd = it.get("done_date")
        entry = {"text": it.get("text",""), "id": it.get("id"), "done": done}
        if d == TODAY:
            today_list.append(entry)
        elif d < TODAY:
            # 逾期：未完成 或 今天刚勾完成的(划线保留)
            if (not done) or (dd == TODAY):
                overdue_list.append(entry)
        elif d > TODAY and d <= future_limit:
            future_list.append(entry)
    # 今日：未完成在前，完成(划线)在后
    today_list.sort(key=lambda x: x["done"])
    overdue_list.sort(key=lambda x: x["done"])
    sections = []
    if today_list:   sections.append({"title": "📅 今日", "type": "list", "items": today_list})
    if overdue_list: sections.append({"title": "⏰ 逾期未完成", "type": "list", "items": overdue_list})
    if future_list:  sections.append({"title": "🔮 即将到来", "type": "list", "items": future_list})
    return sections, today_list, overdue_list

def main():
    data = load("data.json", {})
    columns = []
    summary_parts = []
    for uid, uname in USERS:
        items = data.get(uid, []) or []
        # 防御(2026-06-11): 兼容旧嵌套格式 {daily:[]} / 过滤非dict脏项, 避免崩溃引发刷新风暴
        if isinstance(items, dict):
            flat = []
            for v in items.values():
                if isinstance(v, list): flat.extend(v)
            items = flat
        items = [it for it in items if isinstance(it, dict)]
        sections, today_list, overdue_list = build_user_sections(items)
        # 摘要分母 = 当日 + 逾期未完成 的总数；分子 = 其中已完成
        active = today_list + overdue_list
        total = len(active)
        done_cnt = sum(1 for x in active if x["done"])
        summary_parts.append(f"{uname} {done_cnt}/{total}")
        columns.append({"user": uid, "title": uname, "sections": sections})
    display = {
        "summary": "　".join(summary_parts) if summary_parts else "📋 暂无待办",
        "layout": "two_column",
        "columns": columns,
        "generated_date": TODAY,
        "generated": datetime.now(TZ).isoformat()
    }
    json.dump(display, open(os.path.join(CARD_DIR, "display.json"), "w"),
              ensure_ascii=False, indent=2)
    print(f"✅ todo display 生成: {display['summary']}")

    # 发通知(可选，失败不影响生成)
    if "--no-notify" not in sys.argv:
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://127.0.0.1:5050/v1/api/daily/notify-display-update",
                data=json.dumps({"card": "todo"}).encode(),
                headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
            print("  📡 已通知前端刷新")
        except Exception as e:
            print(f"  (通知跳过: {e})")

if __name__ == "__main__":
    main()
