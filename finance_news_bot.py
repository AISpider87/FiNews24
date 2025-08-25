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
load_dotenv(override=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Optional LLM
LLM_PROVIDER   = os.getenv("LLM_PROVIDER", "").strip()  # 'openai' per abilitare
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
COMMENT_MODEL  = os.getenv("COMMENT_MODEL", OPENAI_MODEL).strip()

# Runtime safeguards (env-configurable)
FEED_TIMEOUT      = int(os.getenv("FEED_TIMEOUT", "12"))       # seconds
FEED_RETRIES      = int(os.getenv("FEED_RETRIES", "2"))
DEADLINE_SECONDS  = int(os.getenv("DEADLINE_SECONDS", "540"))  # 9 minutes

# Thematic filtering (ENV-overridable)
def _split_env_list(name: str, default_items: List[str]) -> List[str]:
    raw = os.getenv(name, "")
    items = [x.strip().lower() for x in raw.split(",") if x.strip()]
    return items or default_items

NEGATIVE_KEYWORDS = _split_env_list("NEGATIVE_KEYWORDS", [
    "papa","vaticano","chiesa","religione","vescovo","santo padre",
    "omicidio","rapina","arrestato","cronaca","assassino","spari","sparatoria",
    "sequestro","violenza","stupro","femminicidio","latitante","inchiesta giudiziaria",
    "gossip","spettacolo","vip","celebrity","reality","calcio","serie a","sport",
])

ECON_KEYWORDS = _split_env_list("ECON_KEYWORDS", [
    # ITA
    "pil","inflazione","deflazione","tassi","bce","federal reserve","fed","banca centrale",
    "spread","debito","obbligazioni","titoli di stato","btp","bund","mercati","borsa",
    "azioni","azionario","obbligazionario","derivati","futures","opzioni","volatilità",
    "commodities","materie prime","petrolio","gas","oro","rame","wti","brent",
    "bilancio","utile","ricavi","eps","guidance","dividendo",
    "pmi","indice pmi","occupazione","disoccupazione","cpi","ppi","pil trimestrale",
    "gdp","indice","indice dei prezzi","bilancia commerciale","partite correnti",
    "criptovalute","bitcoin","ethereum","cripto","defi","stablecoin",
    # ENG
    "inflation","deflation","interest rate","rates","central bank","ecb","fed",
    "treasury","yield","bond","government bond","equities","stocks","stock market",
    "earnings","revenue","guidance","dividend","commodity","oil","gas","gold","copper",
    "pmi","employment","unemployment","cpi","ppi","gdp","trade balance","current account",
    "bitcoin","ethereum","crypto","defi","stablecoin",
])

WHITELIST_DOMAINS = _split_env_list("WHITELIST_DOMAINS", [
    "ft.com","economist.com","bbc.co.uk","cnn.com","apnews.com","nytimes.com",
    "theguardian.com","marketwatch.com","nasdaq.com","cnbc.com","coindesk.com",
    "cointelegraph.com","bitcoinmagazine.com","oilprice.com","kitco.com","mining.com",
    "project-syndicate.org","coingecko.com","coinmarketcap.com","decrypt.co",
    "ilsole24ore.com","ansa.it","repubblica.it","ecb.europa.eu","federalreserve.gov",
    "bankofcanada.ca","calculatedriskblog.com","econbrowser.com","marginalrevolution.com",
    "wolfstreet.com","mishtalk.com","ritholtz.com","awealthofcommonsense.com",
    "thereformedbroker.com","fredblog.stlouisfed.org","billmitchell.org","eyeonhousing.org",
    "supplysideliberal.com","atlantafed.org","jwmason.org",
])

REQUIRE_ECON_KEYWORDS = os.getenv("REQUIRE_ECON_KEYWORDS", "true").lower() == "true"

# Social: Twitter/X (facoltativo)
ENABLE_TWITTER = os.getenv("ENABLE_TWITTER", "false").lower() == "true"
TWITTER_API_KEY       = os.getenv("TWITTER_API_KEY", "").strip()
TWITTER_API_SECRET    = os.getenv("TWITTER_API_SECRET", "").strip()
TWITTER_ACCESS_TOKEN  = os.getenv("TWITTER_ACCESS_TOKEN", "").strip()
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET", "").strip()

# Hashtag
HASHTAGS_BASE = os.getenv("HASHTAGS_BASE", "#borsa #mercati #crypto #bitcoin #inflazione #wallstreet")

# Feeds and behavior
FEEDS = [f.strip() for f in os.getenv("FEEDS", "").split(",") if f.strip()] or [
    # --- Finance / Business (solidi) ---
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "https://www.ft.com/markets?format=rss",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://cdn.cnn.com/cnn/.rss/edition_business.rss",
    "https://apnews.com/hub/business?utm_source=apnews.com&utm_medium=referral&utm_campaign=ap-rss",
    "https://economist.com/feeds/print-sections/79/finance-and-economics.xml",
    "https://blogs.imf.org/feed/",
    "https://www.project-syndicate.org/rss",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://www.theguardian.com/business/rss",
    "https://www.theguardian.com/business/economics/rss",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://www.marketwatch.com/rss/topstories",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.nasdaq.com/feed/rssoutbound?category=Markets",
    "https://www.nasdaq.com/feed/rssoutbound?category=Stocks",
    "https://www.nasdaq.com/feed/rssoutbound?category=Commodities",

    # --- Italia / Europa ---
    "https://www.ansa.it/sito/notizie/economia/economia_rss.xml",
    "https://www.ilsole24ore.com/rss/homepage.xml",
    "https://www.ilsole24ore.com/rss/economia.xml",
    "https://www.repubblica.it/rss/economia/rss2.0.xml",
    "https://www.ecb.europa.eu/rss/press.html",
    "https://www.federalreserve.gov/feeds/press_all.xml",
    "https://www.bankofcanada.ca/content_type/press-releases/feed/",

    # --- Investing.com (varie sezioni utili) ---
    "https://www.investing.com/rss/news_25.rss",
    "https://www.investing.com/rss/news_1.rss",
    "https://www.investing.com/rss/news_11.rss",
    "https://www.investing.com/rss/news_95.rss",
    "https://www.investing.com/rss/news_14.rss",
    "https://www.investing.com/rss/news_301.rss",
    "https://www.investing.com/rss/news.rss",

    # --- Commodities / Energy / Metals ---
    "https://oilprice.com/rss/main",
    "https://www.kitco.com/rss/feeds/KitcoNews.xml",
    "https://www.mining.com/feed/",

    # --- Crypto (notizie principali) ---
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://www.bitcoinmagazine.com/.rss/full/",
    "https://news.bitcoin.com/feed/",
    "https://blockworks.co/feed",
    "https://www.nasdaq.com/feed/rssoutbound?category=Cryptocurrencies",
    "https://www.coinmarketcap.com/headlines/news/feed",
    "https://www.coingecko.com/news.atom",
    "https://decrypt.co/feed",

    # --- Macro / Blog analitici ---
    "http://feeds.feedburner.com/CalculatedRisk",
    "https://www.calculatedriskblog.com/feeds/posts/default",
    "https://econbrowser.com/feed",
    "https://marginalrevolution.com/feed",
    "https://wolfstreet.com/feed/",
    "https://mishtalk.com/feed",
    "https://ritholtz.com/feed",
    "https://awealthofcommonsense.com/feed/",
    "https://thereformedbroker.com/feed/",
    "https://feeds.feedburner.com/EconomicsOne",
    "https://fredblog.stlouisfed.org/feed/",
    "https://billmitchell.org/blog/?feed=rss2",
    "https://eyeonhousing.org/category/macroeconomics/feed/",
    "https://blog.supplysideliberal.com/post?format=RSS",
    "https://www.atlantafed.org/RSS/macroblog.aspx",
    "https://jwmason.org/the-slack-wire/feed/",

    # --- Personal finance (selezione leggera) ---
    "https://financialsamurai.com/feed/",
    "https://www.mrmoneymustache.com/feed/",
    "https://www.getrichslowly.org/feed/",
    "https://www.thesimpledollar.com/feed/",
    "https://www.nerdwallet.com/blog/feed/",
    "https://feeds.feedburner.com/Moneytalksnews",
    "https://affordanything.com/feed/",
    "https://www.kiplinger.com/kiplinger.rss",

    # --- Altre testate globali ---
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.straitstimes.com/news/business/rss.xml",
    "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936",

    # --- FT aggiuntivi ---
    "https://www.ft.com/ft-editors-picks/rss",
]

KEYWORDS = [k.strip().lower() for k in os.getenv("KEYWORDS", "").split(",") if k.strip()]  # optional extra-positive
POST_LIMIT_PER_RUN = int(os.getenv("POST_LIMIT_PER_RUN", "6"))
MAX_SUMMARY_LEN    = int(os.getenv("MAX_SUMMARY_LEN", "240"))
FRESHNESS_MINUTES  = int(os.getenv("FRESHNESS_MINUTES", "360"))
DRY_RUN            = os.getenv("DRY_RUN", "true").lower() == "true"
CACHE_PATH         = os.getenv("CACHE_PATH", "finance_news_cache.json")

TZ = pytz.timezone(os.getenv("TIMEZONE", "Europe/Rome"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ====== Agents ======
class FeedAgent:
    def __init__(self, timeout: int = FEED_TIMEOUT, retries: int = FEED_RETRIES):
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
        for attempt in range(1, self.retries + 2):
            try:
                r = self.session.get(url, timeout=self.timeout)
                r.raise_for_status()
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

    @staticmethod
    def _entry_text(entry: Dict) -> str:
        title = entry.get("title", "") or ""
        summary = BeautifulSoup(entry.get("summary", "") or "", "html.parser").get_text(" ", strip=True)
        tags = " ".join((t.get("term") or "") for t in entry.get("tags", []) if isinstance(t, dict))
        return f"{title} {summary} {tags}".lower()

    @staticmethod
    def _entry_domain(entry: Dict) -> str:
        link = entry.get("link", "") or ""
        return urlparse(link).netloc.replace("www.", "").lower()

    def _is_fresh(self, entry) -> bool:
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
            return True
        return (now - published) <= self.freshness

    def _has_negative(self, text: str) -> bool:
        return any(neg in text for neg in NEGATIVE_KEYWORDS)

    def _is_economic(self, text: str, domain: str) -> bool:
        if domain in WHITELIST_DOMAINS:
            return True
        return any(k in text for k in ECON_KEYWORDS)

    def _matches_user_keywords(self, text: str) -> bool:
        if not self.keywords:
            return True
        return any(k in text for k in self.keywords)

    def filter(self, entries: List[Dict]) -> List[Dict]:
        out = []
        for e in entries:
            title = (e.get("title") or "").strip()
            if not title:
                continue
            if not self._is_fresh(e):
                continue

            text = self._entry_text(e)
            domain = self._entry_domain(e)

            if self._has_negative(text):
                continue
            if REQUIRE_ECON_KEYWORDS and not self._is_economic(text, domain):
                continue
            if not self._matches_user_keywords(text):
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
        if self.provider == "openai" and self.api_key:
            res = self._openai_chat(text[:3000])
            if res:
                return res[: self.max_len]
        s = self._strip_html(summary)
        if not s:
            return title[: self.max_len]
        return s[: self.max_len]

class CommentAgent:
    """Genera un breve commento/analisi con GPT."""
    def __init__(self, provider: str = "", api_key: str = "", model: str = "gpt-4o-mini", max_len: int = 240):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.max_len = max_len

    def _openai_chat(self, title: str, source: str, summary_text: str) -> Optional[str]:
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            prompt = (
                "Scrivi UNA sola riga di analisi rapida (tono sobrio, 1 implicazione pratica per investitori, "
                "no esagerazioni, no consigli finanziari). Max 220 caratteri.\n\n"
                f"Titolo: {title}\nFonte: {source}\nContenuto: {summary_text[:1000]}"
            )
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "Sei un analista finanziario sintetico e neutrale."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.4,
                "max_tokens": 120
            }
            r = requests.post(url, headers=headers, json=body, timeout=30)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logging.warning(f"LLM comment error: {e}")
            return None

    @staticmethod
    def _strip_html(text: str) -> str:
        return BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)

    def comment(self, title: str, source: str, summary_html: str) -> Optional[str]:
        if self.provider != "openai" or not self.api_key:
            return None
        clean = self._strip_html(summary_html)
        out = self._openai_chat(title, source, clean)
        if not out:
            return None
        return out[: self.max_len]

class HashtagAgent:
    """Hashtag fissi + dinamici in base al contenuto."""
    DYNAMIC_MAP = {
        "#bitcoin": ["bitcoin", "btc"],
        "#ethereum": ["ethereum", "eth"],
        "#crypto": ["crypto", "criptovalute", "defi", "stablecoin"],
        "#inflazione": ["inflazione", "inflation", "cpi", "ppi"],
        "#tassi": ["tassi", "rates", "interest rate", "bce", "ecb", "fed", "federal reserve", "yield", "treasury"],
        "#petrolio": ["petrolio", "oil", "brent", "wti"],
        "#oro": ["oro", "gold"],
        "#azioni": ["azioni", "stocks", "equities", "borsa", "stock market"],
        "#obbligazioni": ["obbligazioni", "bond", "bund", "btp", "treasury"],
        "#materieprime": ["commodities", "materie prime", "rame", "gas", "copper"],
        "#mercati": ["mercati", "markets", "wall street", "wallstreet"],
    }

    def __init__(self, base: str):
        # normalizza base in lista
        self.base = [h if h.startswith("#") else f"#{h}" for h in base.split() if h.strip()]

    def gen(self, text_for_tags: str, max_total: int = 10) -> str:
        text_l = text_for_tags.lower()
        dynamic = []
        for tag, keys in self.DYNAMIC_MAP.items():
            if any(k in text_l for k in keys):
                dynamic.append(tag)
        # rimuovi duplicati preservando ordine
        seen = set()
        out = []
        for h in self.base + dynamic:
            if h not in seen:
                seen.add(h)
                out.append(h)
            if len(out) >= max_total:
                break
        return " ".join(out)

class TwitterAgent:
    """Pubblica su Twitter/X (facoltativo)."""
    def __init__(self, enabled: bool, api_key: str, api_secret: str, access_token: str, access_secret: str, dry_run: bool):
        self.enabled = enabled and all([api_key, api_secret, access_token, access_secret])
        self.dry_run = dry_run
        self.client = None
        if self.enabled:
            try:
                import tweepy  # type: ignore
                auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
                self.client = tweepy.API(auth)
            except Exception as e:
                logging.error(f"Twitter init error: {e}")
                self.enabled = False

    @staticmethod
    def _trim_for_tweet(title: str, link: str, hashtags: str, limit: int = 280) -> str:
        base = f"{title} {link}".strip()
        # aggiungi 2-3 hashtag solo se c'è spazio
        tags = " " + " ".join(hashtags.split()[:3]) if hashtags else ""
        text = (base + tags).strip()
        if len(text) <= limit:
            return text
        # taglia titolo se necessario
        cut = limit - len(link) - len(tags) - 1
        if cut < 10:
            # niente hashtag se spazio troppo poco
            tags = ""
            cut = limit - len(link) - 1
        short_title = (title[:cut-1] + "…") if len(title) > cut else title
        return f"{short_title} {link}{tags}"

    def post(self, title: str, link: str, hashtags: str):
        if not self.enabled:
            return {"ok": True, "skipped": True}
        text = self._trim_for_tweet(title, link, hashtags)
        if self.dry_run:
            logging.info("[DRY_RUN] Tweet simulato:\n" + text)
            return {"ok": True, "dry_run": True}
        try:
            self.client.update_status(status=text)
            return {"ok": True}
        except Exception as e:
            logging.error(f"Twitter post error: {e}")
            return {"ok": False, "error": str(e)}

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
def build_post(entry, summarizer: 'SummarizerAgent', commenter: 'CommentAgent', hashtagger: 'HashtagAgent') -> Dict[str, str]:
    title = entry.get("title", "").strip()
    link  = entry.get("link", "").strip()
    summary_html = entry.get("summary", "") or ""
    source = urlparse(link).netloc.replace("www.", "") if link else ""

    # riassunto (frase)
    blurb = summarizer.summarize(title, summary_html)

    # analisi/commento (1 riga)
    comment = commenter.comment(title, source, summary_html) if commenter else None

    # hashtag
    base_text_for_tags = f"{title} {BeautifulSoup(summary_html, 'html.parser').get_text(' ', strip=True)} {source}"
    hashtags = hashtagger.gen(base_text_for_tags)

    # testo Telegram
    parts = [f"📰 {title}"]
    if blurb and blurb.lower() not in title.lower():
        parts.append(blurb)
    if comment:
        parts.append(f"💬 Analisi: {comment}")
    if source:
        parts.append(f"Fonte: {source}")
    if link:
        parts.append(link)
    if hashtags:
        parts.append(hashtags)
    post_text = "\n\n".join(parts)

    return {"post_text": post_text, "title": title, "link": link, "hashtags": hashtags}

def _sort_key(e):
    for field in ("published", "updated", "created"):
        v = e.get(field)
        if v:
            try:
                dt = dateparser.parse(v)
                if not dt.tzinfo:
                    dt = TZ.localize(dt)
                return dt.astimezone(pytz.UTC)
            except Exception:
                pass
    return datetime.now(pytz.UTC)

def main():
    deadline = time.time() + DEADLINE_SECONDS

    feed_agent   = FeedAgent(timeout=FEED_TIMEOUT, retries=FEED_RETRIES)
    filter_agent = FilterAgent(KEYWORDS, TZ, FRESHNESS_MINUTES)
    dedup        = DedupAgent(CACHE_PATH)
    summarizer   = SummarizerAgent(LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL, MAX_SUMMARY_LEN)
    commenter    = CommentAgent(LLM_PROVIDER, OPENAI_API_KEY, COMMENT_MODEL, max_len=220)
    hashtagger   = HashtagAgent(HASHTAGS_BASE)
    publisher    = PublisherAgent(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, dry_run=DRY_RUN)
    twitter      = TwitterAgent(ENABLE_TWITTER, TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET, dry_run=DRY_RUN)

    collected: List[Dict] = []
    for f in FEEDS:
        if time.time() > deadline:
            logging.warning("Deadline reached while fetching feeds. Stopping early.")
            break
        entries = feed_agent.fetch(f)
        fresh   = filter_agent.filter(entries)
        for e in fresh:
            if dedup.is_new(e):
                collected.append(e)

    collected = sorted(collected, key=_sort_key, reverse=True)

    posted = 0
    for e in collected:
        if time.time() > deadline:
            logging.warning("Deadline reached while posting. Stopping early.")
            break
        if posted >= POST_LIMIT_PER_RUN:
            break

        built = build_post(e, summarizer, commenter, hashtagger)
        text  = built["post_text"]
        title = built["title"]
        link  = built["link"]
        tags  = built["hashtags"]

        try:
            publisher.post(text)
            # Tweet (facoltativo)
            if link:
                twitter.post(title, link, tags)
            dedup.mark(e)
            posted += 1
            time.sleep(2)  # be nice to APIs
        except Exception as ex:
            logging.error(f"Post failed: {ex}")
            continue

    logging.info(f"Run complete. Posted {posted} items.")

if __name__ == "__main__":
    main()
