#!/usr/bin/env python3
"""stock 股票卡片 display 生成器。

数据源：
  - A股/港股/指数/ETF: 新浪 hq.sinajs.cn 直连(GBK)，实时行情+(A股)买卖五档
  - 美股/加密: Yahoo Finance 走代理 172.29.4.175:22222 + 失败兜底
  - 历史K线: 新浪(A股日K) / Yahoo(美股·加密)

产出 display.json：
  - summary: 大盘+涨跌最大几只
  - sections:
      table     自选列表(市场/名/现价/涨跌%)
      chart_tabs 每个标的可切换 1D/1W/1M/3M，且 line/candlestick 双图(chartType)
      kv        选中标的详情(现价/涨跌/开高低/量/振幅...)
      indicators MA/RSI/MACD/布林带 + 文字状态
      ai        卡片喵 AI 点评(从 data.json.ai_comment 读)
指标自实现(pandas/numpy)，不依赖 pandas_ta。
"""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

CARD_DIR = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime.now(TZ)
TODAY_S = NOW.strftime("%Y-%m-%d")
TOKEN = "e0fb40cef753818c92577e3c8fe2af53"
PROXY = "http://172.29.4.175:22222"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# ---------------- IO ----------------
def load(name, default):
    p = os.path.join(CARD_DIR, name)
    if os.path.isfile(p) and os.path.getsize(p) > 0:
        try: return json.load(open(p, encoding="utf-8"))
        except Exception: return default
    return default

BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
}

def http_get(url, headers=None, use_proxy=False, timeout=20, binary=False):
    hdr = dict(BROWSER_HEADERS)
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, headers=hdr)
    if use_proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    else:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        raw = r.read()
    return raw if binary else raw.decode("utf-8", "replace")

# ================= 行情抓取（全部国内直连，零代理，零限流） =================
SINA_REF = {"Referer": "https://finance.sina.com.cn"}
TX_REF   = {"Referer": "https://gu.qq.com/"}

# ---------- 实时行情 ----------
def fetch_sina_realtime(codes):
    """新浪实时行情(GBK)。支持 A股/指数/ETF(shXXX/szXXX)、港股(hkXXXXX)、美股(gb_xxx)、加密(btc_btcbtcusd)。"""
    if not codes: return {}
    url = "https://hq.sinajs.cn/list=" + ",".join(codes)
    try:
        text = http_get(url, headers=SINA_REF, binary=True).decode("gbk", "replace")
    except Exception as e:
        print(f"  ⚠️ sina 实时抓取失败: {e}"); return {}
    out = {}
    for line in text.strip().split("\n"):
        if "=" not in line: continue
        code = line.split("=")[0].replace("var hq_str_", "").strip()
        val = line.split('"', 1)[1].rsplit('"', 1)[0] if '"' in line else ""
        f = val.split(",")
        if len(f) < 4: continue
        try:
            if code.startswith("hk"):
                name=f[1]; openp=float(f[2]); prev=float(f[3]); high=float(f[4]); low=float(f[5])
                now=float(f[6]); chg=float(f[7]); chgpct=float(f[8])
                out[code]={"name":name,"price":now,"open":openp,"prev":prev,"high":high,"low":low,
                           "change":round(chg,3),"change_pct":round(chgpct,2),"vol":None,
                           "amp":round((high-low)/prev*100,2) if prev else None,"l2":[]}
            elif code.startswith("gb_"):
                # 美股: name, price, chgpct, time, chg, openp?, prevclose, high, low, w52h, w52l, vol, ...
                name=f[0]; now=float(f[1]); chgpct=float(f[2]); chg=float(f[4])
                prev=float(f[26]) if len(f)>26 and f[26] else (now-chg)
                openp=float(f[5]) if f[5] else None; high=float(f[6]) if f[6] else None; low=float(f[7]) if f[7] else None
                w52h=float(f[8]) if len(f)>8 and f[8] else None; w52l=float(f[9]) if len(f)>9 and f[9] else None
                vol=float(f[10]) if len(f)>10 and f[10] else None
                out[code]={"name":name,"price":now,"open":openp,"prev":round(prev,3),"high":high,"low":low,
                           "change":round(chg,3),"change_pct":round(chgpct,2),"vol":vol,
                           "w52h":w52h,"w52l":w52l,"l2":[]}
            elif code.startswith("btc_"):
                # btc_btcbtcusd: time, ?, ?, now, ?, ?, high, low, prevclose?, name, ...
                now=float(f[3]) or float(f[5]); high=float(f[6]); low=float(f[7]); prev=float(f[8])
                name=f[9] if len(f)>9 else "比特币"
                chg=now-prev; chgpct=(chg/prev*100) if prev else 0.0
                out[code]={"name":name,"price":now,"open":None,"prev":prev,"high":high,"low":low,
                           "change":round(chg,2),"change_pct":round(chgpct,2),"vol":None,
                           "amp":round((high-low)/prev*100,2) if prev else None,"l2":[]}
            else:
                # A股/指数/ETF
                name=f[0]; openp=float(f[1]); prev=float(f[2]); now=float(f[3]); high=float(f[4]); low=float(f[5])
                vol=float(f[8]) if len(f)>8 and f[8] else None
                chg=now-prev; chgpct=(chg/prev*100) if prev else 0.0
                l2=[]
                try:
                    for i in range(5):
                        bp=f[11+i*2]; bvol=f[10+i*2]
                        if bp and float(bp)>0: l2.append(("买"+str(i+1), bp, bvol))
                    for i in range(5):
                        ap=f[21+i*2]; avol=f[20+i*2]
                        if ap and float(ap)>0: l2.append(("卖"+str(i+1), ap, avol))
                except Exception: pass
                out[code]={"name":name,"price":now,"open":openp,"prev":prev,"high":high,"low":low,
                           "change":round(chg,3),"change_pct":round(chgpct,2),"vol":vol,
                           "amp":round((high-low)/prev*100,2) if prev else None,"l2":l2}
        except Exception as e:
            print(f"  ⚠️ 解析实时 {code} 失败: {e}")
    return out

