#!/usr/bin/env python3
"""
scripts/news_crawler.py — 新闻爬虫脚本 (DB8)

从 user-data/news/sources.json 读取新闻源配置，抓取 RSS 内容，
按分类分组，缓存到 user-data/news/YYYY-MM-DD.json。

用法:
  python3 scripts/news_crawler.py [--force]

最后一行 stdout 输出 JSON 摘要给 news/refresh API。
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import feedparser  # type: ignore
import requests

logging.basicConfig(level=logging.INFO, format="[crawler] %(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# 路径
USER_DATA_DIR = "/home/ubuntu/.openclaw/user-data"
NEWS_DIR = os.path.join(USER_DATA_DIR, "news")
SOURCES_PATH = os.path.join(NEWS_DIR, "sources.json")

# 中国时区
TZ_CN = timezone(timedelta(hours=8))

# 默认新闻源（fallback）
DEFAULT_SOURCES = [
    {"name": "36氪", "url": "https://36kr.com/feed", "type": "rss", "enabled": True, "category": "科技"},
    {"name": "知乎日报", "url": "https://www.zhihu.com/rss", "type": "rss", "enabled": True, "category": "综合"},
    {"name": "少数派", "url": "https://sspai.com/feed", "type": "rss", "enabled": True, "category": "科技"},
    {"name": "阮一峰的网络日志", "url": "https://feeds.feedburner.com/ruanyifeng", "type": "rss", "enabled": True, "category": "科技"},
]

REQUEST_TIMEOUT = 15  # 秒
MAX_ITEMS_PER_SOURCE = 8
MAX_ITEMS_PER_CATEGORY = 20
CACHE_DAYS = 3  # 缓存保留天数


def load_sources() -> list:
    """加载新闻源配置。"""
    try:
        if os.path.isfile(SOURCES_PATH) and os.path.getsize(SOURCES_PATH) > 0:
            with open(SOURCES_PATH, "r", encoding="utf-8") as f:
                sources = json.load(f)
                logger.info(f"已加载 {len(sources)} 个新闻源")
                return [s for s in sources if s.get("enabled", True)]
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"sources.json 读取失败: {e}, 使用默认源")
    logger.info(f"使用 {len(DEFAULT_SOURCES)} 个默认新闻源")
    return [s for s in DEFAULT_SOURCES if s.get("enabled", True)]


def fetch_feed(url: str, name: str) -> list:
    """抓取单个 RSS 源，返回条目列表。"""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={
            "User-Agent": "Mozilla/5.0 (compatible; NewsCrawler/1.0; +https://github.com/yukuai26/ai-chat)"
        })
        resp.raise_for_status()

        feed = feedparser.parse(resp.content if hasattr(resp, "content") else resp.text)
        if feed.bozo and not feed.entries:
            logger.warning(f"{name}: Feed 解析失败 ({feed.bozo_exception})")
            return []

        items = []
        for entry in feed.entries[:MAX_ITEMS_PER_SOURCE]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = entry.get("summary", entry.get("description", ""))
            # 清理 HTML 摘要
            summary = _strip_html(summary)[:200] if summary else ""
            published = entry.get("published", entry.get("updated", ""))

            if not title:
                continue

            items.append({
                "title": title,
                "url": link,
                "source": name,
                "summary": summary,
                "published": published,
            })

        logger.info(f"{name}: 抓取到 {len(items)} 条")
        return items

    except requests.Timeout:
        logger.warning(f"{name}: 请求超时 ({url})")
        return []
    except requests.RequestException as e:
        logger.warning(f"{name}: 请求失败 ({e})")
        return []
    except Exception as e:
        logger.warning(f"{name}: 未知错误 ({e})")
        return []


def _strip_html(text: str) -> str:
    """去除简单的 HTML 标签。"""
    import re
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def crawl(sources: list) -> dict:
    """抓取所有源，按分类分组并去重。"""
    categories: dict[str, list] = {}
    seen_urls: set[str] = set()
    total = 0

    for src in sources:
        name = src["name"]
        url = src.get("url", "")
        category = src.get("category", "综合")

        if not url:
            logger.warning(f"{name}: 跳过（无 URL）")
            continue

        logger.info(f"抓取: {name} ({category})")
        items = fetch_feed(url, name)

        # 去重 + 分类
        for item in items:
            if item["url"] and item["url"] in seen_urls:
                continue
            if item["url"]:
                seen_urls.add(item["url"])
            categories.setdefault(category, []).append(item)
            total += 1

    # 每分类截断
    for cat in categories:
        if len(categories[cat]) > MAX_ITEMS_PER_CATEGORY:
            categories[cat] = categories[cat][:MAX_ITEMS_PER_CATEGORY]

    return {
        "categories": categories,
        "total": total,
    }


def save_cache(result: dict, date_str: str):
    """写入今天的缓存文件。"""
    os.makedirs(NEWS_DIR, exist_ok=True)
    cache_path = os.path.join(NEWS_DIR, f"{date_str}.json")

    cache = {
        "date": date_str,
        "updated": datetime.now(TZ_CN).isoformat(),
        "categories": result["categories"],
        "total": result["total"],
    }

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    logger.info(f"缓存已写入: {cache_path} ({result['total']} 条)")


def clean_old_caches():
    """清理 N 天前的缓存文件。"""
    cutoff = datetime.now(TZ_CN) - timedelta(days=CACHE_DAYS)
    try:
        for fname in os.listdir(NEWS_DIR):
            if not fname.endswith(".json"):
                continue
            try:
                dt = datetime.strptime(fname.replace(".json", ""), "%Y-%m-%d")
                if dt.replace(tzinfo=TZ_CN) < cutoff:
                    os.remove(os.path.join(NEWS_DIR, fname))
                    logger.info(f"清理旧缓存: {fname}")
            except ValueError:
                continue
    except FileNotFoundError:
        pass


def main():
    parser = argparse.ArgumentParser(description="新闻爬虫")
    parser.add_argument("--force", action="store_true", help="强制重新抓取")
    args = parser.parse_args()

    date_str = datetime.now(TZ_CN).strftime("%Y-%m-%d")
    cache_path = os.path.join(NEWS_DIR, f"{date_str}.json")

    # 如果今天已有缓存且非强制模式，跳过
    if not args.force and os.path.isfile(cache_path) and os.path.getsize(cache_path) > 0:
        logger.info(f"今日缓存已存在: {cache_path}")
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        print(json.dumps({
            "ok": True,
            "count": cache.get("total", 0),
            "sources": sum(1 for v in cache.get("categories", {}).values() if v),
            "date": cache.get("date"),
            "cached": True,
        }, ensure_ascii=False))
        return

    # 抓取
    sources = load_sources()
    result = crawl(sources)

    # 保存缓存
    save_cache(result, date_str)

    # 清理旧缓存
    clean_old_caches()

    # 输出摘要（最后一行 JSON，给 news/refresh API 解析）
    output = {
        "ok": result["total"] > 0,
        "count": result["total"],
        "sources": len(sources),
        "date": date_str,
        "cached": False,
    }
    print(json.dumps(output, ensure_ascii=False))

    if result["total"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
