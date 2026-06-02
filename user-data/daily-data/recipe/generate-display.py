#!/usr/bin/env python3
"""recipe 卡片：data.json → display.json

前端唯一数据源。输出 sections 格式供前端通用渲染。
由卡片喵与 rules.json 共同维护。
"""

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CARD_DIR = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Asia/Shanghai")
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
USERS = ["yukuai26", "gugugu"]

# 非正餐分类关键词
SNACK_KEYWORDS = {
    "零食": ["薯片", "饼干", "蛋糕", "面包", "糕点", "巧克力", "糖果", "坚果", "瓜子", "膨化", "辣条", "卤味", "冰淇淋", "雪糕"],
    "水果": ["苹果", "香蕉", "橙", "柑", "桃", "梨", "葡萄", "草莓", "蓝莓", "西瓜", "哈密瓜", "芒果", "猕猴桃", "樱桃", "荔枝", "龙眼", "火龙果", "柚子", "木瓜", "菠萝", "百香果", "车厘子"],
    "饮品": ["奶茶", "咖啡", "果汁", "可乐", "雪碧", "茶", "牛奶", "酸奶", "豆浆", "饮料", "啤酒", "酒", "气泡水"]
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    data.setdefault("updated", datetime.now(TZ).isoformat())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_today():
    today = datetime.now(TZ)
    return WEEKDAYS[today.weekday()], today.strftime("%Y-%m-%d"), today


def get_week_dates(today):
    weekday = today.weekday()
    monday = today - timedelta(days=weekday)
    return [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(weekday + 1)]


def classify_snack(name, time_str=None):
    if time_str:
        try:
            hour = int(time_str.split(":")[0])
            if hour >= 21 or hour < 4:
                return "夜宵"
        except (ValueError, IndexError):
            pass
    for category, keywords in SNACK_KEYWORDS.items():
        for kw in keywords:
            if kw in name:
                return category
    return "其他"


def build_summary(today_label, recommendation, today_total):
    recom = recommendation.get("items", [])
    recom_text = "待定"
    if recom:
        parts = []
        for item in recom:
            name = item.get("name", "")
            portion = item.get("portion", "")
            cal = item.get("calories")
            if portion and cal:
                parts.append(f"{name}{portion}({cal}kcal)")
            elif portion:
                parts.append(f"{name}{portion}")
            else:
                parts.append(name)
        recom_text = " + ".join(parts[:6])
        total_cal = recommendation.get("total", {}).get("calories", 0)
        if total_cal:
            recom_text += f" = {total_cal}kcal"

    intake_parts = ["已摄入"]
    for user in USERS:
        cal = today_total.get(user, {}).get("calories", 0)
        if cal:
            intake_parts.append(f"{user} {cal}kcal")
        else:
            intake_parts.append(f"{user} 暂无")
    return f"🥗 {today_label} 推荐: {recom_text} | {' '.join(intake_parts)}"


def extract_intake(today_log):
    intake = {u: [] for u in USERS}
    totals = {u: {"calories": 0} for u in USERS}
    for user in USERS:
        ulog = today_log.get(user, {})
        for meal_type in ["breakfast", "lunch", "dinner", "snack"]:
            meals = ulog.get(meal_type, [])
            if isinstance(meals, dict):
                meals = [meals]
            for m in (meals if isinstance(meals, list) else []):
                entry = {"meal": meal_type, "name": m.get("name", ""), "calories": m.get("calories", 0)}
                intake[user].append(entry)
                totals[user]["calories"] += m.get("calories", 0)
    return intake, totals


def build_snack_stats(intake_log, week_dates, user):
    """统计某用户本周非正餐摄入"""
    categories = {}
    total_cal = 0
    for date_str in week_dates:
        day_log = intake_log.get(date_str, {})
        user_log = day_log.get(user, {})
        snacks = user_log.get("snack", [])
        if isinstance(snacks, dict):
            snacks = [snacks]
        if not isinstance(snacks, list):
            snacks = []
        for item in snacks:
            name = item.get("name", "未知")
            cal = item.get("calories", 0)
            time_str = item.get("time", "")
            cat = classify_snack(name, time_str)
            if cat not in categories:
                categories[cat] = {"calories": 0, "items": []}
            categories[cat]["calories"] += cal
            categories[cat]["items"].append(name)
            total_cal += cal
    return categories, total_cal


def build_nutrition_advice(intake_log, week_dates, user):
    """根据最近摄入给出营养建议"""
    total_protein = 0
    total_carbs = 0
    total_fat = 0
    total_calories = 0
    days_with_data = 0
    has_fruit = False

    for date_str in week_dates:
        day_log = intake_log.get(date_str, {})
        user_log = day_log.get(user, {})
        day_cal = 0
        for meal_type in ["breakfast", "lunch", "dinner", "snack"]:
            meals = user_log.get(meal_type, [])
            if isinstance(meals, dict):
                meals = [meals]
            if not isinstance(meals, list):
                meals = []
            for m in meals:
                cal = m.get("calories", 0)
                day_cal += cal
                macros = m.get("macros", {})
                for key, acc in [("protein", "p"), ("carbs", "c"), ("fat", "f")]:
                    val_str = macros.get(key, "0g")
                    try:
                        val = float(str(val_str).replace("g", ""))
                    except (ValueError, AttributeError):
                        val = 0
                    if key == "protein":
                        total_protein += val
                    elif key == "carbs":
                        total_carbs += val
                    else:
                        total_fat += val
                name = m.get("name", "")
                for kw in SNACK_KEYWORDS.get("水果", []):
                    if kw in name:
                        has_fruit = True
                        break
        if day_cal > 0:
            total_calories += day_cal
            days_with_data += 1

    if days_with_data == 0:
        return "暂无摄入记录，记录饮食后可获得营养建议 📝"

    avg_cal = total_calories / days_with_data
    avg_protein = total_protein / days_with_data

    advices = []
    if avg_protein > 0 and avg_protein < 60:
        advices.append("蛋白质偏低，建议增加鸡胸肉/鱼/蛋白/豆腐等优质蛋白")
    if total_carbs > 0 and (total_carbs / days_with_data) > 250:
        advices.append("碳水偏高，减脂期建议控制精制碳水，用粗粮替代")
    if not has_fruit:
        advices.append("水果摄入较少，建议每天补充200g水果，补充维C和膳食纤维")
    if avg_cal > 2200:
        advices.append(f"日均{int(avg_cal)}kcal偏高，建议控制在1800-2000kcal")
    elif 0 < avg_cal < 1200:
        advices.append(f"日均仅{int(avg_cal)}kcal过低，建议不低于1500kcal")
    if not advices:
        advices.append("近期营养摄入较均衡，继续保持 💪")
    return "；".join(advices[:3])


def build_sections(today_label, today_menu, recommendation, today_intake, today_total,
                   intake_log, week_dates):
    """构建前端 sections 数组"""
    sections = []

    # 1. 今日食谱
    if today_menu:
        rows = []
        for cat, dishes in today_menu.items():
            if dishes:
                rows.append({"cells": [
                    {"text": cat, "style": "color:var(--text-secondary);width:60px"},
                    {"text": "、".join(dishes)}
                ]})
        sections.append({
            "title": f"🍽️ 今日食谱 ({today_label})",
            "type": "table",
            "rows": rows
        })

    # 2. 午餐推荐配比
    recom_items = recommendation.get("items", [])
    if recom_items:
        rows = []
        for item in recom_items:
            rows.append({"cells": [
                {"text": item.get("name", "")},
                {"text": item.get("portion", "")},
                {"text": f"{item.get('calories', 0)}kcal"}
            ]})
        total = recommendation.get("total", {})
        rows.append({"cells": [
            {"text": "合计", "style": "font-weight:bold"},
            {"text": ""},
            {"text": f"{total.get('calories', 0)}kcal (P:{total.get('protein', '0g')} C:{total.get('carbs', '0g')} F:{total.get('fat', '0g')})", "style": "font-weight:bold"}
        ]})
        footer_text = ""
        if recommendation.get("tip"):
            footer_text = f"💡 {recommendation['tip']}"
        sections.append({
            "title": "🥗 午餐推荐配比",
            "type": "table",
            "rows": rows,
            "footer": {"text": footer_text}
        })

    # 3. 本周非正餐摄入（双人）
    for user in USERS:
        cats, total_cal = build_snack_stats(intake_log, week_dates, user)
        if cats:
            rows = []
            for cat_name, cat_data in cats.items():
                rows.append({"cells": [
                    {"text": cat_name, "style": "width:50px"},
                    {"text": "、".join(cat_data["items"])},
                    {"text": f"{cat_data['calories']}kcal"}
                ]})
            rows.append({"cells": [
                {"text": "合计", "style": "font-weight:bold"},
                {"text": ""},
                {"text": f"{total_cal}kcal", "style": "font-weight:bold"}
            ]})
            sections.append({
                "title": f"🍿 本周非正餐摄入 · {user}",
                "type": "table",
                "rows": rows
            })
        else:
            sections.append({
                "title": f"🍿 本周非正餐摄入 · {user}",
                "type": "text",
                "text": "暂无记录"
            })

    # 4. 营养健康推荐（双人）
    for user in USERS:
        advice = build_nutrition_advice(intake_log, week_dates, user)
        sections.append({
            "title": f"💊 营养健康推荐 · {user}",
            "type": "text",
            "text": advice
        })

    return sections


def generate():
    data = load_json(os.path.join(CARD_DIR, "data.json"))

    today_label, today_str, today_dt = get_today()
    plan = data.get("weekly_plan", {})
    recommendation = data.get("today_recommendation", {})
    intake_log = data.get("intake_log", {})
    today_intake, today_total = extract_intake(intake_log.get(today_str, {}))

    today_menu = plan.get(today_label, {}).get("lunch", {}).get("menu", {})

    summary = build_summary(today_label, recommendation, today_total)
    week_dates = get_week_dates(today_dt)

    sections = build_sections(today_label, today_menu, recommendation,
                              today_intake, today_total, intake_log, week_dates)

    display = {
        "summary": summary,
        "sections": sections,
    }
    save_json(os.path.join(CARD_DIR, "display.json"), display)
    print(f"✅ {summary[:60]}...")

    # 通知前端刷新
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://127.0.0.1:5050/v1/api/daily/notify-display-update",
            data=json.dumps({"card": "recipe"}).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer e0fb40cef753818c92577e3c8fe2af53"}
        )
        urllib.request.urlopen(req, timeout=3)
        print("  📡 已通知前端刷新")
    except Exception as e:
        print(f"  ⚠️ 通知前端失败: {e}")


if __name__ == "__main__":
    generate()