def fetch_tx_realtime(tx_code):
    """腾讯实时行情(qt.gtimg.cn)，用于美股 usAAPL 等。返回单条 dict 或 None。"""
    try:
        text = http_get(f"https://qt.gtimg.cn/q={tx_code}", binary=True).decode("gbk","replace")
        val = text.split('"',1)[1].rsplit('"',1)[0]
        f = val.split("~")
        if len(f) < 6: return None
        name=f[1]; now=float(f[3]); prev=float(f[4]); openp=float(f[5])
        chg=float(f[31]) if len(f)>31 and f[31] else now-prev
        chgpct=float(f[32]) if len(f)>32 and f[32] else (chg/prev*100 if prev else 0)
        high=float(f[33]) if len(f)>33 and f[33] else None
        low=float(f[34]) if len(f)>34 and f[34] else None
        return {"name":name,"price":now,"open":openp,"prev":prev,"high":high,"low":low,
                "change":round(chg,3),"change_pct":round(chgpct,2),"vol":None,"l2":[]}
    except Exception as e:
        print(f"  ⚠️ 腾讯实时 {tx_code} 失败: {e}"); return None

# ---------- 历史日K（全部国内直连） ----------
def _sina_jsonp_arr(url):
    """新浪 jsonp 接口取数组。"""
    import re
    raw = http_get(url, headers=SINA_REF)
    m = re.search(r'(\[.*\])', raw, re.S)
    return json.loads(m.group(1)) if m else []

def fetch_kline_ashare(code, datalen=130):
    """A股/指数/ETF 日K：新浪 getKLineData。code=shXXXXXX。"""
    url=(f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
         f"?symbol={code}&scale=240&ma=no&datalen={datalen}")
    try:
        arr=json.loads(http_get(url, headers=SINA_REF))
        return [{"date":it["day"][:10],"o":float(it["open"]),"h":float(it["high"]),
                 "l":float(it["low"]),"c":float(it["close"]),"vol":float(it.get("volume",0) or 0)} for it in arr]
    except Exception as e:
        print(f"  ⚠️ A股K线 {code} 失败: {e}"); return []

def fetch_kline_us(sym, n=130):
    """美股日K：新浪 US_MinKService.getDailyK (40年历史)。"""
    url=f"https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var=/US_MinKService.getDailyK?symbol={sym}&___qn=3"
    try:
        arr=_sina_jsonp_arr(url)
        out=[{"date":it["d"][:10],"o":float(it["o"]),"h":float(it["h"]),
              "l":float(it["l"]),"c":float(it["c"]),"vol":float(it.get("v",0) or 0)} for it in arr]
        return out[-n:]
    except Exception as e:
        print(f"  ⚠️ 美股K线 {sym} 失败: {e}"); return []

