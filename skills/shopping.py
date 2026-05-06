"""
JARVIS — skills/shopping.py
Shopping searches on Amazon India, Flipkart, and more.
Opens results in default browser — fast and reliable.
"""

import re
import urllib.parse
import webbrowser

from utils.logger import log


class ShoppingSkill:
    """Search products across e-commerce platforms."""

    def search_amazon(self, query: str) -> str:
        """Search Amazon India for products."""
        url = f"https://www.amazon.in/s?k={urllib.parse.quote(query)}"
        webbrowser.open(url)
        log.info(f"Amazon search: '{query}'")
        return f"Searching Amazon India for: {query}"

    def search_flipkart(self, query: str) -> str:
        """Search Flipkart for products."""
        url = f"https://www.flipkart.com/search?q={urllib.parse.quote(query)}"
        webbrowser.open(url)
        log.info(f"Flipkart search: '{query}'")
        return f"Searching Flipkart for: {query}"

    def search_myntra(self, query: str) -> str:
        """Search Myntra for fashion products."""
        url = f"https://www.myntra.com/{urllib.parse.quote(query)}"
        webbrowser.open(url)
        log.info(f"Myntra search: '{query}'")
        return f"Searching Myntra for: {query}"

    def compare_prices(self, query: str) -> str:
        """Open product on Amazon + Flipkart for price comparison."""
        amazon_url = f"https://www.amazon.in/s?k={urllib.parse.quote(query)}"
        flipkart_url = f"https://www.flipkart.com/search?q={urllib.parse.quote(query)}"

        webbrowser.open(amazon_url)
        webbrowser.open(flipkart_url)

        return (
            f"Opened Amazon and Flipkart for '{query}' — compare prices in both tabs!"
        )

    def search_flights(self, query: str) -> str:
        """Search flights on Google Flights."""
        url = f"https://www.google.com/travel/flights?q={urllib.parse.quote(query)}"
        webbrowser.open(url)
        log.info(f"Flight search: '{query}'")
        return f"Searching flights for: {query}"

    def search_makemytrip(self, query: str) -> str:
        """Search on MakeMyTrip."""
        url = f"https://www.makemytrip.com/flights/"
        webbrowser.open(url)
        log.info(f"MakeMyTrip opened")
        return f"Opening MakeMyTrip — search for '{query}' there!"

    def search_hotels(self, query: str) -> str:
        """Search hotels on Google Hotels."""
        url = f"https://www.google.com/travel/hotels?q={urllib.parse.quote(query)}"
        webbrowser.open(url)
        log.info(f"Hotel search: '{query}'")
        return f"Searching hotels for: {query}"

    def parse_shopping_command(self, text: str) -> tuple[str, str]:
        """
        Parse shopping voice command → (platform, query).

        Examples:
          'find laptops under 50000 on Amazon'    → ('amazon', 'laptops under 50000')
          'search Flipkart for shoes'             → ('flipkart', 'shoes')
          'compare prices for iPhone 15'          → ('compare', 'iPhone 15')
          'search flights to Mumbai'              → ('flights', 'to Mumbai')
          'find hotels in Goa'                    → ('hotels', 'in Goa')
          'buy headphones'                        → ('amazon', 'headphones')
        """
        text_lower = text.lower().strip()

        # Detect platform
        platform = "amazon"  # Default

        if "flipkart" in text_lower:
            platform = "flipkart"
        elif "myntra" in text_lower:
            platform = "myntra"
        elif "compare" in text_lower and "price" in text_lower:
            platform = "compare"
        elif any(w in text_lower for w in ["flight", "flights", "fly", "ticket"]):
            platform = "flights"
        elif any(w in text_lower for w in ["hotel", "hotels", "stay", "booking"]):
            platform = "hotels"
        elif "makemytrip" in text_lower:
            platform = "makemytrip"

        # Extract the search query (remove platform name + filler words)
        query = text_lower
        remove_words = [
            "on amazon",
            "on flipkart",
            "on myntra",
            "on makemytrip",
            "from amazon",
            "from flipkart",
            "in amazon",
            "in flipkart",
            "search",
            "find",
            "look for",
            "show me",
            "buy",
            "compare prices for",
            "compare price for",
            "compare prices of",
            "compare price of",
            "search for",
            "shop for",
        ]
        for word in remove_words:
            query = query.replace(word, "")

        query = query.strip()
        if not query:
            query = text

        return platform, query

    def execute(self, text: str) -> str:
        """Parse and execute a shopping command."""
        platform, query = self.parse_shopping_command(text)

        log.info(f"Shopping: platform='{platform}', query='{query}'")

        if platform == "flipkart":
            return self.search_flipkart(query)
        elif platform == "myntra":
            return self.search_myntra(query)
        elif platform == "compare":
            return self.compare_prices(query)
        elif platform == "flights":
            return self.search_flights(query)
        elif platform == "hotels":
            return self.search_hotels(query)
        elif platform == "makemytrip":
            return self.search_makemytrip(query)
        else:
            return self.search_amazon(query)

    def add_to_wishlist(self, item: str) -> str:
        """Add an item to the voice wishlist."""
        import json
        from pathlib import Path

        wishlist_file = Path(__file__).parent.parent / "data" / "wishlist.json"
        wishlist_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            wishlist = (
                json.loads(wishlist_file.read_text()) if wishlist_file.exists() else []
            )
            item = item.strip()
            if item.lower() in [w.lower() for w in wishlist]:
                return f"'{item}' is already on your wishlist, sir."
            wishlist.append(item)
            wishlist_file.write_text(json.dumps(wishlist, indent=2))
            return f"Added '{item}' to your wishlist, sir. You have {len(wishlist)} item(s)."
        except Exception as e:
            return f"Could not add to wishlist: {str(e)[:60]}"

    def view_wishlist(self) -> str:
        """View all items on the wishlist."""
        import json
        from pathlib import Path

        wishlist_file = Path(__file__).parent.parent / "data" / "wishlist.json"
        try:
            if not wishlist_file.exists():
                return "Your wishlist is empty, sir."
            wishlist = json.loads(wishlist_file.read_text())
            if not wishlist:
                return "Your wishlist is empty, sir."
            items = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(wishlist))
            return f"Your wishlist ({len(wishlist)} items):\n{items}"
        except Exception as e:
            return f"Could not read wishlist: {str(e)[:60]}"

    def remove_from_wishlist(self, item: str) -> str:
        """Remove an item from the wishlist."""
        import json
        from pathlib import Path

        wishlist_file = Path(__file__).parent.parent / "data" / "wishlist.json"
        try:
            if not wishlist_file.exists():
                return "Wishlist is empty, sir."
            wishlist = json.loads(wishlist_file.read_text())
            before = len(wishlist)
            wishlist = [w for w in wishlist if item.lower() not in w.lower()]
            if len(wishlist) == before:
                return f"'{item}' not found in wishlist, sir."
            wishlist_file.write_text(json.dumps(wishlist, indent=2))
            return f"Removed '{item}' from wishlist, sir."
        except Exception as e:
            return f"Could not update wishlist: {str(e)[:60]}"

    def shop_wishlist_item(self, index: int = 1) -> str:
        """Open Amazon search for a wishlist item."""
        import json
        from pathlib import Path

        wishlist_file = Path(__file__).parent.parent / "data" / "wishlist.json"
        try:
            wishlist = (
                json.loads(wishlist_file.read_text()) if wishlist_file.exists() else []
            )
            if not wishlist:
                return "Wishlist is empty, sir."
            idx = index - 1
            if idx < 0 or idx >= len(wishlist):
                return (
                    f"No item at position {index}. Wishlist has {len(wishlist)} items."
                )
            item = wishlist[idx]
            return self.search_amazon(item)
        except Exception as e:
            return f"Could not open wishlist item: {str(e)[:60]}"

    def summarize_reviews(self, product_url: str, llm=None) -> str:
        """Summarize Amazon/Flipkart product reviews. Requires LLM."""
        if not llm:
            return "Review summarizer needs AI. Pass the LLM handler, sir."
        try:
            import urllib.request

            req = urllib.request.Request(
                product_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            # Extract review text (basic - works for many sites)
            import re

            reviews = re.findall(
                r"(?:review-text|review_body|a-size-base review-text)[^>]*>(.*?)</span",
                html,
            )
            reviews = [
                re.sub("<[^>]+>", "", r).strip() for r in reviews[:5] if len(r) > 20
            ]
            if not reviews:
                return "Could not extract reviews from the page, sir. Try a direct reviews URL."
            combined = " | ".join(reviews[:3])
            return llm.ask(
                f"Summarize these product reviews in 3 sentences: {combined[:600]}"
            )
        except Exception as e:
            return f"Review summary failed: {str(e)[:60]}"


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    shop = ShoppingSkill()
    tests = [
        "find laptops under 50000 on Amazon",
        "search Flipkart for shoes",
        "compare prices for iPhone 15",
        "search flights to Mumbai",
        "find hotels in Goa",
    ]
    for t in tests:
        platform, query = shop.parse_shopping_command(t)
        print(f"'{t}' → platform={platform}, query='{query}'")
