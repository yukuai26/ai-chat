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

# ---------------- 行情抓取 ----------------
def fetch_sina(codes):
    """新浪实时行情，返回 {code: parsed}。GBK 编码。"""
    url = "https://hq.sinajs.cn/list=" + ",".join(codes)
    try:
        raw = http_get(url, headers={"User-Agent": UA, "Referer": "https://finance.sina.com.cn"}, binary=True)
        text = raw.decode("gbk", "replace")
    except Exception as e:
        print(f"  ⚠️ sina 抓取失败: {e}"); return {}
    out = {}
    for line in text.strip().split("\n"):
        if "=" not in line: continue
        code = line.split("=")[0].replace("var hq_str_", "").strip()
        val = line.split('"', 1)[1].rsplit('"', 1)[0] if '"' in line else ""
        f = val.split(",")
        if len(f) < 4: continue
        try:
            if code.startswith("hk"):
                # 港股: name_en, name_cn, open, prevclose, high, low, now, chg, chgpct, ...
                name = f[1]; openp=float(f[2]); prev=float(f[3]); high=float(f[4]); low=float(f[5])
                now=float(f[6]); chg=float(f[7]); chgpct=float(f[8])
                out[code]={"name":name,"price":now,"open":openp,"prev":prev,"high":high,"low":low,
                           "change":chg,"change_pct":chgpct,"vol":None,"date":f[17] if len(f)>17 else "","l2":[]}
            else:
                # A股/指数/ETF: name, open, prevclose, now, high, low, ...(五档)... vol, amount
                name=f[0]; openp=float(f[1]); prev=float(f[2]); now=float(f[3]); high=float(f[4]); low=float(f[5])
                vol=float(f[8]) if len(f)>8 and f[8] else None
                chg = now-prev; chgpct = (chg/prev*100) if prev else 0.0
                # 买卖五档(A股有，指数为0)
                l2=[]
                try:
                    for i in range(5):
                        bvol=f[10+i*2]; bp=f[11+i*2]
                        if bp and float(bp)>0: l2.append(("买"+str(i+1), bp, bvol))
                    for i in range(5):
                        avol=f[20+i*2]; ap=f[21+i*2]
                        if ap and float(ap)>0: l2.append(("卖"+str(i+1), ap, avol))
                except Exception: pass
                amp = ((high-low)/prev*100) if prev else 0.0
                out[code]={"name":name,"price":now,"open":openp,"prev":prev,"high":high,"low":low,
                           "change":round(chg,3),"change_pct":round(chgpct,2),"vol":vol,"amp":round(amp,2),
                           "date":(f[30] if len(f)>30 else ""),"l2":l2}
        except Exception as e:
            print(f"  ⚠️ 解析 {code} 失败: {e}")
    return out

_LAST_YH = [0.0]
YH_MIN_INTERVAL = float(os.environ.get("YH_GAP", "12"))  # Yahoo 全局间隔(秒)，可用环境变量覆盖。共享代理IP限流敏感

def _yahoo_throttle():
    dt = time.time() - _LAST_YH[0]
    if dt < YH_MIN_INTERVAL:
        time.sleep(YH_MIN_INTERVAL - dt)
    _LAST_YH[0] = time.time()

def _yahoo_get(symbol, rng, interval):
    """Yahoo chart 取数。全局节流(>=5s/次) + query2代理 + 429退避 + 直连兜底。返回 result[0] 或 None。"""
    sym = urllib.parse.quote(symbol)
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?interval={interval}&range={rng}"
    _yahoo_throttle()
    for attempt in range(2):  # 代理 + 429退避
        try:
            d = json.loads(http_get(url, use_proxy=True, timeout=15))
            return d["chart"]["result"][0]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(15)
                continue
            break
        except Exception:
            break
    # 直连兜底一次
    try:
        d = json.loads(http_get(url, use_proxy=False, timeout=12))
        return d["chart"]["result"][0]
    except Exception:
        return None

def fetch_yahoo_quote(symbol):
    """Yahoo 实时行情(取 chart meta)。query2+退避+直连兜底。"""
    r = _yahoo_get(symbol, "5d", "1d")
    if not r:
        print(f"  ⚠️ yahoo quote {symbol} 取数失败")
        return None
    try:
        m = r["meta"]
        price = m.get("regularMarketPrice"); prev = m.get("chartPreviousClose") or m.get("previousClose")
        chg = (price-prev) if (price is not None and prev) else None
        chgpct = (chg/prev*100) if (chg is not None and prev) else None
        return {"name":symbol,"price":price,"prev":prev,
                "open":m.get("regularMarketOpen"),"high":m.get("regularMarketDayHigh"),
                "low":m.get("regularMarketDayLow"),"vol":m.get("regularMarketVolume"),
                "change":round(chg,4) if chg is not None else None,
                "change_pct":round(chgpct,2) if chgpct is not None else None,
                "w52h":m.get("fiftyTwoWeekHigh"),"w52l":m.get("fiftyTwoWeekLow"),
                "currency":m.get("currency"),"l2":[]}
    except Exception as e:
        print(f"  ⚠️ yahoo quote {symbol} 解析失败: {e}")
        return None

