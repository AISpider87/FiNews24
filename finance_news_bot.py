
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
import pytz
from dotenv import load_dotenv

# ====== Config & Logging ======
# Read .env variables, forcing override of any pre-existing environment variables.
# Without override=True, variables set in the system environment (e.g., DRY_RUN)
# would take precedence over the .env file. This can lead to confusion when
# adjusting DRY_RUN in the .env file if a conflicting system variable exists.
load_dotenv(override=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Optional LLM
LLM_PROVIDER   = os.getenv("LLM_PROVIDER", "").strip()  # 'openai' to enable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

# Feeds and behavior
FEEDS = [f.strip() for f in os.getenv("FEEDS", "").split(",") if f.strip()] or [
    # Default finance/business RSS feeds (public)
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",    # WSJ Markets
    "https://www.ft.com/?format=rss",                   # FT Top
    "https://www.investing.com/rss/news_25.rss",        # Investing.com - Top News
    "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://it.investing.com/rss/forex_Technical.rss",
    "https://it.investing.com/rss/stock_Stocks.rss",
    "https://it.investing.com/rss/news_1064.rss",
    "https://www.fxempire.com/api/v1/it/articles/rss/news",
    "https://www.fxempire.com/api/v1/it/articles/rss/forecasts",
    "https://billmitchell.org/blog/?feed=rss2",
    "https://ritholtz.com/feed",
    "https://eyeonhousing.org/category/macroeconomics/feed/",
    "https://blog.supplysideliberal.com/post?format=RSS",
    "https://www.atlantafed.org/RSS/macroblog.aspx",
    "https://jwmason.org/the-slack-wire/feed/",
    "https://eyeonhousing.org/category/macroeconomics/feed/",
"https://feeds.bbci.co.uk/news/business/rss.xml",
"https://rss.cnn.com/rss/edition_business.rss",
"http://feeds.reuters.com/reuters/businessNews",
"http://feeds.reuters.com/reuters/marketsNews",
"https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
"https://apnews.com/rss/apf-business",
"https://www.wsj.com/xml/rss/3_7031.xml",
"https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
"https://www.ft.com/?format=rss",
"https://economist.com/feeds/print-sections/79/finance-and-economics.xml",
"https://blogs.imf.org/feed/",
"https://cepr.org/rss/vox-content",
"https://investing.com/rss/news_25.rss",
"https://investing.com/rss/news_1.rss",
"https://investing.com/rss/news_11.rss",
"https://investing.com/rss/news_95.rss",
"https://investing.com/rss/news_14.rss",
"https://investing.com/rss/news_301.rss",
"https://www.nasdaq.com/feed/rssoutbound?category=Markets",
"https://www.nasdaq.com/feed/rssoutbound?category=Stocks",
"https://www.nasdaq.com/feed/rssoutbound?category=Cryptocurrencies",
"https://www.nasdaq.com/feed/rssoutbound?category=Commodities",
"https://oilprice.com/rss/main",
"https://www.kitco.com/rss/feeds/KitcoNews.xml",
"https://www.mining.com/feed/",
"https://www.coindesk.com/arc/outboundfeeds/rss/",
"https://cointelegraph.com/rss",
"https://www.bitcoinmagazine.com/.rss/full/",
"https://news.bitcoin.com/feed/",
"https://blockworks.co/feed",
"https://financialsamurai.com/feed/",
"https://www.mrmoneymustache.com/feed/",
"https://www.getrichslowly.org/feed/",
"https://www.thesimpledollar.com/feed/",
"https://www.nerdwallet.com/blog/feed/",
"https://feeds.feedburner.com/Moneytalksnews",
"https://affordanything.com/feed/",
"https://www.kiplinger.com/kiplinger.rss",
"http://feeds.feedburner.com/CalculatedRisk",
"https://econbrowser.com/feed",
"https://marginalrevolution.com/feed",
"https://feeds.feedburner.com/nakedcapitalism",
"https://wolfstreet.com/feed/",
"https://mishtalk.com/feed",
"https://ritholtz.com/feed",
"https://awealthofcommonsense.com/feed/",
"https://thereformedbroker.com/feed/",
"https://feeds.feedburner.com/zerohedge/feed",
"https://feeds.feedburner.com/EconomicsOne",
"https://www.ansa.it/sito/notizie/economia/economia_rss.xml",
"https://www.ansa.it/english/news/english_nr_rss.xml",
"https://www.ilsole24ore.com/rss/homepage.xml",
"https://www.ilsole24ore.com/rss/economia.xml",
"https://www.repubblica.it/rss/economia/rss2.0.xml",
"https://feeds.skynews.com/feeds/rss/business.xml",
"https://www.theguardian.com/business/rss",
"https://www.aljazeera.com/xml/rss/all.xml",
"https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
"https://www.theguardian.com/business/economics/rss",
"https://www.straitstimes.com/news/business/rss.xml",
"https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936",
"https://www.federalreserve.gov/feeds/press_all.xml",
"https://www.ecb.europa.eu/rss/press.html",
"https://www.bankofcanada.ca/content_type/press-releases/feed/",
"https://www.project-syndicate.org/rss",
"https://feeds.feedburner.com/CalculatedRisk",
"https://feeds.feedburner.com/Economist-sView",
"https://www.ft.com/feeds/rss/markets",
"https://www.ft.com/markets?format=rss",
"https://feeds.marketwatch.com/marketwatch/topstories/",
"https://www.investing.com/rss/news.rss",
"https://www.cnbc.com/id/100003114/device/rss/rss.html",
"https://www.forbes.com/finance/feed/",
"https://www.marketwatch.com/rss/topstories",
"https://www.businessinsider.com/rss",
"https://feeds.feedburner.com/businessinsider",
"https://www.thestreet.com/.rss/full/",
"https://www.yahoo.com/news/tagged/finance/rss",
"https://www.politico.com/rss/politics-economy.xml",
"https://freakonomics.com/feed/",
"https://economix.blogs.nytimes.com/feed/",
"https://ftalphaville.ft.com/blog/feed/",
"https://www.coinmarketcap.com/headlines/news/feed",
"https://www.coingecko.com/news.atom",
"https://www.calculatedriskblog.com/feeds/posts/default",
"https://www.ft.com/ft-editors-picks/rss",
"https://fredblog.stlouisfed.org/feed/",
"https://decrypt.co/feed",

]
KEYWORDS = [k.strip().lower() for k in os.getenv("KEYWORDS", "").split(",") if k.strip()]  # optional
POST_LIMIT_PER_RUN = int(os.getenv("POST_LIMIT_PER_RUN", "6"))
MAX_SUMMARY_LEN    = int(os.getenv("MAX_SUMMARY_LEN", "240"))
FRESHNESS_MINUTES  = int(os.getenv("FRESHNESS_MINUTES", "360"))  # consider items fresh if within last X minutes
DRY_RUN            = os.getenv("DRY_RUN", "true").lower() == "true"
CACHE_PATH         = os.getenv("CACHE_PATH", "finance_news_cache.json")

TZ = pytz.timezone(os.getenv("TIMEZONE", "Europe/Rome"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ====== Agents ======
class FeedAgent:
    def __init__(self, timeout=12, retries=2):
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0 Safari/537.36 FinanceNewsBot/1.0",
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "close",
        })

    def fetch(self, url: str) -> List[Dict]:
        logging.info(f"Fetching feed: {url}")
        for attempt in range(1, self.retries + 2):  # es. 1 tentativo + 2 retry
            try:
                r = self.session.get(url, timeout=self.timeout)
                r.raise_for_status()
                # Passo i bytes al parser: migliore tolleranza a Content-Type strani / HTML
                parsed = feedparser.parse(r.content)
                if getattr(parsed, "bozo", False) and getattr(parsed, "bozo_exception", None):
                    logging.warning(f"Feed parsing warning ({url}): {parsed.bozo_exception}")
                return parsed.entries or []
            except Exception as e:
                if attempt <= self.retries:
                    logging.info(f"Retry {attempt}/{self.retries} on {url} due to: {e}")
                    time.sleep(1.5)
                    continue
                logging.error(f"Feed fetch error ({url}): {e}")
                return []


class FilterAgent:
    def __init__(self, keywords: List[str], tz, freshness_minutes: int = 360):
        self.keywords = [k.lower() for k in keywords]
        self.tz = tz
        self.freshness = timedelta(minutes=freshness_minutes)

    def _is_fresh(self, entry) -> bool:
        # Try published/updated; fall back to now
        now = datetime.now(self.tz)
        published = None
        for field in ("published", "updated", "created"):
            val = getattr(entry, field, None) or entry.get(field)
            if val:
                try:
                    dt = dateparser.parse(val)
                    if not dt.tzinfo:
                        dt = self.tz.localize(dt)
                    published = dt
                    break
                except Exception:
                    pass
        if not published:
            return True  # if no date, don't discard

        return (now - published) <= self.freshness

    def _matches_keywords(self, title: str, summary: str) -> bool:
        if not self.keywords:
            return True
        text = f"{title} {summary}".lower()
        return any(k in text for k in self.keywords)

    def filter(self, entries: List[Dict]) -> List[Dict]:
        out = []
        for e in entries:
            title = e.get("title", "").strip()
            summary = BeautifulSoup(e.get("summary", "") or "", "html.parser").get_text().strip()
            if not title:
                continue
            if not self._is_fresh(e):
                continue
            if not self._matches_keywords(title, summary):
                continue
            out.append(e)
        return out

class DedupAgent:
    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        self._seen = set()
        self._load()

    def _load(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._seen = set(data.get("ids", []))
            except Exception:
                self._seen = set()

    def _save(self):
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump({"ids": list(self._seen)}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Cache save error: {e}")

    @staticmethod
    def _fingerprint(entry: Dict) -> str:
        key = entry.get("id") or entry.get("link") or entry.get("title", "")
        if not key:
            key = json.dumps(entry, sort_keys=True)[:512]
        return hashlib.sha256(key.encode("utf-8", "ignore")).hexdigest()

    def is_new(self, entry: Dict) -> bool:
        fp = self._fingerprint(entry)
        return fp not in self._seen

    def mark(self, entry: Dict):
        fp = self._fingerprint(entry)
        self._seen.add(fp)
        self._save()

class SummarizerAgent:
    def __init__(self, provider: str = "", api_key: str = "", model: str = "gpt-4o-mini", max_len: int = 240):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.max_len = max_len

    def _openai_chat(self, text: str) -> Optional[str]:
        try:
            import requests
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "Riassumi la notizia in 1 frase chiara, neutra, con 1 dato chiave se presente."},
                    {"role": "user", "content": text}
                ],
                "temperature": 0.3,
                "max_tokens": 150
            }
            r = requests.post(url, headers=headers, json=body, timeout=30)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logging.warning(f"LLM summary error: {e}")
            return None

    @staticmethod
    def _strip_html(text: str) -> str:
        return BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)

    def summarize(self, title: str, summary: str) -> str:
        text = f"{title}. {self._strip_html(summary)}"
        # LLM path
        if self.provider == "openai" and self.api_key:
            res = self._openai_chat(text[:3000])  # cap input
            if res:
                return res[: self.max_len]

        # fallback: take first sentence-ish of summary or just the title
        s = self._strip_html(summary)
        if not s:
            return title[: self.max_len]
        # naive: first 240 chars
        blurb = s[: self.max_len]
        return blurb