def fetch_kline_hk(code, n=130):
    """港股日K：腾讯 fqkline。code=hk00700。返回 [[date,open,close,high,low,vol],...]。"""
    num = code.replace("hk","")
    url=f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=hk{num},day,,,{n},qfq"
    try:
        d=json.loads(http_get(url, headers=TX_REF))
        rows=d["data"][f"hk{num}"].get("qfqday") or d["data"][f"hk{num}"].get("day") or []
        return [{"date":r[0],"o":float(r[1]),"c":float(r[2]),"h":float(r[3]),"l":float(r[4]),
                 "vol":float(r[5]) if len(r)>5 else 0} for r in rows]
    except Exception as e:
        print(f"  ⚠️ 港股K线 {code} 失败: {e}"); return []

def fetch_kline_crypto(sym, n=130):
    """加密日K：新浪 GlobalFuturesService。sym=BTC。"""
    url=f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol={sym}"
    try:
        arr=_sina_jsonp_arr(url)
        out=[{"date":it["date"][:10],"o":float(it["open"]),"h":float(it["high"]),
              "l":float(it["low"]),"c":float(it["close"]),"vol":float(it.get("volume",0) or 0)} for it in arr]
        return out[-n:]
    except Exception as e:
        print(f"  ⚠️ 加密K线 {sym} 失败: {e}"); return []


def fetch_minute_tx(tx_code):
    """腾讯当日分时(web.ifzq.gtimg.cn/minute)。tx_code: A股 shXXXXXX / 港股 hkXXXXX / 美股 usSYM。
    返回 [{date:'YYYY-MM-DD HH:MM', o,h,l,c, vol}]，分时每点价格作 OHLC(蜡烛退化为点，折线正常)。
    加密(新浪 btc_ 代码)腾讯不支持 → 返回 []。"""
    url=f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={tx_code}"
    try:
        d=json.loads(http_get(url, headers=TX_REF))
        node=d.get("data",{}).get(tx_code,{}).get("data",{})
        rows=node.get("data") or []
        day=node.get("date") or NOW.strftime("%Y%m%d")
        day_fmt=f"{day[:4]}-{day[4:6]}-{day[6:8]}"
        out=[]
        for r in rows:
            parts=r.split()
            if len(parts)<2: continue
            hhmm=parts[0]; price=float(parts[1])
            vol=float(parts[2]) if len(parts)>2 and parts[2] else 0
            ts=f"{day_fmt} {hhmm[:2]}:{hhmm[2:]}"
            out.append({"date":ts,"o":price,"h":price,"l":price,"c":price,"vol":vol})
        return out
    except Exception as e:
        print(f"  ⚠️ 分时 {tx_code} 失败: {e}"); return []


# ---------------- 技术指标(自实现) ----------------
def _ma(closes, n):
    out=[None]*len(closes)
    for i in range(len(closes)):
        if i>=n-1: out[i]=round(sum(closes[i-n+1:i+1])/n,3)
    return out

def _ema(vals, n):
    out=[None]*len(vals); k=2/(n+1); prev=None
    for i,v in enumerate(vals):
        prev = v if prev is None else v*k+prev*(1-k)
        out[i]=prev
    return out

def _rsi(closes, n=14):
    out=[None]*len(closes)
    if len(closes)<=n: return out
    gains=losses=0.0
    for i in range(1,n+1):
        d=closes[i]-closes[i-1]; gains+=max(d,0); losses+=max(-d,0)
    ag=gains/n; al=losses/n
    out[n]=round(100-100/(1+(ag/al if al else 999)),2)
    for i in range(n+1,len(closes)):
        d=closes[i]-closes[i-1]
        ag=(ag*(n-1)+max(d,0))/n; al=(al*(n-1)+max(-d,0))/n
        out[i]=round(100-100/(1+(ag/al if al else 999)),2)
    return out

def _macd(closes):
    e12=_ema(closes,12); e26=_ema(closes,26)
    dif=[round(e12[i]-e26[i],4) for i in range(len(closes))]
    dea=_ema(dif,9)
    hist=[round((dif[i]-dea[i])*2,4) for i in range(len(closes))]
    return dif,[round(x,4) for x in dea],hist

def _boll(closes,n=20,k=2):
    import math
    mid=_ma(closes,n); up=[None]*len(closes); lo=[None]*len(closes)
    for i in range(len(closes)):
        if i>=n-1:
            seg=closes[i-n+1:i+1]; m=mid[i]
            sd=math.sqrt(sum((x-m)**2 for x in seg)/n)
            up[i]=round(m+k*sd,3); lo[i]=round(m-k*sd,3)
    return up,mid,lo

