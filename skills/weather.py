"""
JARVIS — skills/weather.py
Get weather using OpenWeatherMap free API.
"""

import requests

import config
from utils.logger import log
from utils.safe_api import safe_json_extract, validate_status


class WeatherSkill:
    """Fetches and formats weather data."""

    BASE_URL = "https://api.openweathermap.org/data/2.5"

    def get_current(self, city: str = None) -> str:
        """Get current weather for a city."""
        city = city or config.USER_CITY

        if not config.WEATHER_API_KEY:
            return "Weather API key not set. Add WEATHER_API_KEY to your .env file."

        try:
            url = f"{self.BASE_URL}/weather"
            params = {
                "q": city,
                "appid": config.WEATHER_API_KEY,
                "units": "metric",  # Celsius
            }
            resp = requests.get(url, params=params, timeout=10)

            # Check status code BEFORE parsing JSON
            if not validate_status(resp, expected=200):
                return f"Weather service unavailable (HTTP {resp.status_code}). Try again later."

            data = resp.json()

            # Use safe extraction to handle missing fields
            temp = safe_json_extract(data, "main", "temp", default=None)
            feels_like = safe_json_extract(data, "main", "feels_like", default=None)
            humidity = safe_json_extract(data, "main", "humidity", default=None)
            description = safe_json_extract(
                data, "weather", 0, "description", default="unknown"
            )
            wind_speed = safe_json_extract(data, "wind", "speed", default=None)
            city_name = safe_json_extract(data, "name", default=city)
            country = safe_json_extract(data, "sys", "country", default="")

            # Check if we got the essential data
            if temp is None or humidity is None:
                log.error(f"Weather API missing essential fields for {city}")
                return f"Weather data incomplete for '{city}'."

            result = (
                f"Current weather in {city_name}, {country}: "
                f"{description.capitalize()}. "
                f"Temperature is {temp:.1f}°C, feels like {feels_like:.1f}°C. "
                f"Humidity is {humidity}%, wind speed {wind_speed} m/s."
            )
            log.info(f"Weather fetched for {city_name}")
            return result

        except requests.exceptions.Timeout:
            return f"Weather request timed out for '{city}'. Try again."
        except requests.exceptions.ConnectionError:
            return "No internet connection. Can't fetch weather."
        except Exception as e:
            log.error(f"Weather error: {e}")
            return "Couldn't fetch weather right now. Check your internet connection."

    def get_forecast(self, city: str = None, days: int = 3) -> str:
        """Get weather forecast for next N days."""
        city = city or config.USER_CITY

        if not config.WEATHER_API_KEY:
            return "Weather API key not configured."

        try:
            url = f"{self.BASE_URL}/forecast"
            params = {
                "q": city,
                "appid": config.WEATHER_API_KEY,
                "units": "metric",
                "cnt": days * 8,  # 8 readings per day (every 3hrs)
            }
            resp = requests.get(url, params=params, timeout=10)

            # Check status code BEFORE parsing JSON
            if not validate_status(resp, expected=200):
                return f"Forecast service unavailable (HTTP {resp.status_code})."

            data = resp.json()
            forecast_list = safe_json_extract(data, "list", default=[])

            if not forecast_list:
                log.error(f"Forecast API missing list field for {city}")
                return f"No forecast data available for '{city}'."

            # Summarize by day
            daily = {}
            for item in forecast_list:
                date_str = safe_json_extract(item, "dt_txt", default="")
                date = date_str.split(" ")[0] if date_str else "unknown"
                if date not in daily:
                    description = safe_json_extract(
                        item, "weather", 0, "description", default="unknown"
                    )
                    daily[date] = {"temps": [], "desc": description}
                temp = safe_json_extract(item, "main", "temp", default=None)
                if temp is not None:
                    daily[date]["temps"].append(temp)

            result = f"Weather forecast for {city}:\n"
            for i, (date, info) in enumerate(list(daily.items())[:days]):
                if info["temps"]:
                    min_t = min(info["temps"])
                    max_t = max(info["temps"])
                    result += f"• {date}: {info['desc'].capitalize()}, {min_t:.0f}°C to {max_t:.0f}°C\n"

            return (
                result.strip()
                if result.strip() != f"Weather forecast for {city}:"
                else "No forecast data available."
            )

        except requests.exceptions.Timeout:
            return f"Forecast request timed out. Try again."
        except requests.exceptions.ConnectionError:
            return "No internet connection. Can't fetch forecast."
        except Exception as e:
            log.error(f"Forecast error: {e}")
            return "Couldn't get the forecast right now."

    def get_aqi(self, city: str = None) -> str:
        """Get Air Quality Index for a city using Open-Meteo free API."""
        city = city or config.USER_CITY
        try:
            # First get coordinates using geocoding API
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
            geo_resp = requests.get(geo_url, timeout=5)
            geo_data = geo_resp.json()
            results = geo_data.get("results", [])
            if not results:
                return f"Could not find location '{city}', sir."
            lat = results[0]["latitude"]
            lon = results[0]["longitude"]
            # Get air quality data
            aq_url = (
                f"https://air-quality-api.open-meteo.com/v1/air-quality"
                f"?latitude={lat}&longitude={lon}"
                f"&hourly=pm2_5,pm10,european_aqi&timezone=auto&forecast_days=1"
            )
            aq_resp = requests.get(aq_url, timeout=5)
            aq_data = aq_resp.json()
            hourly = aq_data.get("hourly", {})
            aqi_list = hourly.get("european_aqi", [])
            pm25_list = hourly.get("pm2_5", [])
            if not aqi_list:
                return f"Air quality data unavailable for {city}, sir."
            # Get current hour's reading
            from datetime import datetime

            hour = datetime.now().hour
            aqi = aqi_list[hour] if hour < len(aqi_list) else aqi_list[-1]
            pm25 = pm25_list[hour] if pm25_list and hour < len(pm25_list) else None
            # AQI category
            if aqi <= 20:
                cat = "Excellent 🟢"
            elif aqi <= 40:
                cat = "Good 🟢"
            elif aqi <= 60:
                cat = "Moderate 🟡"
            elif aqi <= 80:
                cat = "Poor 🟠"
            elif aqi <= 100:
                cat = "Very Poor 🔴"
            else:
                cat = "Extremely Poor 🟤"
            result = f"Air quality in {city}: {cat} (AQI: {aqi:.0f})"
            if pm25:
                result += f", PM2.5: {pm25:.1f} μg/m³"
            advice = ""
            if aqi > 80:
                advice = " Avoid outdoor exercise and wear a mask, sir."
            elif aqi > 60:
                advice = " Sensitive people should reduce outdoor activity, sir."
            return result + advice
        except Exception as e:
            log.error(f"AQI error: {e}")
            return f"Could not fetch air quality data for {city}, sir."

    def get_sunrise_sunset(self, city: str = None) -> str:
        """Get today's sunrise and sunset times."""
        city = city or config.USER_CITY
        try:
            # Geocode
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
            geo_resp = requests.get(geo_url, timeout=5)
            results = geo_resp.json().get("results", [])
            if not results:
                return f"Could not find location '{city}', sir."
            lat = results[0]["latitude"]
            lon = results[0]["longitude"]
            # Get sunrise/sunset
            ss_url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                f"&daily=sunrise,sunset&timezone=auto&forecast_days=1"
            )
            ss_resp = requests.get(ss_url, timeout=5)
            ss_data = ss_resp.json()
            daily = ss_data.get("daily", {})
            sunrises = daily.get("sunrise", [])
            sunsets = daily.get("sunset", [])
            if not sunrises or not sunsets:
                return f"Sunrise/sunset data unavailable for {city}, sir."
            from datetime import datetime

            sr_dt = datetime.fromisoformat(sunrises[0])
            ss_dt = datetime.fromisoformat(sunsets[0])
            sr = sr_dt.strftime("%I:%M %p")
            ss = ss_dt.strftime("%I:%M %p")
            daylight = int((ss_dt - sr_dt).total_seconds() / 3600)
            return (
                f"In {city} today — Sunrise: {sr}, Sunset: {ss}. "
                f"Daylight: {daylight} hours, sir."
            )
        except Exception as e:
            log.error(f"Sunrise/sunset error: {e}")
            return f"Could not get sunrise/sunset for {city}, sir."

    def get_weather_suggestion(self, city: str = None) -> str:
        """Get weather-based suggestion: umbrella, sunscreen, jacket, etc."""
        city = city or config.USER_CITY
        try:
            weather = self.get_current(city)
            suggestions = []
            w_lower = weather.lower()
            if any(w in w_lower for w in ["rain", "drizzle", "shower", "thunderstorm"]):
                suggestions.append("carry an umbrella ☂️")
            if "temperature is" in w_lower:
                import re as _re

                temp_m = _re.search(r"temperature is (-?\d+\.?\d*)°c", w_lower)
                if temp_m:
                    temp = float(temp_m.group(1))
                    if temp < 15:
                        suggestions.append("wear a warm jacket 🧥")
                    elif temp < 20:
                        suggestions.append("carry a light jacket")
                    elif temp > 35:
                        suggestions.append("stay hydrated and wear sunscreen 🌞")
                        suggestions.append("avoid going out between 12-3 PM")
            if any(w in w_lower for w in ["sunny", "clear", "hot"]):
                suggestions.append("apply sunscreen and stay cool")
            if any(w in w_lower for w in ["fog", "mist", "haze"]):
                suggestions.append("drive carefully — low visibility 🌫️")
            if any(w in w_lower for w in ["storm", "thunder", "lightning"]):
                suggestions.append("avoid outdoor activities and stay safe ⚡")
            if not suggestions:
                return (
                    f"Weather looks fine in {city}. No special precautions needed, sir."
                )
            return (
                f"Based on current weather in {city}: " + ", ".join(suggestions) + "."
            )
        except Exception as e:
            return f"Could not generate weather suggestion: {str(e)[:60]}"

    def compare_cities(self, cities: list) -> str:
        """Compare current weather across multiple cities."""
        if not cities:
            return "Please specify cities to compare, sir."
        results = []
        for city in cities[:4]:  # Max 4 cities
            try:
                url = f"{self.BASE_URL}/weather"
                params = {"q": city, "appid": config.WEATHER_API_KEY, "units": "metric"}
                resp = requests.get(url, params=params, timeout=4)
                if resp.status_code == 200:
                    data = resp.json()
                    temp = data["main"]["temp"]
                    desc = data["weather"][0]["description"]
                    humidity = data["main"]["humidity"]
                    results.append(
                        f"{city.title()}: {temp:.0f}°C, {desc}, {humidity}% humidity"
                    )
                else:
                    results.append(f"{city.title()}: data unavailable")
            except Exception:
                results.append(f"{city.title()}: error fetching data")
        if not results:
            return "Could not fetch weather comparison, sir."
        return "Weather comparison:\n" + "\n".join(f"• {r}" for r in results)

    def get_weather_alert(self, city: str = None) -> str:
        """Check for severe weather alerts using OpenWeatherMap."""
        city = city or config.USER_CITY
        if not config.WEATHER_API_KEY:
            return "Weather API key not configured, sir."
        try:
            # Use One Call API for alerts (need coordinates first)
            geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={config.WEATHER_API_KEY}"
            geo_resp = requests.get(geo_url, timeout=5)
            geo_data = geo_resp.json()
            if not geo_data:
                return f"Could not find location '{city}', sir."
            lat = geo_data[0]["lat"]
            lon = geo_data[0]["lon"]
            alert_url = (
                f"https://api.openweathermap.org/data/3.0/onecall"
                f"?lat={lat}&lon={lon}&exclude=minutely,hourly,daily"
                f"&appid={config.WEATHER_API_KEY}"
            )
            alert_resp = requests.get(alert_url, timeout=5)
            if alert_resp.status_code == 200:
                alerts = alert_resp.json().get("alerts", [])
                if alerts:
                    msgs = []
                    for a in alerts[:3]:
                        msgs.append(
                            f"⚠️ {a.get('event', 'Alert')}: {a.get('description', '')[:80]}"
                        )
                    return "\n".join(msgs)
                return f"No severe weather alerts for {city} right now, sir."
            return f"Alert check unavailable (needs One Call API 3.0), sir."
        except Exception as e:
            return f"Alert check error: {str(e)[:60]}"


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    w = WeatherSkill()
    print(w.get_current())
    print(w.get_forecast())