# ---------------- 历史K线（统一走 Yahoo：所有市场都支持） ----------------
def fetch_yahoo_kline(symbol, rng, interval):
    r = _yahoo_get(symbol, rng, interval)
    if not r:
        print(f"  ⚠️ yahoo kline {symbol} {rng} 取数失败"); return []
    try:
        ts=r.get("timestamp") or []; q=r["indicators"]["quote"][0]
        intraday = "m" in interval  # 分钟级带时分
        out=[]
        for i,t in enumerate(ts):
            o,h,l,c=q["open"][i],q["high"][i],q["low"][i],q["close"][i]
            if None in (o,h,l,c): continue
            fmt="%Y-%m-%d %H:%M" if intraday else "%Y-%m-%d"
            dt=datetime.fromtimestamp(t,TZ).strftime(fmt)
            out.append({"date":dt,"o":round(o,3),"h":round(h,3),"l":round(l,3),"c":round(c,3),
                        "vol":q["volume"][i]})
        return out
    except Exception as e:
        print(f"  ⚠️ yahoo kline {symbol} {rng} 解析失败: {e}"); return []

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

YH_GAP = 6  # Yahoo 请求间隔(秒)，防 429

def fetch_sina_kline(code, datalen=130):
    """新浪日K(A股/指数/ETF直连，零限流)。code 形如 sh600519/sh000001/sh510300。"""
    url=(f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
         f"?symbol={code}&scale=240&ma=no&datalen={datalen}")
    try:
        arr=json.loads(http_get(url, headers={"Referer":"https://finance.sina.com.cn"}))
        out=[]
        for it in arr:
            out.append({"date":it["day"][:10],"o":float(it["open"]),"h":float(it["high"]),
                        "l":float(it["low"]),"c":float(it["close"]),"vol":float(it.get("volume",0) or 0)})
        return out
    except Exception as e:
        print(f"  ⚠️ sina kline {code} 失败: {e}"); return []

def fetch_kline_bundle(w):
    """按 source 路由：A股/指数/ETF 走新浪日K(无限流)；港股/美股/加密走 Yahoo。
       w = watchlist 条目。返回 {1D,1W,1M,3M}。"""
    code=w["code"]; src=w.get("source"); ysym=w.get("yahoo_sym", code)
    is_a_share = src=="sina" and not code.startswith("hk")  # A股/指数/ETF
    if is_a_share:
        daily = fetch_sina_kline(code, 130)
        # A股暂无免费分时，1D 用最近交易日的日K切片占位(后续可接腾讯分时)
        per = {"1D": daily[-1:] if daily else []}
        for label, n in SLICE.items():
            per[label] = daily[-n:] if daily else []
        return per
    # 港股/美股/加密 → Yahoo
    daily = fetch_yahoo_kline(ysym, "6mo", "1d")
    intraday = fetch_yahoo_kline(ysym, "5d", "5m")
    per = {"1D": intraday}
    for label, n in SLICE.items():
        per[label] = daily[-n:] if daily else []
    return per

def main():
    data = load("data.json", {})
    watchlist = data.get("watchlist", [])
    ai_comment = data.get("ai_comment", {})

    sina_codes=[w["code"] for w in watchlist if w.get("source")=="sina"]
    quotes={}
    if sina_codes:
        quotes.update(fetch_sina(sina_codes))
    cached_quotes = data.get("quotes", {})
    for w in watchlist:
        if w.get("source")=="yahoo":
            q=fetch_yahoo_quote(w.get("yahoo_sym", w["code"]))
            if not q and cached_quotes.get(w["code"]):
                q=dict(cached_quotes[w["code"]]); q["_stale"]=True  # Yahoo失败→用缓存quote兜底
                print(f"  · {w['name']} quote 用缓存兜底", flush=True)
            if q: q["name"]=w["name"]; quotes[w["code"]]=q

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
            print(f"  · {w['name']}({code}) 用今日K线缓存", flush=True)
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
            line_charts[label]=[{"date":p["date"][5:],"value":p["c"]} for p in k]
            candle_charts[label]=[{"x":p["date"],"o":p["o"],"h":p["h"],"l":p["l"],"c":p["c"]} for p in k]
        q=det.get("quote",{})
        sub=[]
        # 双图卡：chartType 可切 line/candlestick，tabs 切周期
        sub.append({"type":"stock_chart","title":f"{w['name']} ({code})",
            "periods":PERIODS,"default_period":"1M",
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
