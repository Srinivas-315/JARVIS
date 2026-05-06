"""
JARVIS — test_weather_api.py
Comprehensive weather API diagnostic and testing script.
Tests weather functionality with specific cities (Delhi, Hyderabad, etc.)
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import requests
from dotenv import load_dotenv

# Load .env file
_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_ENV_PATH)

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
USER_CITY = os.getenv("USER_CITY", "Chennai")

print("=" * 70)
print("JARVIS WEATHER API DIAGNOSTIC TEST")
print("=" * 70)

# ─── 1. Check API Key Configuration ───────────────────────────────
print("\n[1] API KEY CONFIGURATION")
print("-" * 70)
if not WEATHER_API_KEY:
    print("❌ WEATHER_API_KEY is NOT configured!")
    print("   Add WEATHER_API_KEY to your .env file")
    print("   Get one free from: https://openweathermap.org/api")
else:
    print(f"✅ WEATHER_API_KEY configured: {WEATHER_API_KEY[:10]}...")

print(f"📍 Default user city: {USER_CITY}")

# ─── 2. Test with Specific Indian Cities ──────────────────────────
print("\n[2] TESTING SPECIFIC CITIES")
print("-" * 70)

test_cities = [
    "Delhi",
    "Hyderabad",
    "Telangana",
    "Andhra Pradesh",
    "Mumbai",
    "Bangalore",
]

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

for city in test_cities:
    print(f"\n🔍 Testing: {city}")
    try:
        params = {"q": city, "appid": WEATHER_API_KEY, "units": "metric"}

        response = requests.get(BASE_URL, params=params, timeout=5)

        print(f"   HTTP Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            # Extract data
            temp = data.get("main", {}).get("temp", "N/A")
            feels_like = data.get("main", {}).get("feels_like", "N/A")
            humidity = data.get("main", {}).get("humidity", "N/A")
            description = data.get("weather", [{}])[0].get("description", "N/A")
            wind_speed = data.get("wind", {}).get("speed", "N/A")
            city_name = data.get("name", "N/A")
            country = data.get("sys", {}).get("country", "N/A")

            print(f"   ✅ SUCCESS!")
            print(f"      Location: {city_name}, {country}")
            print(f"      Weather: {description.capitalize()}")
            print(f"      Temperature: {temp}°C (feels like {feels_like}°C)")
            print(f"      Humidity: {humidity}%")
            print(f"      Wind Speed: {wind_speed} m/s")

        elif response.status_code == 404:
            print(f"   ❌ CITY NOT FOUND")
            print(f"   Response: {response.text[:150]}")
        elif response.status_code == 401:
            print(f"   ❌ INVALID API KEY")
            print(f"   Check your WEATHER_API_KEY configuration")
        elif response.status_code == 429:
            print(f"   ❌ RATE LIMIT EXCEEDED")
            print(f"   Free plan allows limited requests")
        else:
            print(f"   ❌ ERROR: {response.status_code}")
            print(f"   Response: {response.text[:150]}")

    except requests.exceptions.Timeout:
        print(f"   ❌ TIMEOUT: Request took too long")
    except requests.exceptions.ConnectionError:
        print(f"   ❌ CONNECTION ERROR: Check internet connection")
    except Exception as e:
        print(f"   ❌ ERROR: {str(e)}")

# ─── 3. Test Weather Skill Class ──────────────────────────────────
print("\n[3] TESTING WEATHER SKILL CLASS")
print("-" * 70)

try:
    from skills.weather import WeatherSkill

    weather = WeatherSkill()

    # Test current weather for Delhi
    print("\n🔍 Testing WeatherSkill.get_current('Delhi')")
    result = weather.get_current("Delhi")
    print(f"   Result: {result}")

    # Test current weather for Hyderabad
    print("\n🔍 Testing WeatherSkill.get_current('Hyderabad')")
    result = weather.get_current("Hyderabad")
    print(f"   Result: {result}")

    # Test forecast
    print("\n🔍 Testing WeatherSkill.get_forecast('Delhi')")
    result = weather.get_forecast("Delhi", days=2)
    print(f"   Result: {result}")

    # Test AQI
    print("\n🔍 Testing WeatherSkill.get_aqi('Delhi')")
    result = weather.get_aqi("Delhi")
    print(f"   Result: {result}")

except ImportError as e:
    print(f"❌ Could not import WeatherSkill: {e}")
except Exception as e:
    print(f"❌ Error testing WeatherSkill: {e}")

# ─── 4. Summary and Recommendations ───────────────────────────────
print("\n[4] SUMMARY & RECOMMENDATIONS")
print("-" * 70)

issues = []

if not WEATHER_API_KEY:
    issues.append("• WEATHER_API_KEY not configured")
else:
    # Test if key works
    try:
        response = requests.get(
            BASE_URL,
            params={"q": "Delhi", "appid": WEATHER_API_KEY, "units": "metric"},
            timeout=5,
        )

        if response.status_code == 401:
            issues.append("• WEATHER_API_KEY is invalid or expired")
        elif response.status_code != 200:
            issues.append(f"• API returned HTTP {response.status_code}")
    except:
        issues.append("• Cannot connect to OpenWeatherMap API")

if issues:
    print("❌ ISSUES FOUND:")
    for issue in issues:
        print(issue)
    print("\n📝 TO FIX:")
    print("   1. Get a free API key from: https://openweathermap.org/api")
    print("   2. Add to .env file: WEATHER_API_KEY=your_key_here")
    print("   3. Restart JARVIS")
else:
    print("✅ Weather API appears to be working correctly!")
    print("   - API key is valid")
    print("   - Can fetch weather for Indian cities")
    print("   - Weather skill should be functional")

print("\n" + "=" * 70)
