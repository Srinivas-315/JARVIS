"""
JARVIS — skills/news.py
Get latest news using NewsAPI (free tier: 100 requests/day).
"""

import requests

import config
from utils.logger import log
from utils.safe_api import safe_json_extract, validate_status


class NewsSkill:
    """Fetches and summarizes latest news headlines."""

    BASE_URL = "https://newsapi.org/v2"

    CATEGORIES = [
        "business",
        "entertainment",
        "general",
        "health",
        "science",
        "sports",
        "technology",
    ]

    def get_headlines(self, category: str = "general", count: int = 5) -> str:
        """Get top headlines by category."""

        if not config.NEWS_API_KEY:
            return "News API key not set. Add NEWS_API_KEY to your .env file."

        # Validate category
        if category not in self.CATEGORIES:
            category = "general"

        try:
            url = f"{self.BASE_URL}/top-headlines"
            params = {
                "country": "in",  # India news (change if needed)
                "category": category,
                "apiKey": config.NEWS_API_KEY,
                "pageSize": count,
            }
            resp = requests.get(url, params=params, timeout=5)

            # Check status code BEFORE parsing JSON
            if not validate_status(resp, expected=200):
                return f"News service unavailable (HTTP {resp.status_code})."

            data = resp.json()
            articles = safe_json_extract(data, "articles", default=[])

            if not articles:
                return f"No {category} news found right now."

            result = f"Top {category} news:\n"
            for i, article in enumerate(articles[:count], 1):
                title = safe_json_extract(article, "title", default="").split(" - ")[0]
                source = safe_json_extract(article, "source", "name", default="Unknown")
                result += f"{i}. {title} ({source})\n"

            log.info(f"Fetched {len(articles)} {category} headlines")
            return result.strip()

        except requests.exceptions.Timeout:
            return "News request timed out. Try again."
        except requests.exceptions.ConnectionError:
            return "No internet connection. Can't fetch news."
        except Exception as e:
            log.error(f"News error: {e}")
            return "Couldn't fetch news right now. Check your internet connection."

    def search_news(self, query: str, count: int = 3) -> str:
        """Search for news about a specific topic."""
        if not config.NEWS_API_KEY:
            return "News API key not configured."

        try:
            url = f"{self.BASE_URL}/everything"
            params = {
                "q": query,
                "apiKey": config.NEWS_API_KEY,
                "pageSize": count,
                "sortBy": "publishedAt",
                "language": "en",
            }
            resp = requests.get(url, params=params, timeout=5)

            # Check status code BEFORE parsing JSON
            if not validate_status(resp, expected=200):
                return f"News search service unavailable (HTTP {resp.status_code})."

            data = resp.json()
            articles = safe_json_extract(data, "articles", default=[])

            if not articles:
                return f"No news found about '{query}'."

            result = f"News about '{query}':\n"
            for i, article in enumerate(articles[:count], 1):
                title = safe_json_extract(article, "title", default="").split(" - ")[0]
                result += f"{i}. {title}\n"

            return result.strip()

        except requests.exceptions.Timeout:
            return "News search request timed out. Try again."
        except requests.exceptions.ConnectionError:
            return "No internet connection. Can't search news."
        except Exception as e:
            log.error(f"News search error: {e}")
            return f"Couldn't search news for '{query}'."

    def detect_category(self, text: str) -> str:
        """Detect news category from voice command."""
        text_lower = text.lower()
        category_keywords = {
            "sports": ["sports", "cricket", "football", "ipl", "match", "score"],
            "technology": ["tech", "technology", "ai", "software", "gadget", "phone"],
            "business": ["business", "market", "stock", "economy", "finance"],
            "entertainment": [
                "entertainment",
                "movie",
                "bollywood",
                "celebrity",
                "film",
            ],
            "health": ["health", "covid", "medicine", "hospital", "doctor"],
            "science": ["science", "space", "nasa", "research", "discovery"],
        }
        for category, keywords in category_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return "general"

    def get_rss_news(self, feed_url: str = None, topic: str = None) -> str:
        """
        Fetch news from RSS feed. Uses default feeds if no URL provided.
        Say: 'rss news from bbc' / 'fetch rss feed' / 'read rss'
        """
        DEFAULT_FEEDS = {
            "bbc": "https://feeds.bbci.co.uk/news/rss.xml",
            "reuters": "https://feeds.reuters.com/reuters/topNews",
            "techcrunch": "https://techcrunch.com/feed/",
            "google": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
            "hindu": "https://www.thehindu.com/feeder/default.rss",
            "ndtv": "https://feeds.feedburner.com/ndtvnews-top-stories",
        }
        try:
            import urllib.request
            import xml.etree.ElementTree as ET

            # Pick feed
            if feed_url:
                url = feed_url
            elif topic:
                topic_lower = topic.lower()
                url = next(
                    (v for k, v in DEFAULT_FEEDS.items() if k in topic_lower),
                    DEFAULT_FEEDS["google"],
                )
            else:
                url = DEFAULT_FEEDS["google"]
            req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/2.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            items = root.findall(".//item")[:5]
            if not items:
                return "No articles found in the RSS feed, sir."
            headlines = []
            for item in items:
                title_el = item.find("title")
                title = title_el.text if title_el is not None else "No title"
                title = title.strip().split(" - ")[0][:80]
                headlines.append(f"• {title}")
            source = topic or "RSS"
            return f"Latest from {source}:\n" + "\n".join(headlines)
        except Exception as e:
            log.error(f"RSS feed error: {e}")
            return f"Could not fetch RSS feed: {str(e)[:60]}"

    def summarize_headline(self, article_text: str, llm=None) -> str:
        """Summarize a news article in 2-3 sentences."""
        if not article_text:
            return "No article text to summarize, sir."
        if llm:
            return llm.ask(
                f"Summarize this news in 2-3 sentences for spoken delivery (no bullets, no markdown): {article_text[:800]}"
            )
        # Simple extractive summary without LLM
        sentences = article_text.replace("\n", " ").split(". ")
        summary = ". ".join(sentences[:2]) + "."
        return summary if len(summary) > 20 else article_text[:200]

    def get_trending_topics(self) -> str:
        """Get trending news topics from Google Trends RSS."""
        try:
            import urllib.request
            import xml.etree.ElementTree as ET

            url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=IN"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            items = root.findall(".//item")[:8]
            topics = []
            for item in items:
                title_el = item.find("title")
                if title_el is not None and title_el.text:
                    topics.append(title_el.text.strip())
            if not topics:
                return "Could not fetch trending topics, sir."
            return "Trending in India right now:\n" + "\n".join(
                f"{i + 1}. {t}" for i, t in enumerate(topics)
            )
        except Exception as e:
            log.error(f"Trending topics error: {e}")
            return f"Could not fetch trending topics: {str(e)[:60]}"

    def get_news_by_mood(self, mood: str = "positive") -> str:
        """
        Get news filtered by mood: positive, tech, science, sports.
        Mood keywords filter the headlines.
        """
        mood_category_map = {
            "positive": "general",
            "happy": "entertainment",
            "tech": "technology",
            "science": "science",
            "sports": "sports",
            "business": "business",
            "health": "health",
        }
        category = mood_category_map.get(mood.lower(), "general")
        headlines = self.get_headlines(category, count=8)
        if mood.lower() in ("positive", "happy", "good"):
            # Try to filter for positive words
            positive_words = [
                "win",
                "success",
                "achieve",
                "launch",
                "record",
                "growth",
                "award",
                "break",
                "innovate",
                "save",
                "discover",
                "celebrate",
                "improve",
                "help",
            ]
            lines = headlines.split("\n")
            positive_lines = [
                l for l in lines[1:] if any(w in l.lower() for w in positive_words)
            ]
            if positive_lines:
                return "Positive news today:\n" + "\n".join(positive_lines[:5])
        return headlines


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    news = NewsSkill()
    print(news.get_headlines("technology"))
    print(news.search_news("India AI"))
