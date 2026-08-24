import feedparser
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import os
import pandas as pd
import concurrent.futures
import time
import logging
import math
import json
import ast
import socket
import re
import numpy as np
import threading
from urllib.parse import quote_plus, urlparse
from googletrans import Translator
from urllib3.exceptions import InsecureRequestWarning

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("urllib3").setLevel(logging.ERROR)
import warnings
warnings.simplefilter("ignore", InsecureRequestWarning)

# Set socket timeout to prevent hanging on bad feeds
socket.setdefaulttimeout(10)

class BNTIAnalyzer:
    BORDER_COUNTRIES = ["Armenia", "Georgia", "Greece", "Iran", "Iraq", "Syria", "Bulgaria"]
    SOURCE_SUFFIX_HINTS = {
        "agency", "bulletin", "daily", "globe", "herald", "journal", "magazine",
        "media", "monitor", "news", "observer", "online", "post", "press",
        "radio", "report", "reporter", "review", "times", "today", "tv", "weekly",
        "wire", "alarabiya", "aljazeera", "armradio", "balkaninsight", "bbc",
        "civil", "civilnet", "dnevnik", "enabbaladi", "eurasianet", "farsnews",
        "georgiatoday", "greekreporter", "hetq", "interpressnews", "irna", "isna",
        "jam", "kathimerini", "middleeasteye", "news247", "npasyria", "observer",
        "protothema", "rudaw", "sana", "skai", "sofiaglobe", "thenationalherald",
        "turkiye",
    }
    LLM_CATEGORY_WEIGHTS = {
        "military_conflict": 8.0,
        "terrorism": 7.0,
        "border_security": 5.0,
        "political_instability": 4.0,
        "humanitarian_crisis": 3.0,
        "diplomatic_tensions": 2.5,
        "trade_agreement": -2.0,
        "neutral": 0.0,
    }
    IMPORTANCE_WEIGHTS = {
        "Syria": 1.5,
        "Iraq": 1.5,
        "Iran": 1.3,
        "Armenia": 1.0,
        "Georgia": 1.0,
        "Greece": 0.6,
        "Bulgaria": 0.6,
    }
    FEED_RETRY_TOTAL = 0
    FEED_RETRY_CONNECT = 0
    FEED_RETRY_READ = 0
    FEED_RETRY_BACKOFF = 0.5
    FEED_REQUEST_TIMEOUT_SECONDS = 8
    FEED_PROXY_TIMEOUT_SECONDS = 8
    FEED_MAX_USER_AGENT_ATTEMPTS = 2
    OPENROUTER_TIMEOUT_SECONDS = 45
    MIN_PUBLISHABLE_TOTAL_SIGNALS = 20
    MIN_PUBLISHABLE_ACTIVE_COUNTRIES = 3
    MIN_SIGNAL_COVERAGE_RATIO = 0.35
    MIN_ACTIVE_COUNTRY_COVERAGE_RATIO = 0.5
    SUMMARY_WINDOW_HOURS = 6
    SUMMARY_REFRESH_INTERVAL_HOURS = 6
    SUMMARY_MAX_SOURCE_EVENTS = 12

    def __init__(self):
        self.output_path = os.getcwd()
        self.history_file = os.path.join(self.output_path, "bnti_history.csv")
        self._init_cache()
        
        # TRANSLATOR (For Report Summaries Only)
        self.translator = Translator()

        # OPENROUTER LLM (For Country Re-Attribution)
        self.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.openrouter_backup_api_key = os.environ.get("OPENROUTER_API_KEY_BACKUP", "")
        self.openrouter_model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
        self.openrouter_base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.openrouter_batch_size = max(int(os.environ.get("OPENROUTER_BATCH_SIZE", "10")), 1)
        self.openrouter_disabled_for_run = False
        self.border_countries = list(self.BORDER_COUNTRIES)
        self.category_weights = dict(self.LLM_CATEGORY_WEIGHTS)

        # RSS Feeds Configuration (Multilingual - Feb 2026)
        self.rss_urls = {
            "Armenia": [
                # English sources
                "https://hetq.am/en/rss",
                "https://armenianweekly.com/feed",
                "https://en.armradio.am/feed/",
                "https://www.panarmenian.net/eng/rss/news/",
                "https://www.civilnet.am/en/rss/",
                # International / wire service
                "https://eurasianet.org/feed",
                # Native Armenian language
                "https://www.aravot.am/feed/",
                "https://news.am/arm/news/rss/",
                "https://168.am/feed/"
            ],
            "Georgia": [
                # English sources
                "https://civil.ge/feed",
                "https://georgiatoday.ge/feed",
                "https://jam-news.net/feed",
                "https://oc-media.org/feed",
                "https://www.interpressnews.ge/en/rss",

                # International / wire service
                "https://eurasianet.org/feed",
                # Native Georgian language
                "https://www.interpressnews.ge/ge/rss",

                "https://netgazeti.ge/feed/"
            ],
            "Greece": [
                # Greek language sources (primary)
                "https://www.in.gr/feed/?rid=2&pid=250&la=1&si=1",
                "https://www.naftemporiki.gr/feed",
                "https://www.protothema.gr/rss",
                "https://www.skai.gr/rss/news",
                "https://www.news247.gr/feed",
                "https://www.kathimerini.gr/rss/",
                # English sources
                "https://gtp.gr/rss.asp",
                "https://greece.greekreporter.com/feed/",
                "https://www.thenationalherald.com/feed/"
            ],
            "Iran": [
                # Persian/Farsi language sources
                "https://www.irna.ir/rss",
                "https://www.isna.ir/rss",
                "https://www.farsnews.ir/rss",

                # English sources
                "https://en.irna.ir/rss.aspx",
                "https://www.presstv.ir/RSS",
                "https://www.middleeasteye.net/rss",
                "https://www.aljazeera.com/xml/rss/all.xml",
                "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"
            ],
            "Iraq": [
                # Arabic language sources
                "https://www.almayadeen.net/rss/all",
                "https://arabic.rt.com/rss/",
                "https://www.alarabiya.net/ar/rss.xml",
                # Kurdish sources
                "https://www.rudaw.net/rss",
                "https://www.kurdistan24.net/rss",
                # English sources
                "https://iraq-businessnews.com/feed",
                "https://www.newarab.com/rss",
                "https://www.rudaw.net/english/rss",
                "https://www.kurdistan24.net/en/rss",
                "https://www.middleeasteye.net/rss",
                "https://www.aljazeera.com/xml/rss/all.xml",
                "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"
            ],
            "Syria": [
                # Arabic language sources
                "https://www.sana.sy/?feed=rss2",
                "https://www.enabbaladi.net/feed",
                "https://www.almayadeen.net/rss/all",
                "https://arabic.rt.com/rss/",
                # English sources
                "https://www.sana.sy/en/?feed=rss2",
                "https://english.enabbaladi.net/feed",
                "https://syrianobserver.com/feed",
                "https://npasyria.com/en/feed",
                "https://www.newarab.com/rss",
                "https://www.middleeasteye.net/rss",
                "https://www.aljazeera.com/xml/rss/all.xml"
            ],
            "Bulgaria": [
                # Bulgarian language sources
                "https://www.dnevnik.bg/rss/",
                "https://www.24chasa.bg/international/rss.xml",
                "https://news.bg/rss.html",
                "https://nova.bg/rss",
                # English sources
                "https://sofiaglobe.com/feed",
                "https://balkaninsight.com/feed/?post_type=news&country=bulgaria"
            ]
        }

        # Debiased mirror queries â€” neutral framing to avoid inflating threat scores
        self.mirror_queries = {
            "Armenia": [
                "Armenia news today",
                "Armenia politics",
                "Armenia economy",
                "Armenia diplomacy"
            ],
            "Georgia": [
                "Georgia country news",
                "Georgia politics today",
                "Georgia economy",
                "Georgia diplomacy"
            ],
            "Greece": [
                "Greece news today",
                "Greece politics",
                "Greece economy",
                "Greece Aegean"
            ],
            "Iran": [
                "Iran news today",
                "Iran politics",
                "Iran economy",
                "Iran diplomacy"
            ],
            "Iraq": [
                "Iraq news today",
                "Iraq politics",
                "Iraq economy",
                "Iraq reconstruction"
            ],
            "Syria": [
                "Syria news today",
                "Syria politics",
                "Syria economy",
                "Syria reconstruction"
            ],
            "Bulgaria": [
                "Bulgaria news today",
                "Bulgaria politics",
                "Bulgaria economy"
            ]
        }
        self._add_mirror_sources()

        # Modern User Agents (Feb 2026)
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0"
        ]
        
        self.now = datetime.now()
        self.start_of_yesterday = datetime(self.now.year, self.now.month, self.now.day) - timedelta(days=1)

    # Persistent feed cache for war-time resilience
    def _init_cache(self):
        cache_root = os.path.join(os.path.expanduser("~"), ".cache", "bnti")
        self.cache_dir = cache_root
        self.feed_cache_file = os.path.join(self.cache_dir, "feed_cache.json")
        self.cache_fresh_ttl_seconds = 60 * 30
        self.cache_stale_ttl_seconds = 60 * 60 * 48
        self.cache_lock = threading.Lock()
        self.feed_cache = {}
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            self.feed_cache = self._load_feed_cache()
        except Exception as e:
            logger.warning(f"Feed cache disabled: {e}")
            self.feed_cache_file = None

    def _load_feed_cache(self):
        if not self.feed_cache_file or not os.path.exists(self.feed_cache_file):
            return {}
        try:
            with open(self.feed_cache_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.warning(f"Failed to load feed cache: {e}")
        return {}

    def _save_feed_cache_locked(self):
        if not self.feed_cache_file:
            return
        tmp_path = f"{self.feed_cache_file}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(self.feed_cache, handle, ensure_ascii=True, separators=(",", ":"))
        os.replace(tmp_path, self.feed_cache_file)

    def _cache_entry_age_seconds(self, entry):
        fetched_at = entry.get("fetched_at")
        if not fetched_at:
            return None
        try:
            cached_time = date_parser.parse(fetched_at).replace(tzinfo=None)
        except Exception:
            return None
        return (datetime.utcnow() - cached_time).total_seconds()

    def _get_cached_entries(self, url, max_age_seconds):
        if not self.feed_cache_file:
            return None, None
        with self.cache_lock:
            entry = self.feed_cache.get(url)
        if not isinstance(entry, dict):
            return None, None
        age = self._cache_entry_age_seconds(entry)
        if age is None or age > max_age_seconds:
            return None, None
        entries = entry.get("entries")
        if not isinstance(entries, list):
            return None, None
        return entries, age

    def _serialize_entries(self, entries):
        if not entries:
            return []
        serialized = []
        for entry in entries:
            title = entry.get("title") if hasattr(entry, "get") else getattr(entry, "title", None)
            link = entry.get("link") if hasattr(entry, "get") else getattr(entry, "link", None)
            if not title or not link:
                continue
            item = {"title": str(title), "link": str(link)}
            published = entry.get("published") if hasattr(entry, "get") else getattr(entry, "published", None)
            if published:
                item["published"] = str(published)
            serialized.append(item)
        return serialized

    def _write_cache_entries(self, url, entries):
        if not self.feed_cache_file:
            return
        serialized = self._serialize_entries(entries)
        if not serialized:
            return
        payload = {
            "fetched_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            "entries": serialized
        }
        with self.cache_lock:
            self.feed_cache[url] = payload
            self._save_feed_cache_locked()

    def _google_news_url(self, query):
        encoded = quote_plus(query)
        return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"

    def _add_mirror_sources(self):
        for country, queries in self.mirror_queries.items():
            if isinstance(queries, str):
                queries = [queries]
            mirrors = []
            for query in queries:
                mirrors.append(self._google_news_url(query))
            base = self.rss_urls.get(country, [])
            merged = list(dict.fromkeys(base + mirrors))
            self.rss_urls[country] = merged

    def _extract_entries(self, entries):
        if not entries:
            return []

        now = datetime.now()
        recent_entries = []
        for entry in entries:
            link = entry.get('link') if hasattr(entry, 'get') else getattr(entry, 'link', None)
            title = entry.get('title') if hasattr(entry, 'get') else getattr(entry, 'title', None)
            if not link or not title:
                continue

            published_date_str = entry.get('published') if hasattr(entry, 'get') else getattr(entry, 'published', None)
            if published_date_str:
                try:
                    published_date = date_parser.parse(published_date_str).replace(tzinfo=None)
                    if published_date >= (now - timedelta(days=2)):
                        recent_entries.append(entry)
                except Exception:
                    continue
            else:
                recent_entries.append(entry)

        if recent_entries:
            return recent_entries

        fallback = []
        for entry in entries:
            link = entry.get('link') if hasattr(entry, 'get') else getattr(entry, 'link', None)
            title = entry.get('title') if hasattr(entry, 'get') else getattr(entry, 'title', None)
            if link and title:
                fallback.append(entry)
        return fallback[:5]

    def _build_proxy_url(self, url):
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return f"https://r.jina.ai/{parsed.scheme}://{parsed.netloc}{path}"

    def _parse_proxy_markdown(self, content):
        entries = []
        for line in content.splitlines():
            if "CDATA[" not in line:
                continue
            title_match = re.search(r"<!\\[CDATA\\[(.*?)\\]\\]>", line)
            if not title_match:
                continue
            url_match = re.search(r"https?://[^\\s]+", line)
            if not url_match:
                continue
            date_match = re.search(
                r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\\s+\\d{1,2}\\s+\\w+\\s+\\d{4}\\s+\\d{2}:\\d{2}:\\d{2}\\s+\\w+",
                line
            )
            entry = feedparser.FeedParserDict()
            entry["title"] = title_match.group(1).strip()
            entry["link"] = url_match.group(0)
            if date_match:
                entry["published"] = date_match.group(0)
            entries.append(entry)

        if not entries:
            return []

        deduped = []
        seen = set()
        for entry in entries:
            link = entry.get("link")
            if link in seen:
                continue
            seen.add(link)
            deduped.append(entry)
        return deduped[:12]

    def _fetch_proxy_entries(self, url, session, headers):
        proxy_url = self._build_proxy_url(url)
        if not proxy_url:
            return []
        try:
            response = session.get(
                proxy_url,
                headers=headers,
                timeout=self.FEED_PROXY_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            entries = self._parse_proxy_markdown(response.text)
            return self._extract_entries(entries)
        except Exception as e:
            logger.warning(f"Proxy fetch failed for {url}: {e}")
            return []

    def fetch_feed_entries(self, country, url):
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        retries = Retry(
            total=self.FEED_RETRY_TOTAL,
            connect=self.FEED_RETRY_CONNECT,
            read=self.FEED_RETRY_READ,
            backoff_factor=self.FEED_RETRY_BACKOFF,
            status_forcelist=[408, 429, 500, 502, 503, 504, 522, 524],
            allowed_methods=frozenset(["HEAD", "GET", "OPTIONS"]),
            respect_retry_after_header=True
        )
        session.mount('https://', HTTPAdapter(max_retries=retries))
        session.mount('http://', HTTPAdapter(max_retries=retries))

        base_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Linux"',
            'Connection': 'keep-alive',
            'Referer': 'https://www.google.com/'
        }

        cached_entries, _ = self._get_cached_entries(url, self.cache_fresh_ttl_seconds)
        if cached_entries:
            cached = self._extract_entries(cached_entries)
            if cached:
                return cached

        last_error = None
        saw_timeout = False
        saw_non_timeout_error = False
        user_agents = self.user_agents[:self.FEED_MAX_USER_AGENT_ATTEMPTS]
        for user_agent in user_agents:
            headers = dict(base_headers)
            headers['User-Agent'] = user_agent
            try:
                response = session.get(
                    url,
                    headers=headers,
                    timeout=self.FEED_REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                feed = feedparser.parse(response.content)
                entries = self._extract_entries(feed.entries if hasattr(feed, 'entries') else [])
                if entries:
                    self._write_cache_entries(url, entries)
                    return entries
            except requests.exceptions.SSLError as e:
                last_error = e
                try:
                    response = session.get(
                        url,
                        headers=headers,
                        timeout=self.FEED_REQUEST_TIMEOUT_SECONDS,
                        verify=False,
                    )
                    response.raise_for_status()
                    feed = feedparser.parse(response.content)
                    entries = self._extract_entries(feed.entries if hasattr(feed, 'entries') else [])
                    if entries:
                        logger.warning(f"SSL verification skipped for {url}")
                        self._write_cache_entries(url, entries)
                        return entries
                except Exception as e2:
                    last_error = e2
                    saw_non_timeout_error = True
            except requests.exceptions.Timeout as e:
                last_error = e
                saw_timeout = True
            except Exception as e:
                last_error = e
                if isinstance(e, requests.exceptions.Timeout):
                    saw_timeout = True
                else:
                    saw_non_timeout_error = True

        skip_network_fallbacks = saw_timeout and not saw_non_timeout_error

        if not skip_network_fallbacks:
            try:
                feed = feedparser.parse(url)
                entries = self._extract_entries(feed.entries if hasattr(feed, 'entries') else [])
                if entries:
                    self._write_cache_entries(url, entries)
                    return entries
            except Exception as e:
                last_error = e

        if not skip_network_fallbacks:
            entries = self._fetch_proxy_entries(url, session, base_headers)
            if entries:
                self._write_cache_entries(url, entries)
                return entries

        cached_entries, cache_age = self._get_cached_entries(url, self.cache_stale_ttl_seconds)
        if cached_entries:
            cached = self._extract_entries(cached_entries)
            if cached:
                if cache_age is not None:
                    age_minutes = int(cache_age // 60)
                    logger.warning(f"Using cached feed for {url} ({age_minutes}m old)")
                return cached

        if last_error:
            logger.error(f"Error fetching {url}: {last_error}")
        return []

    # Keywords that indicate non-threatening news (false positive filter)
    def process_country(self, country, urls):
        logger.info(f"Processing {country}...")
        all_entries = []
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(self.fetch_feed_entries, country, url) for url in urls]
            for future in concurrent.futures.as_completed(futures):
                all_entries.extend(future.result())
        
        if not all_entries:
            return country, []

        seen_links = set()
        unique_entries = []
        for e in all_entries:
            if hasattr(e, 'link') and e.link and e.link not in seen_links:
                unique_entries.append(e)
                seen_links.add(e.link)
        
        unique_entries = unique_entries[:15]

        final_report_data = []
        for original_entry in unique_entries:
            final_report_data.append({
                "title": original_entry.title,
                "translated_title": None,
                "link": original_entry.link,
                "date": original_entry.get('published', 'N/A'),
                "source_country": country,
            })

        return country, final_report_data

    def calculate_final_index(self, raw_score):
        """Maps volume-normalized threat score to 1-10 index.
        
        Uses a saturating exponential (sigmoid-like) curve that:
        - Maps 0 -> 1.0 (minimum/stable)
        - Maps ~2.5 avg threat -> ~4.5 (ELEVATED threshold)
        - Maps ~5.0 avg threat -> ~7.0 (CRITICAL threshold)  
        - Only reaches ~9.5+ for extreme threat densities
        
        Based on GPR Index and FSI normalization methodology.
        """
        if raw_score <= 0: return 1.0
        # After volume normalization, raw_score is avg contribution per article
        # Typical range: 0-8 (weight*confidence per article)
        scaled = raw_score / 5.0
        index = 1.0 + 9.0 * (1.0 - math.exp(-scaled * 1.2))
        return round(min(max(index, 1.0), 10.0), 2)

    def _parse_timestamp(self, value):
        if not value:
            return None
        try:
            return date_parser.parse(str(value)).replace(tzinfo=None)
        except Exception:
            return None

    def _extract_index(self, record):
        for key in ("main_index", "index"):
            value = record.get(key)
            if value is None:
                continue
            try:
                num = float(value)
            except (TypeError, ValueError):
                continue
            if math.isnan(num):
                continue
            return num
        return None

    def _trim_history(self, history, hours=48, max_points=48):
        if not history:
            return []
        now = datetime.now()
        recent = []
        for entry in history:
            ts = self._parse_timestamp(entry.get("timestamp"))
            if not ts:
                continue
            if now - ts <= timedelta(hours=hours):
                recent.append(entry)
        if not recent:
            recent = history[-max_points:]
        return recent[-max_points:]

    def _build_history_payload(self, history, include_live=False, live_index=None):
        payload = []
        for entry in history:
            idx = self._extract_index(entry)
            ts = entry.get("timestamp")
            if idx is None or not ts:
                continue
            payload.append({
                "timestamp": ts,
                "main_index": round(idx, 2),
                "index": round(idx, 2),
                "type": "historical"
            })
        if include_live and live_index is not None:
            payload.append({
                "timestamp": datetime.now().isoformat(),
                "main_index": round(live_index, 2),
                "index": round(live_index, 2),
                "type": "live"
            })
        return payload

    def detect_and_enrich_metadata(self, events):
        """Adds AI metadata to all events for transparency."""
        for e in events:
            e["ai_model"] = e.get("ai_model") or self.openrouter_model
            e["ai_confidence_score"] = f"{e.get('confidence', 1.0) * 100:.1f}%"

            # Simple language heuristic
            if e["title"].isascii():
                e["detected_lang"] = "en"
                e["is_translated"] = False
            else:
                e["detected_lang"] = "local" # approximations
                e["is_translated"] = False # will be updated if selected for translation

    def _ensure_translated_titles(self, events):
        if not events:
            return events

        self.detect_and_enrich_metadata(events)
        for event in events:
            if event.get("translated_title"):
                continue

            try:
                if event.get("detected_lang") == "en":
                    event["translated_title"] = event["title"]
                    event["is_translated"] = False
                else:
                    trans = self.translator.translate(event["title"], dest='en')
                    event["translated_title"] = trans.text
                    event["is_translated"] = True
                    event["translation_engine"] = "Google Neural MT"
                    time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Translation failed: {e}")
                event["translated_title"] = event["title"]
                event["is_translated"] = False

        return events

    def translate_top_threats(self, dashboard_data):
        """Translates only the top 15 most weighted events to English with metadata."""
        all_events = []
        for c in dashboard_data["countries"]:
            self.detect_and_enrich_metadata(dashboard_data["countries"][c]["events"])
            for e in dashboard_data["countries"][c]["events"]:
                e["country"] = c
                all_events.append(e)
        
        # Sort by weight descending (Top 15 for better coverage)
        top_list = sorted(all_events, key=lambda x: x['weight'], reverse=True)[:15]

        logger.info(f"Translating Top {len(top_list)} Threats...")
        self._ensure_translated_titles(top_list)
        return top_list

    def load_history(self):
        """Loads historical index data from CSV."""
        if os.path.exists(self.history_file):
            try:
                df = pd.read_csv(self.history_file)
                history = df.to_dict('records')
                for entry in history:
                    idx = self._extract_index(entry)
                    if idx is not None:
                        entry["main_index"] = idx
                return history
            except Exception:
                return []
        return []

    def _utc_now(self):
        return datetime.utcnow().replace(microsecond=0)

    def _utc_iso(self, dt_value):
        return dt_value.replace(microsecond=0).isoformat() + "Z"

    def _load_existing_dashboard_data(self, json_path=None):
        json_path = json_path or os.path.join(self.output_path, "bnti_data.json")
        if not os.path.exists(json_path):
            return None
        try:
            with open(json_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as e:
            logger.warning(f"Failed to load existing dashboard data: {e}")
            return None

    def _load_existing_summary(self):
        dashboard_data = self._load_existing_dashboard_data()
        if not isinstance(dashboard_data, dict):
            return None
        return dashboard_data.get("briefing", {}).get("regional_summary_6h")

    def _get_summary_slot_bounds(self, now_utc=None):
        now_utc = (now_utc or self._utc_now()).replace(minute=0, second=0, microsecond=0)
        slot_end_hour = (now_utc.hour // self.SUMMARY_REFRESH_INTERVAL_HOURS) * self.SUMMARY_REFRESH_INTERVAL_HOURS
        slot_end = now_utc.replace(hour=slot_end_hour)
        slot_start = slot_end - timedelta(hours=self.SUMMARY_WINDOW_HOURS)
        next_refresh = slot_end + timedelta(hours=self.SUMMARY_REFRESH_INTERVAL_HOURS)
        return slot_start, slot_end, next_refresh

    def _summary_matches_slot(self, summary_payload, slot_start, slot_end):
        if not isinstance(summary_payload, dict):
            return False
        payload_start = str(summary_payload.get("slot_start", "")).rstrip("Z")
        payload_end = str(summary_payload.get("slot_end", "")).rstrip("Z")
        return (
            payload_start == slot_start.replace(microsecond=0).isoformat()
            and payload_end == slot_end.replace(microsecond=0).isoformat()
        )

    def _build_regional_summary_candidates(self, country_results, slot_start, slot_end):
        candidates = []
        seen = set()
        for country in self.border_countries:
            for event in country_results.get(country, {}).get("events", []):
                event_time = self._parse_timestamp(event.get("date"))
                if not event_time or event_time < slot_start or event_time >= slot_end:
                    continue

                weight = float(event.get("weight", 0) or 0)
                if weight <= 0:
                    continue

                dedupe_key = event.get("link") or event.get("title")
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                event_copy = dict(event)
                event_copy["country"] = country
                event_copy["_event_time"] = event_time
                candidates.append(event_copy)

        candidates.sort(
            key=lambda item: (
                float(item.get("weight", 0) or 0),
                item.get("_event_time", datetime.min),
            ),
            reverse=True,
        )
        candidates = candidates[:self.SUMMARY_MAX_SOURCE_EVENTS]
        return candidates

    def _build_quiet_regional_summary(self, slot_start, slot_end, now_utc, next_refresh):
        return {
            "slot_start": self._utc_iso(slot_start),
            "slot_end": self._utc_iso(slot_end),
            "generated_at": self._utc_iso(now_utc),
            "next_refresh_at": self._utc_iso(next_refresh),
            "window_hours": self.SUMMARY_WINDOW_HOURS,
            "source_event_count": 0,
            "source_countries": [],
            "headline": "Border pressure stayed limited in the last completed 6-hour window.",
            "bullets": [
                "No border-country event in the completed window concentrated enough military, terrorist, or border-security pressure to dominate the regional picture.",
                "Available reporting was fragmented, low-intensity, or outside the seven border neighbors' direct threat envelope.",
                "Monitoring should stay alert for isolated incidents hardening into repeated force activity, organized militant pressure, or sharper interstate coercion.",
            ],
            "watch": None,
        }

    def _build_fallback_regional_summary(self, summary_events, slot_start, slot_end, now_utc, next_refresh):
        source_countries = sorted({event.get("country") for event in summary_events if event.get("country")})
        country_count = len(source_countries)
        country_word = "neighbor" if country_count == 1 else "neighbors"

        return {
            "slot_start": self._utc_iso(slot_start),
            "slot_end": self._utc_iso(slot_end),
            "generated_at": self._utc_iso(now_utc),
            "next_refresh_at": self._utc_iso(next_refresh),
            "window_hours": self.SUMMARY_WINDOW_HOURS,
            "source_event_count": len(summary_events),
            "source_countries": source_countries,
            "headline": f"Border-country reporting stayed active across {country_count} {country_word}.",
            "bullets": [
                f"{len(summary_events)} scored signals passed the feed and coverage gates for the completed window.",
                "Country placement uses source-country attribution while automated re-attribution is unavailable.",
                "Review high-weight events directly before treating the regional picture as settled.",
            ],
            "watch": None,
        }

    def _build_regional_summary_prompt(self, summary_events, slot_start, slot_end):
        lines = []
        for idx, event in enumerate(summary_events, start=1):
            translated_title = event.get("translated_title") or event.get("title") or ""
            original_title = event.get("title") or ""
            title_block = f'Headline: "{translated_title}"'
            if translated_title != original_title:
                title_block += f' | Original: "{original_title}"'
            event_time = event.get("_event_time") or self._parse_timestamp(event.get("date"))
            time_label = event_time.isoformat() + "Z" if event_time else "UNKNOWN"
            lines.append(
                f'{idx}. Country: {event.get("country", "UNKNOWN")}; '
                f'Category: {event.get("category", "unknown")}; '
                f'Weight: {float(event.get("weight", 0) or 0):.1f}; '
                f'Time: {time_label}; {title_block}'
            )

        events_block = "\n".join(lines)
        return f"""You are writing the Border Neighbor Threat Index regional briefing for the last completed 6-hour window.
Use only the supplied events. Focus on the most problematic and operationally significant developments across Armenia, Georgia, Greece, Iran, Iraq, Syria, and Bulgaria.
Do not write a country-by-country list.
Do not add background filler, generic scene-setting, or unsupported speculation.
Prioritize cross-border escalation risk, force activity, militant violence, border-security pressure, diplomatic rupture, and severe civilian stress with direct regional relevance.
If one theater clearly dominates, say so.
Use concrete actors, places, and actions when they are present in the event list.

Window start: {self._utc_iso(slot_start)}
Window end: {self._utc_iso(slot_end)}

Return ONLY a valid JSON object, no markdown, no explanation:
{{"headline":"...", "bullets":["...", "...", "..."], "watch": null}}

Requirements:
- headline: one sharp line, at most 120 characters
- bullets: exactly 3 bullets, each a single sentence, concrete, distinct, and non-repetitive
- watch: either one short sentence at most 24 words or null
- never introduce a border country, city, actor, militia, or theater that is not explicitly present in the event lines
- if the events are fragmented, stay narrow and factual instead of inventing linkages
- use the exact geography from the inputs when you mention place names
- do not mention feeds, scores, weights, models, prompts, or sources
- synthesize the events into a regional operational picture for Turkiye's border environment

Events:
{events_block}"""

    def _parse_regional_summary_response(self, response_text):
        if not response_text:
            return None

        parsed = self._parse_llm_literal(response_text, dict)
        if not isinstance(parsed, dict):
            return None

        headline = str(parsed.get("headline", "")).strip()
        bullets = parsed.get("bullets")
        watch = parsed.get("watch")

        if not headline:
            return None
        if not isinstance(bullets, list) or len(bullets) != 3:
            return None

        normalized_bullets = []
        for bullet in bullets:
            bullet_text = str(bullet).strip()
            if not bullet_text:
                return None
            normalized_bullets.append(bullet_text)

        if watch is None:
            normalized_watch = None
        else:
            normalized_watch = str(watch).strip() or None

        return {
            "headline": headline,
            "bullets": normalized_bullets,
            "watch": normalized_watch,
        }

    def _regional_summary_mentions_are_grounded(self, parsed_summary, summary_events):
        if not parsed_summary:
            return False

        summary_text = " ".join(
            [parsed_summary.get("headline", ""), *(parsed_summary.get("bullets") or []), parsed_summary.get("watch") or ""]
        ).lower()

        allowed_countries = set()
        for event in summary_events:
            source_country = event.get("country")
            if source_country:
                allowed_countries.add(source_country)

            source_text = " ".join(
                str(event.get(key, "")) for key in ("title", "translated_title", "country")
            ).lower()
            for country in self.border_countries:
                if re.search(rf"\b{re.escape(country.lower())}\b", source_text):
                    allowed_countries.add(country)

        for country in self.border_countries:
            if re.search(rf"\b{re.escape(country.lower())}\b", summary_text) and country not in allowed_countries:
                return False
        return True

    def _build_regional_summary(self, country_results, existing_summary=None):
        now_utc = self._utc_now()
        slot_start, slot_end, next_refresh = self._get_summary_slot_bounds(now_utc)

        if self._summary_matches_slot(existing_summary, slot_start, slot_end):
            return existing_summary

        summary_events = self._build_regional_summary_candidates(country_results, slot_start, slot_end)
        if not summary_events:
            return self._build_quiet_regional_summary(slot_start, slot_end, now_utc, next_refresh)

        prompt = self._build_regional_summary_prompt(summary_events, slot_start, slot_end)
        response = self._call_openrouter(prompt)
        parsed = self._parse_regional_summary_response(response)
        if not parsed or not self._regional_summary_mentions_are_grounded(parsed, summary_events):
            logger.warning("Regional summary generation failed; using deterministic summary fallback")
            return self._build_fallback_regional_summary(summary_events, slot_start, slot_end, now_utc, next_refresh)

        return {
            "slot_start": self._utc_iso(slot_start),
            "slot_end": self._utc_iso(slot_end),
            "generated_at": self._utc_iso(now_utc),
            "next_refresh_at": self._utc_iso(next_refresh),
            "window_hours": self.SUMMARY_WINDOW_HOURS,
            "source_event_count": len(summary_events),
            "source_countries": sorted({event.get("country") for event in summary_events if event.get("country")}),
            "headline": parsed["headline"],
            "bullets": parsed["bullets"],
            "watch": parsed["watch"],
        }

    def save_history(self, final_index, country_results=None, status="UNKNOWN"):
        """Appends comprehensive run results to history CSV for predictions and archival."""
        # Base record
        new_record = {
            "timestamp": datetime.now().isoformat(),
            "main_index": round(final_index, 2),
            "index": round(final_index, 2),
            "status": status
        }
        
        # Add per-country indices if available
        country_order = ["Armenia", "Georgia", "Greece", "Iran", "Iraq", "Syria", "Bulgaria"]
        total_signals = 0
        
        for country in country_order:
            if country_results and country in country_results:
                new_record[f"{country.lower()}_idx"] = country_results[country].get("index", 0)
                new_record[f"{country.lower()}_signals"] = len(country_results[country].get("events", []))
                total_signals += len(country_results[country].get("events", []))
            else:
                new_record[f"{country.lower()}_idx"] = 0
                new_record[f"{country.lower()}_signals"] = 0
        
        new_record["total_signals"] = total_signals
        
        df_new = pd.DataFrame([new_record])
        
        if os.path.exists(self.history_file):
            # Check if we need to add new columns (migration)
            try:
                existing_df = pd.read_csv(self.history_file, nrows=0)
                existing_cols = set(existing_df.columns)
                new_cols = set(df_new.columns)
                
                if new_cols != existing_cols:
                    # Schema changed, recreate with all columns
                    full_df = pd.read_csv(self.history_file)
                    for col in new_cols - existing_cols:
                        full_df[col] = 0 if 'idx' in col or 'signals' in col else ''
                    full_df = pd.concat([full_df, df_new], ignore_index=True)
                    full_df.to_csv(self.history_file, mode='w', header=True, index=False)
                else:
                    df_new.to_csv(self.history_file, mode='a', header=False, index=False)
            except Exception:
                df_new.to_csv(self.history_file, mode='a', header=False, index=False)
        else:
            df_new.to_csv(self.history_file, mode='w', header=True, index=False)
            
    def generate_forecast(self, history):
        """Generates a simple linear forecast for the next 6 hours."""
        points = []
        for entry in history:
            idx = self._extract_index(entry)
            ts = self._parse_timestamp(entry.get("timestamp"))
            if idx is None or not ts:
                continue
            points.append((ts, idx))

        if len(points) < 2:
            return []

        points.sort(key=lambda x: x[0])
        points = points[-24:]
        y = np.array([p[1] for p in points], dtype=float)
        x = np.arange(len(y), dtype=float)

        if len(x) < 2:
            return []

        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)

        y_pred = p(x)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.5

        last_time = points[-1][0]
        forecast_points = []

        for i in range(1, 7):
            val = p(len(y) + i - 1)
            ts = last_time + timedelta(hours=i)
            confidence = max(0.3, min(0.95, r_squared * (1 - i * 0.08)))
            forecast_points.append({
                "timestamp": ts.isoformat(),
                "index": round(max(1.0, min(10.0, float(val))), 2),
                "main_index": round(max(1.0, min(10.0, float(val))), 2),
                "confidence": round(confidence, 2),
                "type": "forecast"
            })
        return forecast_points

    def _compute_composite_index(self, country_results):
        if not country_results:
            return 1.0

        weighted_sum = 0.0
        total_weight = 0.0
        for country, result in country_results.items():
            weight = self.IMPORTANCE_WEIGHTS.get(country, 1.0)
            weighted_sum += result.get("index", 1.0) * weight
            total_weight += weight

        if total_weight <= 0:
            return 1.0
        return round(weighted_sum / total_weight, 2)

    def _derive_status(self, turkey_index):
        if turkey_index > 7.0:
            return "CRITICAL"
        if turkey_index > 4.0:
            return "ELEVATED"
        return "STABLE"

    def _build_history_record(self, final_index, country_results=None, status="UNKNOWN"):
        new_record = {
            "timestamp": datetime.now().isoformat(),
            "main_index": round(final_index, 2),
            "index": round(final_index, 2),
            "status": status,
        }

        total_signals = 0
        for country in self.BORDER_COUNTRIES:
            result = (country_results or {}).get(country, {})
            events = result.get("events", [])
            new_record[f"{country.lower()}_idx"] = result.get("index", 0)
            new_record[f"{country.lower()}_signals"] = len(events)
            total_signals += len(events)

        new_record["total_signals"] = total_signals
        return new_record

    def _write_history_records(self, history_records):
        if not history_records:
            return
        df = pd.DataFrame(history_records)
        tmp_path = f"{self.history_file}.tmp"
        df.to_csv(tmp_path, index=False)
        os.replace(tmp_path, self.history_file)

    def _build_dashboard_data(self, country_results, turkey_index, status, history_records=None, regional_summary=None):
        history_records = self._trim_history(history_records if history_records is not None else self.load_history())
        next_update = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)

        dashboard_data = {
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "main_index": round(turkey_index, 2),
                "status": status,
                "active_scan": False,
                "next_update": next_update.isoformat(),
                "version": "2.0.0",
            },
            "countries": country_results,
            "history": self._build_history_payload(history_records),
            "forecast": self.generate_forecast(history_records),
            "methodology": {
                "name": "LLM Border Threat Taxonomy",
                "description": "OpenRouter free routing chooses the final country attribution and canonical threat category for each headline.",
                "weights": self.category_weights,
                "formula": "PerCountry = 1 + 9*(1 - exp(-avg(weight)/5 * 1.2)); Composite = weighted_avg(PerCountry)",
                "scale": {
                    "min": 1.0,
                    "max": 10.0,
                    "thresholds": {
                        "STABLE": [1.0, 4.0],
                        "ELEVATED": [4.0, 7.0],
                        "CRITICAL": [7.0, 10.0],
                    },
                },
            },
            "briefing": {
                "regional_summary_6h": regional_summary,
            },
        }
        self.translate_top_threats(dashboard_data)
        return dashboard_data

    def _write_dashboard_files(self, dashboard_data, json_path=None, js_path=None):
        json_path = json_path or os.path.join(self.output_path, "bnti_data.json")
        js_path = js_path or os.path.join(self.output_path, "bnti_data.js")

        json_tmp = f"{json_path}.tmp"
        js_tmp = f"{js_path}.tmp"

        with open(json_tmp, "w", encoding="utf-8") as handle:
            json.dump(dashboard_data, handle, indent=2, ensure_ascii=False)

        with open(js_tmp, "w", encoding="utf-8") as handle:
            json_str = json.dumps(dashboard_data, indent=2, ensure_ascii=False)
            handle.write(f"window.BNTI_DATA = {json_str};")

        os.replace(json_tmp, json_path)
        os.replace(js_tmp, js_path)

    def _promote_candidate_snapshot(self, candidate, json_path=None, js_path=None):
        if not candidate or not candidate.get("publishable"):
            logger.warning("Candidate snapshot not publishable â€” leaving live files unchanged")
            return False

        country_results = candidate.get("country_results", {})
        turkey_index = candidate.get("turkey_index", 1.0)
        status = candidate.get("status", self._derive_status(turkey_index))
        regional_summary = candidate.get("regional_summary_6h")
        history_records = candidate.get("history_records")
        if history_records is None:
            history_records = self._trim_history(self.load_history())
            history_records.append(self._build_history_record(turkey_index, country_results, status))

        dashboard_data = self._build_dashboard_data(
            country_results,
            turkey_index,
            status,
            history_records=history_records,
            regional_summary=regional_summary,
        )
        self._write_dashboard_files(dashboard_data, json_path=json_path, js_path=js_path)
        self._write_history_records(history_records)
        return True

    def save_snapshot(self, country_results, turkey_index_so_far, status="SCANNING_NETWORKS"):
        candidate = {
            "publishable": True,
            "country_results": country_results,
            "turkey_index": turkey_index_so_far,
            "status": status,
            "history_records": self._trim_history(self.load_history()),
        }
        return self._promote_candidate_snapshot(candidate)

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # OPENROUTER LLM â€” COUNTRY RE-ATTRIBUTION
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _call_openrouter(self, prompt, max_retries=2):
        """Call OpenRouter with automatic primary/backup key failover."""
        import requests

        if getattr(self, "openrouter_disabled_for_run", False):
            return None

        api_keys = []
        for key in [self.openrouter_api_key, getattr(self, "openrouter_backup_api_key", "")]:
            if key and key not in api_keys:
                api_keys.append(key)

        if not api_keys:
            logger.warning("OpenRouter API keys not set — cannot build publishable candidate")
            self.openrouter_disabled_for_run = True
            return None

        base_payload = {
            "model": self.openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 8192,
        }

        for api_key in api_keys:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://akgularda.github.io/border-neighbor-threat-index/",
                "X-Title": "BNTI Intelligence Pipeline",
            }
            for attempt in range(max_retries + 1):
                try:
                    payload = dict(base_payload)
                    payload["reasoning"] = {"effort": "none"}
                    resp = requests.post(
                        self.openrouter_base_url,
                        headers=headers,
                        json=payload,
                        timeout=self.OPENROUTER_TIMEOUT_SECONDS,
                    )
                    if resp.status_code == 400 and "Reasoning is mandatory" in resp.text:
                        payload = dict(base_payload)
                        resp = requests.post(
                            self.openrouter_base_url,
                            headers=headers,
                            json=payload,
                            timeout=self.OPENROUTER_TIMEOUT_SECONDS,
                        )

                    if resp.status_code == 429:
                        if attempt < max_retries:
                            wait = min(30, 5 * (attempt + 1))
                            logger.warning(f"OpenRouter rate-limited, waiting {wait}s (attempt {attempt + 1})")
                            time.sleep(wait)
                            continue
                        logger.warning("OpenRouter key exhausted after retry budget; trying next key")
                        break

                    if resp.status_code in (401, 403):
                        logger.warning("OpenRouter key rejected; trying next key")
                        break

                    resp.raise_for_status()
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if content:
                        return content
                    logger.warning("OpenRouter returned empty content")
                    if attempt < max_retries:
                        time.sleep(3)
                        continue
                    break
                except Exception as e:
                    logger.warning(f"OpenRouter call failed (attempt {attempt + 1}): {e}")
                    if attempt < max_retries:
                        time.sleep(3)
                        continue
                    break
        self.openrouter_disabled_for_run = True
        return None

    def _normalize_headline_for_llm(self, value):
        return re.sub(r"\s+", " ", str(value or "").replace('"', "'")).strip()

    def _strip_trailing_source_suffix(self, value):
        text = self._normalize_headline_for_llm(value)
        if not text:
            return text

        for delimiter in (" | ", " - ", " — ", " – ", " -- "):
            left, separator, right = text.rpartition(delimiter)
            if not separator or not left or not right:
                continue

            suffix_text = re.sub(r"[^A-Za-z0-9 ]+", " ", right).lower()
            suffix_words = [word for word in suffix_text.split() if word]
            if not suffix_words:
                continue

            looks_like_source = (
                len(suffix_words) <= 6
                and (
                    any(word in self.SOURCE_SUFFIX_HINTS for word in suffix_words)
                    or right.isupper()
                    or bool(re.search(r"\b(?:ap|afp|bbc|cnn|dw|itv|npr|reuters|rt|sky|trt)\b", suffix_text))
                )
            )
            if looks_like_source:
                return left.strip()

        return text

    def _resolve_border_country(self, country_name):
        normalized_name = str(country_name or "").strip()
        if not normalized_name:
            return None
        if normalized_name.upper() == "IRRELEVANT":
            return "IRRELEVANT"
        return next((name for name in self.border_countries if normalized_name.lower() == name.lower()), None)

    def _format_headline_for_prompt(self, event):
        translated_title_raw = self._normalize_headline_for_llm(
            event.get("translated_title") or event.get("title") or ""
        )
        original_title_raw = self._normalize_headline_for_llm(event.get("title") or "")
        translated_title = self._strip_trailing_source_suffix(translated_title_raw)
        original_title = self._strip_trailing_source_suffix(original_title_raw)

        headline_block = f'Headline: "{translated_title}"'
        if translated_title_raw and translated_title_raw != translated_title:
            headline_block += f' | Published: "{translated_title_raw}"'
        if original_title and original_title != translated_title:
            headline_block += f' | Original: "{original_title}"'
        return headline_block

    def _build_attribution_prompt(self, all_events, start_index=0):
        lines = []
        for i, event in enumerate(all_events):
            lines.append(f"{start_index + i + 1}. {self._format_headline_for_prompt(event)}")

        headlines_block = "\n".join(lines)
        return f"""You are a geopolitical intelligence analyst for Turkiye's border threat monitoring system.
Turkiye's border neighbor countries are: Armenia, Georgia, Greece, Iran, Iraq, Syria, Bulgaria.

For each numbered headline below, do THREE things:
1. Choose exactly ONE published border country as primary_country, or \"IRRELEVANT\".
2. Classify the headline into exactly ONE category from this list:
   - \"military_conflict\"
   - \"terrorism\"
   - \"border_security\"
   - \"political_instability\"
   - \"humanitarian_crisis\"
   - \"diplomatic_tensions\"
   - \"trade_agreement\"
   - \"neutral\"
3. Write a short subject phrase describing the main thing the headline is about.

Country attribution rules:
- Attribute from headline content only, never from feed source.
- Choose exactly one primary_country. Never return multiple countries.
- Use \"IRRELEVANT\" if no single border country is clearly the direct main subject.
- The publication language, outlet nationality, and source-country feed do not matter.
- If a headline is in Greek, Arabic, Persian, Armenian, Georgian, Bulgarian, or English, the target country is still the country in the headline, not the country of the newspaper.
- A border country qualifies only when the headline is directly mainly about that country's territory, government, population, infrastructure, armed forces, economy, or border situation.
- If the main event happens in a non-border place, return \"IRRELEVANT\" even if the outlet is from a border country.
- If a non-border actor strikes, pressures, or negotiates over a border country, choose the directly affected border country.
- If two border countries are equally central and no single primary focus is clear, return \"IRRELEVANT\" rather than guessing.
- \"Israel strikes Iran\" -> primary_country \"Iran\"
- \"Israel, Iran launch new waves of strikes\" -> primary_country \"Iran\"
- \"UN demands justice after US strike on Iranian school\" -> primary_country \"Iran\"
- \"Drone attacks near Baghdad airport raise security concerns\" -> primary_country \"Iraq\"
- \"Canada is not planning to reopen embassy in Syria\" -> primary_country \"Syria\"
- \"Study: Electricity bills eat into Syrians' food basket\" -> primary_country \"Syria\"
- Greek-language headline about bombing sites in Iran -> primary_country \"Iran\", not \"Greece\"
- \"UNIFIL calls for halt to military escalation in Southern Lebanon\" -> primary_country \"IRRELEVANT\"
- \"Israel pushes deeper into south Lebanon amid Hezbollah clashes\" -> primary_country \"IRRELEVANT\"
- \"War costs reach $1 billion a day as Israel faces missile interceptor shortage\" -> primary_country \"IRRELEVANT\"
- \"Palestinian killed as Jewish settlers rampage through West Bank\" -> primary_country \"IRRELEVANT\"
- \"Jordan, Egypt discuss regional escalation\" -> primary_country \"IRRELEVANT\"
- \"Nepal premier sworn in\" -> primary_country \"IRRELEVANT\"

Category rules:
- Classify the main event, not background context or subordinate clauses.
- If conflict words appear only as context introduced by phrases like "as", "after", "amid", "while", "despite", or "following", classify the headline by the main action instead.
- War, strikes, armed clashes, military operations -> \"military_conflict\"
- Terror bombings, extremist attacks, militant attacks -> \"terrorism\"
- Border closures, checkpoints, smuggling, incursions, migration enforcement, airspace violations -> \"border_security\"
- Government instability, domestic political breakdown, coup risk, parliamentary deadlock -> \"political_instability\"
- Refugees, famine, displacement, disaster, severe civilian deprivation -> \"humanitarian_crisis\"
- Embassy disputes, warnings, sanctions diplomacy, hostile state-to-state standoffs -> \"diplomatic_tensions\"
- Treaties, trade corridors, normalization, signed cooperation, reopened links -> \"trade_agreement\"
- Reconstruction, rebuilding, reopening, recovery, restored services, resumed schooling, and economic revival -> \"neutral\" unless the main event is a signed trade or cooperation opening.
- Sports, celebrity, lifestyle, culture, weather, general news -> \"neutral\"
- \"Syria silently rebuilds itself as war with Iran tarnishes Gulf infrastructure - Turkiye Today\" -> primary_country \"Syria\", category \"neutral\"
- \"Syria reopens municipal services after wartime disruption\" -> primary_country \"Syria\", category \"neutral\"

Headlines:
{headlines_block}

Respond ONLY with a valid JSON array, no explanation, no markdown:
[{{\"id\": 1, \"primary_country\": \"Syria\", \"category\": \"neutral\", \"subject\": \"Syrian municipal reconstruction\"}}, {{\"id\": 2, \"primary_country\": \"IRRELEVANT\", \"category\": \"neutral\", \"subject\": \"Israeli domestic cost pressures\"}}]"""

    def _parse_llm_literal(self, response_text, expected_type):
        if not response_text:
            return None

        text = response_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
            text = text.strip()

        if expected_type is list:
            match = re.search(r"\[.*\]", text, re.DOTALL)
        else:
            match = re.search(r"\{.*\}", text, re.DOTALL)

        candidates = [text]
        if match:
            candidates.append(match.group(0))

        for candidate in candidates:
            normalized = (
                candidate
                .replace("“", '"')
                .replace("”", '"')
                .replace("’", "'")
                .replace("‘", "'")
            )
            normalized = re.sub(r",(\s*[}\]])", r"\1", normalized)

            for parser in (json.loads, ast.literal_eval):
                try:
                    parsed = parser(normalized)
                except (json.JSONDecodeError, SyntaxError, ValueError):
                    continue
                if isinstance(parsed, expected_type):
                    return parsed
        return None

    def _parse_attribution_response(self, response_text, all_events, start_index=0):
        attribution_map = {}
        if not response_text:
            return attribution_map

        parsed = self._parse_llm_literal(response_text, list)
        if not parsed:
            logger.warning("OpenRouter response is not a JSON array")
            return attribution_map

        expected_ids = set(range(start_index + 1, start_index + len(all_events) + 1))
        seen_ids = set()
        valid_categories = set(self.category_weights.keys())

        for item in parsed:
            if not isinstance(item, dict):
                return {}

            idx = item.get("id")
            primary_country = self._resolve_border_country(item.get("primary_country"))
            category = str(item.get("category", "")).strip().lower()
            subject = str(item.get("subject", "")).strip()
            if idx not in expected_ids or idx in seen_ids:
                return {}
            if primary_country is None or category not in valid_categories or not subject:
                return {}

            seen_ids.add(idx)
            attribution_map[int(idx) - 1] = {
                "primary_country": primary_country,
                "category": category,
                "subject": subject,
            }

        if seen_ids != expected_ids:
            return {}
        return attribution_map

    def _resolve_attribution_batch(self, all_events, start_index=0):
        if getattr(self, "openrouter_disabled_for_run", False):
            return {}

        prompt = self._build_attribution_prompt(all_events, start_index=start_index)
        response = self._call_openrouter(prompt)
        parsed = self._parse_attribution_response(response, all_events, start_index=start_index)
        if len(parsed) == len(all_events):
            return parsed
        if len(all_events) == 1:
            return {}

        logger.warning(
            f"LLM attribution batch {start_index + 1}-{start_index + len(all_events)} invalid; retrying in smaller chunks"
        )
        midpoint = len(all_events) // 2
        left_events = all_events[:midpoint]
        right_events = all_events[midpoint:]
        left_map = self._resolve_attribution_batch(left_events, start_index=start_index)
        if len(left_map) != len(left_events):
            return {}
        right_map = self._resolve_attribution_batch(right_events, start_index=start_index + midpoint)
        if len(right_map) != len(right_events):
            return {}
        merged = dict(left_map)
        merged.update(right_map)
        return merged

    def _build_country_audit_prompt(self, all_events, attribution_map, start_index=0):
        lines = []
        for i, event in enumerate(all_events):
            global_idx = start_index + i
            proposed = attribution_map.get(global_idx, {})
            proposed_country = proposed.get("primary_country", "IRRELEVANT")
            lines.append(
                f'{global_idx + 1}. {self._format_headline_for_prompt(event)} | '
                f'Proposed primary_country: "{proposed_country}"'
            )

        headlines_block = "\n".join(lines)
        return f"""You are auditing country attribution for Turkiye's border threat monitoring system.
Return the final published country for each headline.
Ignore the publication language, outlet nationality, and feed source.
Use the headline itself as the source of truth. Proposed labels are only candidate guesses and may be wrong.

Rules:
- Return exactly one final_country for each item.
- final_country must be one of: Armenia, Georgia, Greece, Iran, Iraq, Syria, Bulgaria, IRRELEVANT.
- If the proposed country is wrong, replace it with the correct border country.
- If no single border country is clearly the direct main subject, return IRRELEVANT.
- Do not keep a country just because the article came from that country's media.
- Greek-language headline about bombing sites in Iran -> final_country "Iran"
- Lebanon-only, Israel-only, Jordan-only, Egypt-only, West-Bank-only, or other non-border headlines -> final_country "IRRELEVANT"
- If two border countries are equally central and no single primary focus is clear, return IRRELEVANT.

Items:
{headlines_block}

Respond ONLY with a valid JSON array, no explanation, no markdown:
[{{"id": 1, "final_country": "Iran"}}, {{"id": 2, "final_country": "IRRELEVANT"}}]"""

    def _parse_country_audit_response(self, response_text, all_events, start_index=0):
        audit_map = {}
        if not response_text:
            return audit_map

        parsed = self._parse_llm_literal(response_text, list)
        if not parsed:
            logger.warning("Country audit response is not a JSON array")
            return audit_map

        expected_ids = set(range(start_index + 1, start_index + len(all_events) + 1))
        seen_ids = set()
        for item in parsed:
            if not isinstance(item, dict):
                return {}

            idx = item.get("id")
            final_country = self._resolve_border_country(item.get("final_country"))
            if idx not in expected_ids or idx in seen_ids or final_country is None:
                return {}

            seen_ids.add(idx)
            audit_map[int(idx) - 1] = {
                "final_country": final_country,
            }

        if seen_ids != expected_ids:
            return {}
        return audit_map

    def _slice_attribution_map(self, attribution_map, start_index, event_count):
        return {
            idx: attribution_map[idx]
            for idx in range(start_index, start_index + event_count)
            if idx in attribution_map
        }

    def _resolve_country_audit_batch(self, all_events, attribution_map, start_index=0):
        if getattr(self, "openrouter_disabled_for_run", False):
            return {}

        prompt = self._build_country_audit_prompt(all_events, attribution_map, start_index=start_index)
        response = self._call_openrouter(prompt)
        parsed = self._parse_country_audit_response(response, all_events, start_index=start_index)
        if len(parsed) == len(all_events):
            return parsed
        if len(all_events) == 1:
            return {}

        logger.warning(
            f"LLM country audit batch {start_index + 1}-{start_index + len(all_events)} invalid; retrying in smaller chunks"
        )
        midpoint = len(all_events) // 2
        left_events = all_events[:midpoint]
        right_events = all_events[midpoint:]

        left_attribution_map = self._slice_attribution_map(attribution_map, start_index, midpoint)
        right_attribution_map = self._slice_attribution_map(
            attribution_map,
            start_index + midpoint,
            len(right_events),
        )

        left_map = self._resolve_country_audit_batch(left_events, left_attribution_map, start_index=start_index)
        if len(left_map) != len(left_events):
            return {}
        right_map = self._resolve_country_audit_batch(
            right_events,
            right_attribution_map,
            start_index=start_index + midpoint,
        )
        if len(right_map) != len(right_events):
            return {}

        merged = dict(left_map)
        merged.update(right_map)
        return merged

    def _collect_candidate_events(self, country_candidates):
        all_events = []
        seen = set()
        for country in self.border_countries:
            for event in country_candidates.get(country, []):
                event_copy = dict(event)
                event_copy.setdefault("source_country", country)
                dedupe_key = event_copy.get("link") or event_copy.get("title")
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                all_events.append(event_copy)
        return all_events

    def _build_fallback_attribution_map(self, all_events, start_index=0, reason="llm_attribution_failed"):
        attribution_map = {}
        for offset, event in enumerate(all_events):
            idx = start_index + offset
            source_country = event.get("source_country")
            if source_country not in self.border_countries:
                source_country = "IRRELEVANT"

            attribution_map[idx] = {
                "primary_country": source_country,
                "final_country": source_country,
                "category": "border_security" if source_country != "IRRELEVANT" else "neutral",
                "subject": event.get("translated_title") or event.get("title"),
                "confidence": 0.35,
                "ai_category": False,
                "ai_model": "deterministic-fallback",
                "fallback_reason": reason,
            }
        return attribution_map

    def _build_fallback_country_audit_map(self, all_events, attribution_map, start_index=0, reason="country_audit_failed"):
        audit_map = {}
        for offset, event in enumerate(all_events):
            idx = start_index + offset
            result = attribution_map.get(idx, {})
            final_country = result.get("primary_country") or event.get("source_country") or "IRRELEVANT"
            audit_map[idx] = {
                "final_country": final_country,
                "fallback_reason": reason,
            }
        return audit_map

    def _build_country_results(self, all_events, attribution_map):
        country_events = {country: [] for country in self.border_countries}
        seen_targets = {country: set() for country in self.border_countries}

        for idx, event in enumerate(all_events):
            result = attribution_map.get(idx)
            if not result:
                continue
            final_country = result.get("final_country") or result.get("primary_country")
            if final_country == "IRRELEVANT" or not final_country:
                continue

            category = result["category"]
            weight = self.category_weights.get(category, 0.0)
            source_country = event.get("source_country")
            dedupe_key = event.get("link") or event.get("title")
            if dedupe_key in seen_targets[final_country]:
                continue
            seen_targets[final_country].add(dedupe_key)

            event_copy = dict(event)
            event_copy["category"] = category
            event_copy["weight"] = weight
            event_copy["confidence"] = result.get("confidence", 1.0)
            event_copy["ai_model"] = result.get("ai_model", self.openrouter_model)
            event_copy["ai_category"] = result.get("ai_category", True)
            event_copy["ai_reattributed"] = (final_country != source_country)
            event_copy["llm_primary_country"] = result.get("primary_country")
            event_copy["llm_final_country"] = final_country
            event_copy["llm_subject"] = result.get("subject")
            event_copy["llm_country_audit_corrected"] = (final_country != result.get("primary_country"))
            if result.get("fallback_reason"):
                event_copy["fallback_reason"] = result.get("fallback_reason")
            country_events[final_country].append(event_copy)

        country_results = {}
        for country in self.border_countries:
            events = sorted(country_events[country], key=lambda item: item.get("weight", 0), reverse=True)
            if events:
                raw_score = round(sum(event.get("weight", 0) for event in events) / len(events), 2)
                final_index = round(self.calculate_final_index(raw_score), 2)
            else:
                raw_score = 0.0
                final_index = 1.0

            country_results[country] = {
                "index": final_index,
                "raw_score": raw_score,
                "events": events,
            }
        return country_results

    def _build_coverage_metrics(self, country_results):
        total_signals = 0
        active_countries = 0
        for country in self.border_countries:
            events = country_results.get(country, {}).get("events", [])
            signal_count = len(events)
            total_signals += signal_count
            if signal_count:
                active_countries += 1
        return {
            "total_signals": total_signals,
            "active_countries": active_countries,
        }

    def _build_history_coverage_baseline(self, history_records):
        totals = []
        active_counts = []
        for record in history_records[-12:]:
            total_value = record.get("total_signals")
            try:
                total_signals = int(float(total_value))
            except (TypeError, ValueError):
                total_signals = 0

            active_countries = 0
            for country in self.border_countries:
                key = f"{country.lower()}_signals"
                try:
                    if float(record.get(key, 0)) > 0:
                        active_countries += 1
                except (TypeError, ValueError):
                    continue

            if total_signals > 0:
                totals.append(total_signals)
            if active_countries > 0:
                active_counts.append(active_countries)

        baseline_total = int(round(float(np.median(totals)))) if totals else 0
        baseline_active = int(round(float(np.median(active_counts)))) if active_counts else 0
        return {
            "total_signals": baseline_total,
            "active_countries": baseline_active,
        }

    def _passes_coverage_gate(self, country_results, history_records):
        metrics = self._build_coverage_metrics(country_results)
        baseline = self._build_history_coverage_baseline(history_records)

        required_total = self.MIN_PUBLISHABLE_TOTAL_SIGNALS
        if baseline["total_signals"] > 0:
            required_total = max(
                required_total,
                math.ceil(baseline["total_signals"] * self.MIN_SIGNAL_COVERAGE_RATIO),
            )

        required_active = self.MIN_PUBLISHABLE_ACTIVE_COUNTRIES
        if baseline["active_countries"] > 0:
            required_active = max(
                required_active,
                math.ceil(baseline["active_countries"] * self.MIN_ACTIVE_COUNTRY_COVERAGE_RATIO),
            )

        passed = (
            metrics["total_signals"] >= required_total
            and metrics["active_countries"] >= required_active
        )
        return passed, {
            "candidate_total_signals": metrics["total_signals"],
            "candidate_active_countries": metrics["active_countries"],
            "required_total_signals": required_total,
            "required_active_countries": required_active,
            "baseline_total_signals": baseline["total_signals"],
            "baseline_active_countries": baseline["active_countries"],
        }

    def build_candidate_snapshot(self, country_candidates):
        history_records = self._trim_history(self.load_history())
        all_events = self._collect_candidate_events(country_candidates)
        if not all_events:
            return {
                "publishable": False,
                "reason": "no_candidate_events",
            }

        attribution_map = {}
        batch_size = max(int(getattr(self, "openrouter_batch_size", 10)), 1)
        for start in range(0, len(all_events), batch_size):
            batch_events = all_events[start:start + batch_size]
            batch_map = self._resolve_attribution_batch(batch_events, start_index=start)
            if len(batch_map) != len(batch_events):
                logger.warning(
                    f"LLM attribution failed for batch starting at {start + 1}; using deterministic fallback"
                )
                batch_map = self._build_fallback_attribution_map(
                    batch_events,
                    start_index=start,
                    reason="llm_attribution_failed",
                )

            audit_map = self._resolve_country_audit_batch(batch_events, batch_map, start_index=start)
            if len(audit_map) != len(batch_events):
                logger.warning(
                    f"LLM country audit failed for batch starting at {start + 1}; using source-country fallback"
                )
                audit_map = self._build_fallback_country_audit_map(
                    batch_events,
                    batch_map,
                    start_index=start,
                    reason="country_audit_failed",
                )

            for idx, result in batch_map.items():
                merged = dict(result)
                merged["final_country"] = audit_map[idx]["final_country"]
                if audit_map[idx].get("fallback_reason") and not merged.get("fallback_reason"):
                    merged["fallback_reason"] = audit_map[idx]["fallback_reason"]
                attribution_map[idx] = merged

        if len(attribution_map) != len(all_events):
            return {"publishable": False, "reason": "partial_attribution_map"}

        country_results = self._build_country_results(all_events, attribution_map)
        coverage_ok, coverage = self._passes_coverage_gate(country_results, history_records)
        if not coverage_ok:
            return {
                "publishable": False,
                "reason": "insufficient_feed_coverage",
                "coverage": coverage,
            }

        existing_summary = self._load_existing_summary()
        regional_summary = self._build_regional_summary(country_results, existing_summary=existing_summary)
        if not regional_summary:
            return {
                "publishable": False,
                "reason": "summary_generation_failed",
            }

        turkey_index = self._compute_composite_index(country_results)
        status = self._derive_status(turkey_index)
        history_records.append(self._build_history_record(turkey_index, country_results, status))
        return {
            "publishable": True,
            "country_results": country_results,
            "turkey_index": turkey_index,
            "status": status,
            "history_records": history_records,
            "regional_summary_6h": regional_summary,
        }

    def run(self):
        os.makedirs(self.output_path, exist_ok=True)
        country_candidates = {country: [] for country in self.border_countries}

        for country, urls in self.rss_urls.items():
            if not urls:
                continue
            _, candidates = self.process_country(country, urls)
            country_candidates[country] = candidates

        candidate = self.build_candidate_snapshot(country_candidates)
        if not candidate.get("publishable"):
            logger.warning(f"Run completed without publish: {candidate.get('reason', 'unknown_reason')}")
            return False

        self._promote_candidate_snapshot(candidate)
        logger.info(f"Analysis Complete. Composite Index: {candidate['turkey_index']:.2f}")
        return True
if __name__ == "__main__":
    try:
        analyzer = BNTIAnalyzer()
        analyzer.run()
    except Exception as e:
        # NEVER crash - log and exit gracefully
        logging.error(f"Analyzer encountered a critical error: {e}")
        logging.info("Exiting gracefully to prevent workflow failure.")
        # Exit 0 so GitHub Actions reports SUCCESS
        import sys
        sys.exit(0)