class PublisherAgent:
    def __init__(self, token: str, chat_id: str, dry_run: bool = True):
        self.token = token
        self.chat_id = chat_id
        self.dry_run = dry_run

    def post(self, text: str) -> Dict:
        if self.dry_run:
            logging.info("[DRY_RUN] Post simulato:\n" + text)
            return {"ok": True, "dry_run": True}

        if not self.token or not self.chat_id:
            raise RuntimeError("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID mancanti.")

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": False}
        r = requests.post(url, json=payload, timeout=30)
        try:
            data = r.json()
        except Exception:
            r.raise_for_status()
            data = {"ok": False, "error": "JSON decode"}
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data}")
        return data

# ====== Orchestrator ======
def build_post(entry, summarizer: SummarizerAgent) -> str:
    title = entry.get("title", "").strip()
    link  = entry.get("link", "").strip()
    summary = entry.get("summary", "").strip()
    source = urlparse(link).netloc.replace("www.", "") if link else ""

    blurb = summarizer.summarize(title, summary)
    parts = [f"📰 {title}"]
    if blurb and blurb.lower() not in title.lower():
        parts.append(blurb)
    if source:
        parts.append(f"Fonte: {source}")
    if link:
        parts.append(link)
    return "\n\n".join(parts)

def _sort_key(e):
    """
    Sorting helper for news entries. It attempts to parse the
    `published`, `updated` or `created` fields and returns a
    timezone-aware UTC datetime. If parsing fails or no date is
    available, it returns the current time in UTC. This ensures
    consistent sorting without mixing naive and aware datetimes.
    """
    for field in ("published", "updated", "created"):
        v = e.get(field)
        if v:
            try:
                dt = dateparser.parse(v)
                # If the date has no timezone, localize it to the configured TZ
                if not dt.tzinfo:
                    dt = TZ.localize(dt)
                # Always convert to UTC for sorting
                return dt.astimezone(pytz.UTC)
            except Exception:
                pass
    # Fallback: current time in UTC
    return datetime.now(pytz.UTC)