def compute_indicators(kline):
    closes=[p["c"] for p in kline]
    if len(closes)<5: return {}
    ma5=_ma(closes,5); ma10=_ma(closes,10); ma20=_ma(closes,20); ma60=_ma(closes,60)
    rsi=_rsi(closes,14); dif,dea,hist=_macd(closes); bu,bm,bl=_boll(closes,20,2)
    last=-1
    def g(a): return a[last] if a and a[last] is not None else None
    return {
        "ma":{"MA5":g(ma5),"MA10":g(ma10),"MA20":g(ma20),"MA60":g(ma60)},
        "rsi":g(rsi),
        "macd":{"DIF":g(dif),"DEA":g(dea),"HIST":g(hist)},
        "boll":{"UP":g(bu),"MID":g(bm),"LOW":g(bl)},
        "series":{"ma5":ma5,"ma20":ma20}  # 给折线叠加用
    }

def indicator_text(ind, price):
    """把指标翻译成大白话状态(规则层，AI点评由卡片喵另出)"""
    notes=[]
    rsi=ind.get("rsi")
    if rsi is not None:
        if rsi>=70: notes.append(f"RSI {rsi} 超买⚠️")
        elif rsi<=30: notes.append(f"RSI {rsi} 超卖")
        else: notes.append(f"RSI {rsi} 中性")
    macd=ind.get("macd",{})
    if macd.get("HIST") is not None:
        notes.append("MACD 多头" if macd["HIST"]>0 else "MACD 空头")
    ma=ind.get("ma",{})
    if price is not None and ma.get("MA20"):
        notes.append("站上20日线" if price>=ma["MA20"] else "跌破20日线")
    boll=ind.get("boll",{})
    if price is not None and boll.get("UP") and boll.get("LOW"):
        if price>=boll["UP"]: notes.append("触布林上轨")
        elif price<=boll["LOW"]: notes.append("触布林下轨")
    return " · ".join(notes)

# ---------------- 主流程 ----------------
# 为省 Yahoo 请求(防429)：每标的只打 2 次——日线6mo(切1W/1M/3M) + 日内5d/5m(当1D)
PERIODS = ["1D", "1W", "1M", "3M"]
SLICE = {"1W": 5, "1M": 22, "3M": 66}  # 从日线尾部切的交易日数

def fetch_kline_bundle(w):
    """按 mkt 路由日K，全部国内直连。返回 {1D,1W,1M,3M}。
    1D = 腾讯当日分时(ashare/hk/us)；crypto 无免费分时，1D 退化为最近日K单点。"""
    code=w["code"]; mkt=w.get("mkt"); sym=w.get("sym")
    if mkt=="ashare":   daily=fetch_kline_ashare(code,130)
    elif mkt=="hk":     daily=fetch_kline_hk(code,130)
    elif mkt=="us":     daily=fetch_kline_us(sym or code.replace("us_",""),130)
    elif mkt=="crypto": daily=fetch_kline_crypto(sym or "BTC",130)
    else:               daily=[]
    # 1D 分时：腾讯 minute（A股/港股/美股）。腾讯代码：A股=code, 港股=code, 美股=us+sym
    minute=[]
    if mkt=="ashare":   minute=fetch_minute_tx(code)
    elif mkt=="hk":     minute=fetch_minute_tx(code)
    elif mkt=="us":     minute=fetch_minute_tx("us"+(sym or code.replace("us_","")))
    per={"1D": minute if minute else (daily[-1:] if daily else [])}
    for label,n in SLICE.items():
        per[label]=daily[-n:] if daily else []
    return per

