#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新闻卡片爬虫 — ac-news-card-design-V1.0
抓 16 源(国内直连 + 国际走代理失败兜底) → 归一化 → 跨源去重聚合 → 兴趣/热度打分 → 写 data.json → 跑 generate-display.py
"""
import json, os, re, sys, time, urllib.request, urllib.error, ssl, subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

CARD_DIR = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime.now(TZ)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
SSL_CTX = ssl.create_default_context(); SSL_CTX.check_hostname=False; SSL_CTX.verify_mode=ssl.CERT_NONE

def load_json(name, default):
    p = os.path.join(CARD_DIR, name)
    if os.path.isfile(p) and os.path.getsize(p) > 0:
        try: return json.load(open(p, encoding="utf-8"))
        except Exception: return default
    return default

def fetch(url, proxy=None, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://finance.eastmoney.com/"})
    if proxy:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                                         urllib.request.HTTPSHandler(context=SSL_CTX))
    else:
        op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=SSL_CTX))
    with op.open(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")

# ---------- 各源解析器: 返回 [{title,url,summary}] ----------
def p_sina_roll(txt):
    d = json.loads(txt); out=[]
    for it in d.get("result",{}).get("data",[]):
        t=it.get("title","").strip(); u=it.get("url","").strip()
        if t and u: out.append({"title":t,"url":u,"summary":it.get("intro","")})
    return out

def p_eastmoney(txt):
    d=json.loads(txt); out=[]
    for it in d.get("data",{}).get("list",[]):
        t=(it.get("title") or it.get("Art_Title") or "").strip()
        u=(it.get("url_w") or it.get("Art_Url") or "").strip()
        if not u and it.get("code"): u="https://finance.eastmoney.com/a/%s.html"%it.get("code")
        if t and u: out.append({"title":t,"url":u,"summary":it.get("summary","")})
    return out

def p_baidu_hot(txt):
    d=json.loads(txt); out=[]
    for card in d.get("data",{}).get("cards",[]):
        for blk in card.get("content",[]):
            # 百度榜单在嵌套 content[].content[]，也兼容平铺
            rows = blk.get("content") if isinstance(blk.get("content"), list) else [blk]
            for it in rows:
                t=(it.get("word") or it.get("query") or "").strip(); u=it.get("url","").strip()
                if t and u: out.append({"title":t,"url":u,"summary":it.get("desc","")})
    return out

def p_toutiao_hot(txt):
    d=json.loads(txt); out=[]
    for it in d.get("data",[]):
        t=it.get("Title","").strip(); u=it.get("Url","").strip()
        if t and u: out.append({"title":t,"url":u,"summary":""})
    return out

def p_zhihu_hot(txt):
    d=json.loads(txt); out=[]
    for it in d.get("data",[]):
        tg=it.get("target",{}); t=(tg.get("title") or "").strip()
        tid=tg.get("id"); u="https://www.zhihu.com/question/%s"%tid if tid else ""
        if t and u: out.append({"title":t,"url":u,"summary":(tg.get("excerpt") or "")})
    return out

def p_bili_hot(txt):
    d=json.loads(txt); out=[]
    for it in d.get("data",{}).get("list",[]):
        t=it.get("title","").strip(); u=it.get("short_link_v2") or ("https://www.bilibili.com/video/%s"%it.get("bvid",""))
        if t and u: out.append({"title":t,"url":u,"summary":(it.get("desc") or "")[:80]})
    return out

_WX_ZH={"Sunny":"晴","Clear":"晴","Partly cloudy":"多云","Cloudy":"阴","Overcast":"阴",
  "Mist":"薄雾","Fog":"雾","Smoky haze":"霾","Haze":"霾","Patchy rain possible":"局部小雨",
  "Patchy rain nearby":"局部小雨","Light rain":"小雨","Moderate rain":"中雨","Heavy rain":"大雨",
  "Light rain shower":"阵雨","Thundery outbreaks possible":"可能雷阵雨","Patchy light rain":"零星小雨",
  "Light drizzle":"毛毛雨","Rain":"雨","Light snow":"小雪"}
def _wx(en): return _WX_ZH.get(en, en)
def p_wttr(txt):
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI
    d=json.loads(txt)
    cc=(d.get("current_condition") or [{}])[0]
    cur_desc=_wx(cc.get("weatherDesc",[{}])[0].get("value",""))
    cur_temp=cc.get("temp_C","")
    days=d.get("weather",[])
    alerts=[]
    now=_dt.now(_ZI("Asia/Shanghai")); cur_h=now.hour
    # 1) 今天剩余时段: 降雨提醒(每3小时档)
    if days:
        rain_hours=[]
        for h in days[0].get("hourly",[]):
            hr=int(h.get("time","0"))//100
            if hr<cur_h: continue
            cor=int(h.get("chanceofrain","0") or 0)
            wd=h.get("weatherDesc",[{}])[0].get("value","")
            if cor>=50 or ("rain" in wd.lower() and cor>=30) or "thunder" in wd.lower():
                rain_hours.append((hr,cor,_wx(wd)))
        if rain_hours:
            hr,cor,wd=rain_hours[0]
            alerts.append("🌧️ 约%d点%s(降雨%d%%)，记得带伞"%(hr,wd,cor))
    # 2) 明天: 高温/降温/低温提醒
    if len(days)>=2:
        td=days[0]; tm=days[1]
        try:
            t_max=int(td.get("maxtempC","0")); m_max=int(tm.get("maxtempC","0")); m_min=int(tm.get("mintempC","0"))
            if m_max>=35: alerts.append("🥵 明天高温%d°C，注意防暑"%m_max)
            elif m_max-t_max>=5: alerts.append("📈 明天升温至%d°C"%m_max)
            elif t_max-m_max>=5: alerts.append("📉 明天降温至%d°C(最低%d°C)，添衣"%(m_max,m_min))
            if m_min<=5: alerts.append("🥶 明天最低仅%d°C"%m_min)
            # 明天降雨
            tmr_rain=max((int(h.get("chanceofrain","0") or 0) for h in tm.get("hourly",[])), default=0)
            if tmr_rain>=60: alerts.append("☔ 明天有雨(概率%d%%)"%tmr_rain)
        except Exception: pass
    cur="%s%s°C"%(cur_desc, cur_temp) if cur_temp else ""
    return {"weather": cur, "weather_alerts": alerts}

def p_rss(txt):
    out=[]
    try:
        txt=re.sub(r'<\?xml[^>]*\?>','',txt).strip()
        root=ET.fromstring(txt)
    except Exception:
        # rdf/namespace 容错: 提取 item
        items=re.findall(r'<item[ >].*?</item>', txt, re.S)
        for raw in items:
            mt=re.search(r'<title[^>]*>(.*?)</title>', raw, re.S)
            ml=re.search(r'<link[^>]*>(.*?)</link>', raw, re.S)
            if mt and ml:
                t=re.sub(r'<!\[CDATA\[|\]\]>','',mt.group(1)).strip()
                u=re.sub(r'<!\[CDATA\[|\]\]>','',ml.group(1)).strip()
                if t and u: out.append({"title":t,"url":u,"summary":""})
        return out
    for item in root.iter():
        tag=item.tag.split('}')[-1]
        if tag in ("item","entry"):
            t=u=""; 
            for ch in item:
                ct=ch.tag.split('}')[-1]
                if ct=="title" and ch.text: t=ch.text.strip()
                elif ct=="link":
                    u=(ch.text or ch.get("href") or "").strip()
            if t and u: out.append({"title":t,"url":u,"summary":""})
    return out

PARSERS={"sina_roll":p_sina_roll,"eastmoney":p_eastmoney,"baidu_hot":p_baidu_hot,
         "toutiao_hot":p_toutiao_hot,"zhihu_hot":p_zhihu_hot,"bili_hot":p_bili_hot,
         "rss":p_rss,"wttr":p_wttr}

# ---------- 翻译(方案A: Google免费端点, 走代理, 带缓存) ----------
import urllib.parse
TRANS_CACHE_PATH=os.path.join(CARD_DIR,"trans_cache.json")
def load_trans_cache():
    try: return json.load(open(TRANS_CACHE_PATH,encoding="utf-8"))
    except Exception: return {}
def save_trans_cache(c):
    try: json.dump(c,open(TRANS_CACHE_PATH,"w"),ensure_ascii=False)
    except Exception: pass

def translate_one(text, proxy, timeout=8):
    """英/日 → 中文。失败返回原文。"""
    if not text: return text
    q=urllib.parse.quote(text)
    url="https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q="+q
    try:
        txt=fetch(url, proxy=proxy, timeout=timeout)
        arr=json.loads(txt)
        out="".join(seg[0] for seg in arr[0] if seg and seg[0])
        return out.strip() or text
    except Exception:
        return text

def translate_items(items, proxy, cache):
    """对一批 items 的 title 翻译(用缓存避免重复)。原标题存 title_orig。"""
    for it in items:
        t=it["title"]
        if t in cache:
            it["title_orig"]=t; it["title"]=cache[t]; continue
        zh=translate_one(t, proxy)
        if zh and zh!=t:
            cache[t]=zh; it["title_orig"]=t; it["title"]=zh
    return items

# ---------- 去重 + 打分 ----------
def norm_title(t):
    return re.sub(r'[\s\W_【】\[\]丨|：:，,。.、!！?？]+','', t).lower()

def main():
    cfg=load_json("sources.json",{}); prompt=load_json("prompt.json",{})
    proxy=cfg.get("proxy"); timeout=cfg.get("timeout",8); limit=cfg.get("per_source_limit",15)
    kw_map=prompt.get("interest_keywords",{})
    all_kw=[(w,ch) for ch,ws in kw_map.items() for w in ws]

    _trans_cache=load_trans_cache()
    raw_items=[]; by_source={}; weather=""; weather_alerts=[]; ok_src=0; fail_src=[]
    for s in cfg.get("sources",[]):
        if not s.get("enabled"): continue
        try:
            txt=fetch(s["url"], proxy=(proxy if s["net"]=="proxy" else None), timeout=timeout)
            parser=PARSERS.get(s["kind"])
            if s["kind"]=="wttr":
                w=parser(txt); weather=w.get("weather",""); weather_alerts=w.get("weather_alerts",[]); ok_src+=1; continue
            items=parser(txt)[:limit]
            if items:
                ok_src+=1
                if s.get("translate"):
                    items=translate_items(items, proxy, _trans_cache)
                by_source[s["name"]]=[{"title":it["title"],"url":it["url"],"channel":s["channel"],"title_orig":it.get("title_orig","")} for it in items]
                for it in items:
                    raw_items.append({**it,"source":s["name"],"channel":s["channel"]})
        except Exception as e:
            fail_src.append("%s(%s)"%(s["name"], str(e)[:40]))
    # 跨源去重聚合
    merged={}
    for it in raw_items:
        k=norm_title(it["title"])[:40]
        if not k: continue
        if k in merged:
            merged[k]["source_count"]+=1
            if it["source"] not in merged[k]["_srcs"]: merged[k]["_srcs"].append(it["source"])
        else:
            merged[k]={"title":it["title"],"url":it["url"],"source":it["source"],
                       "channel":it["channel"],"source_count":1,"_srcs":[it["source"]]}
    # 打分
    items=[]
    for m in merged.values():
        score=m["source_count"]*10.0
        hits=[]; t=m["title"]
        for w,ch in all_kw:
            if w in t and w not in hits:
                hits.append(w); score+=6.0
        if m["channel"] in ("国际政治","经济财经"): score+=4.0
        if m["channel"] in ("国内时事","国内政治"): score+=2.0
        m["score"]=round(score,1); m["hit_keywords"]=hits
        del m["_srcs"]
        items.append(m)
    items.sort(key=lambda x:(-x["score"], -x["source_count"]))

    data={"date":NOW.strftime("%Y-%m-%d"),"updated":NOW.isoformat(),
          "total":len(items),"weather":weather,"weather_alerts":weather_alerts,"items":items,"by_source":by_source}
    save_trans_cache(_trans_cache)
    json.dump(data, open(os.path.join(CARD_DIR,"data.json"),"w"), ensure_ascii=False, indent=2)
    print(json.dumps({"count":len(items),"sources":ok_src,"failed":fail_src,"date":data["date"]}, ensure_ascii=False))

    # 跑 generate-display
    if "--no-display" not in sys.argv:
        gd=os.path.join(CARD_DIR,"generate-display.py")
        if os.path.isfile(gd):
            subprocess.run(["python3",gd], timeout=20)

if __name__=="__main__":
    main()
