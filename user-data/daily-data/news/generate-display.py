#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新闻卡片 display 生成器 — ac-news-card-design-V1.0
读 data.json → 折叠态摘要(Top要闻+天气) + 展开态(精选Top12 + 按来源分块) → display.json
每条 item 带 url，前端渲染为可点链接。
"""
import json, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo

CARD_DIR=os.path.dirname(os.path.abspath(__file__))
TZ=ZoneInfo("Asia/Shanghai")
TOKEN="e0fb40cef753818c92577e3c8fe2af53"
TOP_N=12

def load(name,default):
    p=os.path.join(CARD_DIR,name)
    if os.path.isfile(p) and os.path.getsize(p)>0:
        try: return json.load(open(p,encoding="utf-8"))
        except Exception: return default
    return default

def main():
    data=load("data.json",{})
    items=data.get("items",[]); by_source=data.get("by_source",{})
    total=data.get("total",len(items)); weather=data.get("weather",""); weather_alerts=data.get("weather_alerts",[])
    updated=data.get("updated","")
    try: hhmm=datetime.fromisoformat(updated).astimezone(TZ).strftime("%H:%M") if updated else ""
    except Exception: hhmm=""

    # 折叠态摘要：精简——只留头条1条(截短) + 计数/时间/天气
    head=items[0]["title"] if items else ""
    if len(head)>22: head=head[:22]+"…"
    parts=["🔥 共%d条"%total]
    if head: parts.append(head)
    tail2=[]
    if hhmm: tail2.append(hhmm)
    if weather: tail2.append("🌦️杭州"+weather)
    sm=" ｜ ".join(parts)
    if tail2: sm+="  ("+"·".join(tail2)+")"
    # 天气提醒(下雨/高温等)放 summary 末尾, 最显眼
    if weather_alerts:
        sm+="  "+weather_alerts[0]

    sections=[]
    # 精选 Top12
    sel=[]
    for it in items[:TOP_N]:
        mark="·%d源"%it["source_count"] if it.get("source_count",1)>1 else ""
        sel.append({"text":"%s 〔%s%s〕"%(it["title"], it["source"], mark), "url":it["url"]})
    if sel:
        sections.append({"title":"🔥 精选要闻","type":"list","items":sel})

    # 按来源分块(全部) —— 形态①多源并排矩阵(source_matrix)
    ch_order={"经济财经":0,"国内时事":1,"国内热点":2,"国内热议":3,"综合":4,"国际政治":5,"国际":6,"杭州本地":7}
    src_ch={}
    for it in items:
        src_ch.setdefault(it["source"], it["channel"])
    ordered=sorted(by_source.keys(), key=lambda s: ch_order.get(src_ch.get(s,""),9))
    columns_m=[]
    for src in ordered:
        lst=by_source.get(src,[])
        if not lst: continue
        columns_m.append({"source":src,"channel":src_ch.get(src,""),
                          "items":[{"text":x["title"],"url":x["url"]} for x in lst]})
    if columns_m:
        sections.append({"title":"📰 全部来源","type":"source_matrix","columns":columns_m})

    # 天气提醒块(下雨/高温/降温等需关注信息)
    if weather_alerts or weather:
        wlines=list(weather_alerts)
        if weather: wlines.append("当前：%s"%weather)
        sections.insert(0, {"title":"🌦️ 杭州天气提醒","type":"list",
                            "items":[{"text":x} for x in wlines]})

    display={"summary":sm,"sections":sections,
             "generated":datetime.now(TZ).isoformat(),"total":total}
    json.dump(display, open(os.path.join(CARD_DIR,"display.json"),"w"), ensure_ascii=False, indent=2)
    print("✅ news display 生成: %d sections, total=%d"%(len(sections),total))

    if "--no-notify" not in sys.argv:
        try:
            import urllib.request
            req=urllib.request.Request("http://127.0.0.1:5050/v1/api/daily/notify-display-update",
                data=json.dumps({"card":"news"}).encode(),
                headers={"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"})
            urllib.request.urlopen(req,timeout=5); print("  📡 已通知前端")
        except Exception as e: print("  (通知跳过: %s)"%e)

if __name__=="__main__":
    main()