def main():
    feed_agent   = FeedAgent()
    filter_agent = FilterAgent(KEYWORDS, TZ, FRESHNESS_MINUTES)
    dedup        = DedupAgent(CACHE_PATH)
    summarizer   = SummarizerAgent(LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL, MAX_SUMMARY_LEN)
    # The PublisherAgent accepts a `dry_run` boolean; pass the evaluated DRY_RUN
    # from the environment or override it here. Use lowercase parameter name
    # and Python boolean `False` instead of the undefined `false`.
    publisher    = PublisherAgent(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, dry_run=DRY_RUN)

    collected: List[Dict] = []
    for f in FEEDS:
        entries = feed_agent.fetch(f)
        fresh   = filter_agent.filter(entries)
        for e in fresh:
            if dedup.is_new(e):
                collected.append(e)
    # Sort by published date descending using the helper
    collected = sorted(collected, key=_sort_key, reverse=True)

    posted = 0
    for e in collected:
        if posted >= POST_LIMIT_PER_RUN:
            break
        text = build_post(e, summarizer)
        try:
            publisher.post(text)
            dedup.mark(e)
            posted += 1
            time.sleep(2)  # be nice to Telegram API
        except Exception as ex:
            logging.error(f"Post failed: {ex}")
            continue

    logging.info(f"Run complete. Posted {posted} items.")

if __name__ == "__main__":
    main()
