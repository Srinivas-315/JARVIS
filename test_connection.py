"""
JARVIS — test_connection.py
Quick test to verify ALL API connections before running main.py
Run: python test_connection.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import config

print("\n" + "═" * 55)
print("  🤖 JARVIS — Connection Test")
print("═" * 55)

# ─── 1. Gemini API ───────────────────────────────────────────
print("\n[1/4] Testing Gemini AI...")
try:
    import requests as req
    if not config.GEMINI_API_KEY:
        print("  ❌ GEMINI_API_KEY is empty!")
    else:
        models   = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
        auths    = [
            ("query-v1beta", "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent", False),
            ("header-v1beta","https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent", True),
        ]
        body  = {"contents": [{"parts": [{"text": "Say: JARVIS online"}]}], "generationConfig": {"maxOutputTokens": 20}}
        found = False
        for model in models:
            for auth_name, base_url, use_header in auths:
                if use_header:
                    url = base_url.format(m=model)
                    hdrs = {"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"}
                else:
                    url  = f"{base_url.format(m=model)}?key={config.GEMINI_API_KEY}"
                    hdrs = {"Content-Type": "application/json"}
                r = req.post(url, json=body, headers=hdrs, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    # Gemini 2.5 thinking model response may have multiple parts
                    # Find the last text part (skip "thought" parts)
                    try:
                        parts = data["candidates"][0]["content"]["parts"]
                        text  = next(
                            p["text"] for p in reversed(parts)
                            if "text" in p and not p.get("thought", False)
                        )
                        print(f"  ✅ Gemini OK! [{auth_name}] Model: {model} → {text.strip()[:60]}")
                    except Exception:
                        # Fallback: just confirm connection worked
                        print(f"  ✅ Gemini CONNECTED! [{auth_name}] Model: {model}")
                        print(f"     Raw: {str(data)[:120]}")
                    found = True
                    break
            if found:
                break
        if not found:
            print("  ❌ All Gemini methods failed.")
            print("  → Please get a NEW key from: https://aistudio.google.com/app/apikey")
except Exception as e:
    print(f"  ❌ Gemini failed: {e}")
    print("  ℹ️  Get your key at: https://aistudio.google.com")

# ─── 2. OpenWeatherMap ───────────────────────────────────────
print("\n[2/4] Testing OpenWeatherMap (Weather)...")
try:
    import requests
    if not config.WEATHER_API_KEY:
        print("  ❌ WEATHER_API_KEY is empty!")
    else:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={config.USER_CITY}&appid={config.WEATHER_API_KEY}&units=metric"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"]
            print(f"  ✅ Weather OK! {config.USER_CITY}: {temp}°C, {desc}")
        elif resp.status_code == 401:
            print("  ❌ Invalid weather API key!")
        else:
            print(f"  ❌ Weather error: HTTP {resp.status_code}")
except Exception as e:
    print(f"  ❌ Weather failed: {e}")

# ─── 3. NewsAPI ──────────────────────────────────────────────
print("\n[3/4] Testing NewsAPI (News)...")
try:
    import requests
    if not config.NEWS_API_KEY:
        print("  ❌ NEWS_API_KEY is empty!")
    else:
        url = f"https://newsapi.org/v2/top-headlines?country=in&pageSize=1&apiKey={config.NEWS_API_KEY}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            articles = data.get("articles", [])
            if articles:
                print(f"  ✅ NewsAPI OK! Latest: {articles[0]['title'][:60]}...")
            else:
                print("  ✅ NewsAPI OK! (no articles right now)")
        elif resp.status_code == 401:
            print("  ❌ Invalid News API key!")
        else:
            print(f"  ❌ News error: HTTP {resp.status_code}")
except Exception as e:
    print(f"  ❌ News failed: {e}")

# ─── 4. Voice Systems ────────────────────────────────────────
print("\n[4/4] Testing Voice Output (pyttsx3)...")
try:
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", 180)
    print("  ✅ pyttsx3 OK! Speaking test...")
    engine.say("JARVIS voice system online!")
    engine.runAndWait()
    print("  ✅ Voice output working!")
except Exception as e:
    print(f"  ❌ Voice output failed: {e}")

# ─── Summary ─────────────────────────────────────────────────
print("\n" + "═" * 55)
print("  Test complete! Fix any ❌ issues above, then run:")
print("  python main.py")
print("═" * 55 + "\n")
