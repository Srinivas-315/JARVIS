"""
JARVIS — skills/web_search.py
Real-time Web Search — fetches LIVE answers and speaks them.

Unlike browser.py (which just opens Chrome), this:
  1. Fetches actual web results silently in background
  2. Extracts the answer
  3. Speaks it to you — no browser window needed

Sources (in priority order):
  1. DuckDuckGo Instant Answers  (fast, no API key)
  2. Wikipedia Summary            (factual questions)
  3. Google Search scraping       (general fallback)
  4. Open browser                 (last resort)

Examples:
  "What is the current Bitcoin price?"  → speaks live price
  "Latest news about India"             → speaks top headlines
  "Who is Elon Musk?"                   → speaks Wikipedia summary
  "What time is it in New York?"        → speaks current time
  "How to reverse a string in Python?"  → speaks answer
"""

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime

from utils.logger import log

# Headers to mimic a real browser
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

# DuckDuckGo Instant Answer API (no key needed)
DDG_API = "https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"

# Wikipedia API
WIKI_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

# Request timeout
TIMEOUT = 8


class WebSearch:
    """
    Real-time web search — fetches live answers silently.
    No browser window, no API key needed.
    """

    def __init__(self):
        self._cache = {}  # Simple in-memory cache
        log.info("WebSearch ready ✅ (DuckDuckGo + Wikipedia)")

    # ═══════════════════════════════════════════════════════════
    # MAIN SEARCH METHOD
    # ═══════════════════════════════════════════════════════════

    def search(self, query: str) -> str:
        """
        Main entry point — figures out best source and returns answer.
        Returns a short, voice-friendly answer string.
        """
        query = query.strip()
        if not query:
            return "What should I search for?"

        log.info(f"Web search: '{query}'")

        # Check cache (avoid re-fetching same query)
        cache_key = query.lower()
        if cache_key in self._cache:
            log.info("Returning cached result")
            return self._cache[cache_key]

        # Route to best source based on query type
        query_lower = query.lower().strip()

        # --- 0. Query Rewriting & Intent Extraction ---
        prog_langs = {"python", "java", "c++", "c#", "go", "rust", "ruby", "php", "javascript"}
        
        # Strip common prefixes to find the core entity
        core_entity = query_lower
        for p in ["what is a ", "what is an ", "what is ", "what are ", "who is ", "who was ", "who founded ", "who created ", "tell me about ", "define "]:
            if core_entity.startswith(p):
                core_entity = core_entity[len(p):].strip()
                break

        # If it's a known language, append "programming language"
        is_prog_context = any(w in query_lower for w in ["language", "programming", "code", "coding", "software"])
        if core_entity in prog_langs or (is_prog_context and core_entity.split()[0] in prog_langs):
            if "programming" not in query_lower and "language" not in query_lower:
                query = query + " programming language"
                query_lower = query.lower()
                core_entity = core_entity + " programming language"

        # Handle QA (Who founded / created)
        qa_field = None
        if "who founded" in query_lower or "who created" in query_lower or "founder of" in query_lower or "creator of" in query_lower:
            qa_field = "founder"

        if qa_field:
            result = self._duckduckgo(core_entity, qa_field=qa_field)
            if result:
                return self._cache_and_return(cache_key, result)

        # 1. Live data — crypto/stock prices
        if any(
            w in query_lower
            for w in [
                "bitcoin",
                "btc",
                "ethereum",
                "eth",
                "crypto",
                "price of",
                "stock price",
            ]
        ):
            result = self._crypto_price(query)
            if result:
                return self._cache_and_return(cache_key, result)

        # 2. Time in other city
        if "time in" in query_lower or "what time is it in" in query_lower:
            result = self._world_time(query)
            if result:
                return self._cache_and_return(cache_key, result)

        # 3. Wikipedia — "who is", "what is", definitions
        if any(
            query_lower.startswith(p)
            for p in [
                "who is",
                "who was",
                "what is",
                "what are",
                "define ",
                "tell me about",
                "explain ",
                "history of",
            ]
        ):
            result = self._wikipedia(query)
            if result:
                return self._cache_and_return(cache_key, result)

        # 4. DuckDuckGo Instant Answer
        result = self._duckduckgo(query)
        if result:
            return self._cache_and_return(cache_key, result)

        # 5. Wikipedia fallback
        result = self._wikipedia(query)
        if result:
            return self._cache_and_return(cache_key, result)

        # 6. Try a broader/simplified DuckDuckGo search
        simplified = " ".join(query.split()[:4])  # Use first 4 words
        result = self._duckduckgo(simplified)
        if result:
            return self._cache_and_return(cache_key, result)

        # 7. Open browser as absolute last resort
        import webbrowser

        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        webbrowser.open(url)
        return f"Opening Google for '{query}', sir."

    def search_news(self, topic: str = "") -> str:
        """Get latest news headlines for a topic."""
        query = f"latest news {topic}".strip()
        log.info(f"News search: '{query}'")

        result = self._duckduckgo(query)
        if result:
            return result

        # Fallback: open Google News
        import webbrowser

        url = f"https://news.google.com/search?q={urllib.parse.quote(topic)}&hl=en-IN"
        webbrowser.open(url)
        return f"Opening Google News for '{topic}'."

    def quick_answer(self, query: str) -> str:
        """Get a quick factual answer — DuckDuckGo only, very fast."""
        result = self._duckduckgo(query)
        return result or f"No instant answer found for '{query}'."

    # ═══════════════════════════════════════════════════════════
    # SEARCH SOURCES
    # ═══════════════════════════════════════════════════════════

    def _duckduckgo(self, query: str, qa_field: str = None) -> str:
        """Fetch DuckDuckGo Instant Answer (no API key, fast)."""
        try:
            url = DDG_API.format(query=urllib.parse.quote(query))
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            # Try different result types
            
            # QA Infobox Extraction
            if qa_field and data.get("Infobox") and data["Infobox"].get("content"):
                for item in data["Infobox"]["content"]:
                    label = item.get("label", "").lower()
                    if qa_field == "founder" and any(k in label for k in ["founder", "creator", "author", "developer", "inventor"]):
                        val = item.get("value")
                        if val:
                            if isinstance(val, dict):
                                val = val.get("id", str(val))
                            return f"{val}"

            # Type A = article (best)
            if data.get("AbstractText"):
                text = data["AbstractText"]
                source = data.get("AbstractSource", "")
                text = self._trim_for_voice(text)
                return f"{text} (Source: {source})" if source else text

            # Type D = disambiguation
            if data.get("RelatedTopics"):
                topics = data["RelatedTopics"]
                results = []
                for t in topics[:3]:
                    if isinstance(t, dict) and t.get("Text"):
                        results.append(t["Text"])
                if results:
                    return self._trim_for_voice(results[0])

            # Instant answer
            if data.get("Answer"):
                return str(data["Answer"])

            # Definition
            if data.get("Definition"):
                return self._trim_for_voice(data["Definition"])

        except Exception as e:
            log.warning(f"DuckDuckGo error: {e}")
        return ""

    def _wikipedia(self, query: str) -> str:
        """Fetch Wikipedia summary for a topic."""
        try:
            # Clean query for Wikipedia title
            title = query.strip()
            for prefix in [
                "Who is ",
                "Who was ",
                "What is ",
                "What are ",
                "Tell me about ",
                "Explain ",
                "Define ",
                "who is ",
                "who was ",
                "what is ",
                "what are ",
                "tell me about ",
                "explain ",
                "define ",
            ]:
                if title.startswith(prefix):
                    title = title[len(prefix) :]
                    break
            title = title.strip()

            # Try Wikipedia search API first (more reliable than direct title)
            search_url = (
                "https://en.wikipedia.org/w/api.php?action=query"
                "&list=search&srsearch={q}&format=json&srlimit=1".format(
                    q=urllib.parse.quote(title)
                )
            )
            req = urllib.request.Request(search_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = data.get("query", {}).get("search", [])
            if not results:
                return ""

            # Get the page title from search result
            page_title = results[0]["title"].replace(" ", "_")
            summary_url = WIKI_API.format(title=urllib.parse.quote(page_title))
            req2 = urllib.request.Request(summary_url, headers=HEADERS)
            with urllib.request.urlopen(req2, timeout=TIMEOUT) as resp2:
                page = json.loads(resp2.read().decode("utf-8"))

            if page.get("type") == "disambiguation":
                return ""

            extract = page.get("extract", "")
            if extract and len(extract) > 30:
                return self._trim_for_voice(extract)

        except Exception as e:
            log.warning(f"Wikipedia error: {e}")
        return ""

    def _crypto_price(self, query: str) -> str:
        """Get live crypto price from CoinGecko (free, no key)."""
        try:
            # Detect coin
            coin_map = {
                "bitcoin": "bitcoin",
                "btc": "bitcoin",
                "ethereum": "ethereum",
                "eth": "ethereum",
                "dogecoin": "dogecoin",
                "doge": "dogecoin",
                "cardano": "cardano",
                "ada": "cardano",
                "solana": "solana",
                "sol": "solana",
            }
            query_lower = query.lower()
            coin_id = None
            coin_name = None
            for keyword, cid in coin_map.items():
                if keyword in query_lower:
                    coin_id = cid
                    coin_name = keyword.title()
                    break

            if not coin_id:
                return ""

            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd,inr"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if coin_id in data:
                usd = data[coin_id].get("usd", 0)
                inr = data[coin_id].get("inr", 0)
                return (
                    f"{coin_name} is currently at ${usd:,.2f} USD or ₹{inr:,.0f} INR."
                )

        except Exception as e:
            log.warning(f"Crypto price error: {e}")
        return ""

    def _world_time(self, query: str) -> str:
        """Get current time in a city."""
        try:
            # Extract city from query
            city = query.lower()
            for prefix in ["what time is it in ", "time in ", "current time in "]:
                city = city.replace(prefix, "")
            city = city.strip()

            # Use worldtimeapi
            url = f"http://worldtimeapi.org/api/timezone"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                zones = json.loads(resp.read().decode("utf-8"))

            # Find matching zone
            city_clean = city.replace(" ", "_").lower()
            matching = [z for z in zones if city_clean in z.lower()]

            if matching:
                zone_url = f"http://worldtimeapi.org/api/timezone/{matching[0]}"
                req2 = urllib.request.Request(zone_url, headers=HEADERS)
                with urllib.request.urlopen(req2, timeout=TIMEOUT) as resp2:
                    tz_data = json.loads(resp2.read().decode("utf-8"))
                dt_str = tz_data.get("datetime", "")
                if dt_str:
                    dt = datetime.fromisoformat(dt_str[:19])
                    return f"It's {dt.strftime('%I:%M %p')} in {city.title()}."

        except Exception as e:
            log.warning(f"World time error: {e}")
        return ""

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _trim_for_voice(self, text: str, max_chars: int = 300) -> str:
        """Trim text to voice-friendly length (max ~3 sentences)."""
        if not text:
            return ""
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Remove parenthetical references like (1920–2005) or [citation]
        text = re.sub(r"\s*\([^)]{1,30}\)", "", text)
        text = re.sub(r"\s*\[[^\]]{1,30}\]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        # Cut to 3 sentences max
        sentences = re.split(r"(?<=[.!?])\s+", text)
        result = " ".join(sentences[:3])
        # Hard limit — cut at last complete sentence within limit
        if len(result) > max_chars:
            truncated = result[:max_chars]
            # Find last sentence ending before the limit
            last_end = max(
                truncated.rfind(". "), truncated.rfind("! "), truncated.rfind("? ")
            )
            if last_end > max_chars // 2:
                result = truncated[: last_end + 1]
            else:
                result = truncated.rsplit(" ", 1)[0] + "."
        return result

    def _cache_and_return(self, key: str, value: str) -> str:
        """Save to cache and return."""
        self._cache[key] = value
        # Keep cache small
        if len(self._cache) > 50:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        return value


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    ws = WebSearch()

    tests = [
        "Who is Elon Musk?",
        "What is machine learning?",
        "Bitcoin price",
        "Time in New York",
    ]
    for q in tests:
        print(f"\nQ: {q}")
        print(f"A: {ws.search(q)}")