def main():
    data = load("data.json", {})
    watchlist = data.get("watchlist", [])
    ai_comment = data.get("ai_comment", {})
    cached_quotes = data.get("quotes", {})

    # ---- 实时行情(全部国内直连) ----
    quotes={}
    # 新浪一把抓: A股/港股/指数/ETF/加密(都用各自 code)；美股单独用腾讯
    sina_codes=[]
    for w in watchlist:
        mkt=w.get("mkt")
        if mkt in ("ashare","hk","crypto"):
            sina_codes.append(w["code"])
    if sina_codes:
        quotes.update(fetch_sina_realtime(sina_codes))
    # 美股走腾讯 usSYM
    for w in watchlist:
        if w.get("mkt")=="us":
            q=fetch_tx_realtime("us"+(w.get("sym") or w["code"].replace("us_","")))
            if not q and cached_quotes.get(w["code"]):
                q=dict(cached_quotes[w["code"]]); q["_stale"]=True
                print(f"  · {w['name']} quote 用缓存兜底", flush=True)
            if q: quotes[w["code"]]=q
    # 统一覆盖中文名
    for w in watchlist:
        if w["code"] in quotes: quotes[w["code"]]["name"]=w["name"]

    # 自选列表
    rows=[]
    for w in watchlist:
        q=quotes.get(w["code"],{})
        price=q.get("price"); pct=q.get("change_pct")
        color="#ef4444" if (pct or 0)>0 else ("#22c55e" if (pct or 0)<0 else "#888")
        arrow="▲" if (pct or 0)>0 else ("▼" if (pct or 0)<0 else "—")
        rows.append({"cells":[
            {"text":w["market"]},
            {"text":w["name"]},
            {"text":(f"{price}" if price is not None else "—")},
            {"text":(f"{arrow}{abs(pct):.2f}%" if pct is not None else "—"),"color":color}
        ]})

    # K线 + 指标(每个标的，多周期) — A股走新浪(无限流)，港美加密走Yahoo
    # 缓存策略: K线一天抓一次(写回 _date)；当天已抓则复用
    force = "--refresh-kline" in sys.argv
    klines_cache = data.get("klines", {})
    klines={}; indicators={}; details={}
    for w in watchlist:
        code=w["code"]; ysym=w.get("yahoo_sym", code)
        cached = klines_cache.get(code, {})
        if (not force) and cached.get("_date")==TODAY_S and cached.get("3M"):
            perranges={k:cached[k] for k in PERIODS if k in cached}
            # 1D 分时盘中实时变化：缓存命中也重抓分时(单请求,便宜)，日K仍复用
            mkt=w.get("mkt"); sym=w.get("sym")
            if mkt=="ashare":   _m=fetch_minute_tx(code)
            elif mkt=="hk":     _m=fetch_minute_tx(code)
            elif mkt=="us":     _m=fetch_minute_tx("us"+(sym or code.replace("us_","")))
            else:               _m=[]
            if _m:
                perranges["1D"]=_m
                klines_cache[code]["1D"]=_m  # 同步缓存
            print(f"  · {w['name']}({code}) 用今日K线缓存(1D分时已刷新 {len(perranges.get('1D',[]))}点)", flush=True)
        else:
            perranges=fetch_kline_bundle(w)  # 按 source 路由
            got = sum(1 for v in perranges.values() if v)
            print(f"  · {w['name']}({code}) K线周期到位 {got}/4", flush=True)
            if got>0:
                klines_cache[code]={**perranges, "_date":TODAY_S}  # 写回缓存
            else:
                # 抓失败则沿用旧缓存(不丢历史)
                perranges={k:cached[k] for k in PERIODS if k in cached}
        klines[code]=perranges
        # 指标用最长周期(3M)算
        base=perranges.get("3M") or perranges.get("1M") or []
        ind=compute_indicators(base) if base else {}
        indicators[code]=ind
        q=quotes.get(code,{})
        details[code]={"quote":q,"ind_text":indicator_text(ind,q.get("price")) if ind else ""}

    # 写回 data.json(持久化 K线缓存 + 最新行情)
    data["klines"]=klines_cache
    data["quotes"]={c:quotes[c] for c in quotes}
    data["_last_run"]=NOW.isoformat()
    try:
        json.dump(data, open(os.path.join(CARD_DIR,"data.json"),"w"), ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  (data.json 写回失败:{e})")

    # summary：上证 + 涨跌幅最大一只
    summ=[]
    idx=quotes.get("sh000001")
    if idx and idx.get("change_pct") is not None:
        summ.append(f"📈 上证 {idx['price']}({idx['change_pct']:+.2f}%)")
    valid=[(w,quotes.get(w['code'],{})) for w in watchlist]
    valid=[(w,q) for w,q in valid if q.get("change_pct") is not None and w['code']!='sh000001']
    if valid:
        top=max(valid,key=lambda x:abs(x[1]['change_pct']))
        summ.append(f"{top[0]['name']} {top[1].get('price')}({top[1]['change_pct']:+.2f}%)")
    summary=" | ".join(summ) if summ else "📊 行情加载中"

    # sections
    sections=[]
    sections.append({"type":"table","title":"⭐ 自选股",
        "header":[{"text":"市场"},{"text":"名称"},{"text":"现价"},{"text":"涨跌"}],
        "rows":rows})

    # 每个标的：图(双图+周期) + 详情 + 指标 + AI
    for w in watchlist:
        code=w["code"]; per=klines.get(code,{}); ind=indicators.get(code,{}); det=details.get(code,{})
        # 折线序列(收盘) + 蜡烛序列(ohlc)，按周期
        line_charts={}; candle_charts={}
        for label,k in per.items():
            def _dlabel(dt):
                # 分时 "YYYY-MM-DD HH:MM" → "HH:MM"；日K "YYYY-MM-DD" → "MM-DD"
                return dt[11:] if (" " in dt and len(dt)>=16) else dt[5:]
            line_charts[label]=[{"date":_dlabel(p["date"]),"value":p["c"]} for p in k]
            candle_charts[label]=[{"x":p["date"],"o":p["o"],"h":p["h"],"l":p["l"],"c":p["c"]} for p in k]
        q=det.get("quote",{})
        sub=[]
        # 双图卡：可切 折线/蜡烛 + 周期。只暴露有≥2个点的周期(1D=腾讯分时;crypto无分时则1D单点被剔除)
        avail_periods=[p for p in PERIODS if len(candle_charts.get(p,[]))>=2]
        defp = "1M" if "1M" in avail_periods else (avail_periods[-1] if avail_periods else "3M")
        sub.append({"type":"stock_chart","title":f"{w['name']} ({code})",
            "periods":avail_periods or PERIODS,"default_period":defp,
            "line":line_charts,"candle":candle_charts})
        # 详情 kv
        pairs=[]
        if q.get("price") is not None: pairs.append({"key":"现价","value":str(q['price'])})
        if q.get("change_pct") is not None: pairs.append({"key":"涨跌幅","value":f"{q['change_pct']:+.2f}%"})
        if q.get("open") is not None: pairs.append({"key":"今开","value":str(q['open'])})
        if q.get("high") is not None: pairs.append({"key":"最高","value":str(q['high'])})
        if q.get("low") is not None: pairs.append({"key":"最低","value":str(q['low'])})
        if q.get("amp") is not None: pairs.append({"key":"振幅","value":f"{q['amp']}%"})
        if q.get("vol") is not None: pairs.append({"key":"成交量","value":str(q['vol'])})
        if q.get("w52h"): pairs.append({"key":"52周高","value":str(q['w52h'])})
        if q.get("w52l"): pairs.append({"key":"52周低","value":str(q['w52l'])})
        sub.append({"type":"kv","title":"📋 详情","pairs":pairs})
        # 指标 kv
        if ind:
            ip=[]
            ma=ind.get("ma",{})
            for kk in ("MA5","MA10","MA20","MA60"):
                if ma.get(kk) is not None: ip.append({"key":kk,"value":str(ma[kk])})
            if ind.get("rsi") is not None: ip.append({"key":"RSI(14)","value":str(ind['rsi'])})
            m=ind.get("macd",{})
            if m.get("DIF") is not None: ip.append({"key":"MACD","value":f"DIF {m['DIF']} / DEA {m['DEA']} / 柱 {m['HIST']}"})
            b=ind.get("boll",{})
            if b.get("UP") is not None: ip.append({"key":"布林带","value":f"上 {b['UP']} / 中 {b['MID']} / 下 {b['LOW']}"})
            sub.append({"type":"kv","title":"📊 技术指标","pairs":ip,"footer":det.get("ind_text","")})
        # AI 点评
        ai=ai_comment.get(code)
        if ai and ai.get("text"):
            sub.append({"type":"note","title":"🤖 卡片喵点评","text":ai["text"]})
        sections.append({"type":"stock_detail","title":w["name"],"code":code,
            "market":w["market"],"sub":sub})

    display={
        "summary":summary,
        "sections":sections,
        "generated_date":TODAY_S,
        "generated":NOW.isoformat()
    }
    json.dump(display, open(os.path.join(CARD_DIR,"display.json"),"w"), ensure_ascii=False, indent=2)
    print(f"✅ stock display: {summary}")

    if "--no-notify" not in sys.argv:
        try:
            req=urllib.request.Request("http://127.0.0.1:5050/v1/api/daily/notify-display-update",
                data=json.dumps({"card":"stock"}).encode(),
                headers={"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json"})
            urllib.request.urlopen(req,timeout=5); print("  📡 已通知前端")
        except Exception as e: print(f"  (通知跳过:{e})")

if __name__=="__main__":
    main()
