#!/usr/bin/env python3
"""data 健康卡片 display 生成器。
单人(yukuai26)。三类数据(body/intake/exercise)按日期稀疏存。
生成：4组7日折线序列(weight/body_fat/intake/burn,可切换) + 最新身体数据(带评级) + 今日摄入/运动。
"""
import json, os, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CARD_DIR = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Asia/Shanghai")
TODAY = datetime.now(TZ).date()
TODAY_S = TODAY.strftime("%Y-%m-%d")
USER = "yukuai26"
TOKEN = "e0fb40cef753818c92577e3c8fe2af53"

def load(name, default):
    p = os.path.join(CARD_DIR, name)
    if os.path.isfile(p) and os.path.getsize(p) > 0:
        try: return json.load(open(p, encoding="utf-8"))
        except Exception: return default
    return default

def last7_dates():
    return [(TODAY - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]

def main():
    data = load("data.json", {}).get(USER, {})
    body = data.get("body", {})
    intake = data.get("intake", {})
    exercise = data.get("exercise", {})
    days = last7_dates()

    # ---- 4 组折线序列(稀疏:只放有数据的点) ----
    def series(getter):
        out = []
        for d in days:
            v = getter(d)
            if v is not None:
                out.append({"date": d[5:], "value": v})  # MM-DD
        return out

    charts = {
        "weight":   series(lambda d: body.get(d, {}).get("weight")),
        "body_fat": series(lambda d: body.get(d, {}).get("body_fat")),
        "intake":   series(lambda d: intake.get(d, {}).get("total")),
        "burn":     series(lambda d: sum(e.get("active_kcal", 0) for e in exercise.get(d, [])) or None),
    }

    # ---- 最新身体数据(取最近有记录的一天) ----
    body_dates = sorted([d for d in body if body[d]], reverse=True)
    latest_body = body.get(body_dates[0], {}) if body_dates else {}
    latest_body_date = body_dates[0] if body_dates else None
    # 体重变化(对比上一条body记录)
    weight_delta = None
    if len(body_dates) >= 2:
        w0 = body.get(body_dates[0], {}).get("weight")
        w1 = body.get(body_dates[1], {}).get("weight")
        if w0 is not None and w1 is not None:
            weight_delta = round(w0 - w1, 2)

    # 身体数据 KV(带评级) — 中文标签
    LABELS = [
        ("weight","体重(kg)"),("bmi","BMI"),("body_fat","体脂率(%)"),("water_rate","体水分率(%)"),
        ("muscle_rate","肌肉率(%)"),("protein_rate","蛋白质率(%)"),("skeletal_muscle","骨骼肌率(%)"),
        ("bmr","基础代谢"),("visceral_fat","内脏脂肪"),("fat_mass","脂肪重量(kg)"),("muscle_mass","肌肉量(kg)")
    ]
    ratings = latest_body.get("ratings", {})
    body_pairs = []
    for k, lab in LABELS:
        if k in latest_body and k != "ratings":
            val = latest_body[k]
            r = ratings.get(k)
            body_pairs.append({"key": lab, "value": str(val) + (f"  〔{r}〕" if r else "")})

    # ---- 今日摄入 ----
    ti = intake.get(TODAY_S, {})
    intake_rows = []
    for k, lab in [("breakfast","早餐"),("lunch","午餐"),("dinner","晚餐"),("snack","加餐")]:
        if k in ti:
            intake_rows.append({"cells":[{"text":lab},{"text":str(ti[k])+" kcal"}]})
    if "water" in ti:
        intake_rows.append({"cells":[{"text":"💧水分"},{"text":str(ti["water"])+" 杯"}]})
    intake_total = ti.get("total")

    # ---- 今日运动 ----
    te = exercise.get(TODAY_S, [])
    ex_rows = []
    for e in te:
        ex_rows.append({"cells":[
            {"text": e.get("type","运动")},
            {"text": f"{e.get('distance_km','?')}km"},
            {"text": e.get("duration","")},
            {"text": str(e.get("active_kcal","?"))+"kcal"}
        ]})

    # ---- summary ----
    parts = []
    if latest_body.get("weight") is not None:
        s = f"⚖️ {latest_body['weight']}kg"
        if weight_delta is not None:
            s += f"({'↓' if weight_delta<0 else '↑' if weight_delta>0 else '='}{abs(weight_delta)})"
        parts.append(s)
    if intake_total is not None:
        parts.append(f"🍽️ 摄入{intake_total}")
    today_burn = sum(e.get("active_kcal",0) for e in te)
    if today_burn:
        parts.append(f"🏃 消耗{today_burn}")
    summary = " | ".join(parts) if parts else "📊 暂无数据，发体脂秤/餐食/运动截图记录"

    # ---- 组装 sections ----
    sections = []
    sections.append({"type":"chart_tabs","title":"📈 7日趋势",
        "tabs":[{"key":"weight","label":"体重(kg)"},{"key":"body_fat","label":"体脂(%)"},
                {"key":"intake","label":"摄入(kcal)"},{"key":"burn","label":"额外消耗(kcal)"}],
        "default":"weight","charts":charts})
    if body_pairs:
        sections.append({"type":"kv","title":f"📊 最新身体数据（{latest_body_date or '—'}）","pairs":body_pairs})
    if intake_rows:
        ft = f"合计 {intake_total} kcal" if intake_total else ""
        sections.append({"type":"table","title":"🍽️ 今日摄入","rows":intake_rows,"footer":ft})
    if ex_rows:
        sections.append({"type":"table","title":"🏃 今日运动","rows":ex_rows})

    display = {
        "summary": summary,
        "sections": sections,
        "charts": charts,
        "generated_date": TODAY_S,
        "generated": datetime.now(TZ).isoformat()
    }
    json.dump(display, open(os.path.join(CARD_DIR,"display.json"),"w"), ensure_ascii=False, indent=2)
    print(f"✅ data display: {summary}")

    if "--no-notify" not in sys.argv:
        try:
            import urllib.request
            req=urllib.request.Request("http://127.0.0.1:5050/v1/api/daily/notify-display-update",
                data=json.dumps({"card":"data"}).encode(),
                headers={"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json"})
            urllib.request.urlopen(req,timeout=5); print("  📡 已通知前端")
        except Exception as e: print(f"  (通知跳过:{e})")

if __name__=="__main__":
    main()
