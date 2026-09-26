import time
import httpx
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from backend.app.core.logging import logger
from backend.app.schemas.weather import (
    WeatherData,
    WeatherCurrentDTO,
    WeatherForecastDayDTO,
    WeatherSoilDTO,
    WeatherSignalsDTO,
    LocationMetadataDTO,
)


WMO_WEATHER_CODE_DESCRIPTIONS: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def get_wmo_description(code: int) -> str:
    return WMO_WEATHER_CODE_DESCRIPTIONS.get(code, "Cloudy/Variable conditions")


class OpenMeteoProvider:
    """
    Client for Open-Meteo numerical weather forecast API.
    Provides weather facts and neutral signals with in-memory caching and strict provenance.
    """

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, cache_ttl_seconds: int = 900, timeout_seconds: float = 6.0):
        self.cache_ttl = cache_ttl_seconds
        self.timeout = timeout_seconds
        # In-memory cache: key -> (timestamp, WeatherData)
        self._cache: Dict[str, Tuple[float, WeatherData]] = {}

    def _get_cache_key(self, lat: float, lon: float) -> str:
        return f"{round(lat, 2)}_{round(lon, 2)}"

    def clear_cache(self) -> None:
        self._cache.clear()

    async def fetch_weather(
        self,
        location: LocationMetadataDTO,
        client: Optional[httpx.AsyncClient] = None,
        force_refresh: bool = False,
    ) -> Optional[WeatherData]:
        """
        Fetches current weather, 3-day forecast, ET0, and soil parameters for the resolved location.
        Returns None if external provider fails or times out.
        """
        cache_key = self._get_cache_key(location.latitude, location.longitude)
        now = time.time()

        if not force_refresh and cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if now - cached_time < self.cache_ttl:
                # Return cached copy with updated location and data_origin
                return cached_data.model_copy(
                    update={
                        "data_origin": "production_cached",
                        "location": location,
                        "cached": True,
                    }
                )

        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,wind_direction_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,et0_fao_evapotranspiration",
            "hourly": "soil_temperature_0_to_10cm,soil_moisture_0_to_1cm",
            "timezone": "Asia/Kolkata",
            "forecast_days": 3,
        }

        should_close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            should_close_client = True

        try:
            response = await client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            raw = response.json()
            weather_data = self._parse_response(raw, location)
            self._cache[cache_key] = (now, weather_data)
            return weather_data
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning(f"Open-Meteo weather fetch failed for ({location.latitude}, {location.longitude}): {exc}")
            return None
        except Exception as exc:
            logger.error(f"Unexpected error parsing Open-Meteo response: {exc}", exc_info=True)
            return None
        finally:
            if should_close_client:
                await client.aclose()

    def _parse_response(self, raw: Dict[str, Any], location: LocationMetadataDTO) -> WeatherData:
        current_raw = raw.get("current", {})
        daily_raw = raw.get("daily", {})
        hourly_raw = raw.get("hourly", {})

        current_code = int(current_raw.get("weather_code", 0))
        current = WeatherCurrentDTO(
            time=str(current_raw.get("time", "")),
            temperature=float(current_raw.get("temperature_2m", 0.0)),
            relative_humidity=int(current_raw.get("relative_humidity_2m", 0)),
            precipitation=float(current_raw.get("precipitation", 0.0)),
            weather_code=current_code,
            weather_description=get_wmo_description(current_code),
            wind_speed=float(current_raw.get("wind_speed_10m", 0.0)),
            wind_direction=float(current_raw.get("wind_direction_10m")) if current_raw.get("wind_direction_10m") is not None else None,
        )

        forecast_days = []
        times = daily_raw.get("time", [])
        w_codes = daily_raw.get("weather_code", [])
        t_maxs = daily_raw.get("temperature_2m_max", [])
        t_mins = daily_raw.get("temperature_2m_min", [])
        precip_sums = daily_raw.get("precipitation_sum", [])
        precip_probs = daily_raw.get("precipitation_probability_max", [])
        wind_maxs = daily_raw.get("wind_speed_10m_max", [])
        et0s = daily_raw.get("et0_fao_evapotranspiration", [])

        for i in range(len(times)):
            code = int(w_codes[i]) if i < len(w_codes) else 0
            et0_val = float(et0s[i]) if i < len(et0s) and et0s[i] is not None else None
            forecast_days.append(
                WeatherForecastDayDTO(
                    date=times[i],
                    weather_code=code,
                    weather_description=get_wmo_description(code),
                    temp_max=float(t_maxs[i]) if i < len(t_maxs) else 0.0,
                    temp_min=float(t_mins[i]) if i < len(t_mins) else 0.0,
                    precipitation_sum=float(precip_sums[i]) if i < len(precip_sums) else 0.0,
                    precipitation_probability_max=int(precip_probs[i]) if i < len(precip_probs) else 0,
                    wind_speed_max=float(wind_maxs[i]) if i < len(wind_maxs) else 0.0,
                    et0_evapotranspiration=et0_val,
                )
            )

        # Soil parameters from hourly array (take current / latest reading)
        soil_temps = hourly_raw.get("soil_temperature_0_to_10cm", [])
        soil_moists = hourly_raw.get("soil_moisture_0_to_1cm", [])
        soil_temp = float(soil_temps[0]) if soil_temps else None
        soil_moist = float(soil_moists[0]) if soil_moists else None
        soil = WeatherSoilDTO(
            soil_temperature_0_to_10cm=soil_temp,
            soil_moisture_0_to_1cm=soil_moist,
        )

        # Compute neutral meteorological signals
        rain_expected = any(
            day.precipitation_sum >= 0.5 or day.precipitation_probability_max >= 40
            for day in forecast_days
        ) or current.precipitation > 0.0

        high_wind = any(day.wind_speed_max >= 20.0 for day in forecast_days) or current.wind_speed >= 20.0
        high_temp = any(day.temp_max >= 38.0 for day in forecast_days) or current.temperature >= 38.0
        low_temp = any(day.temp_min <= 10.0 for day in forecast_days) or current.temperature <= 10.0
        dry_period = all(day.precipitation_sum == 0.0 and day.precipitation_probability_max < 20 for day in forecast_days)

        signals = WeatherSignalsDTO(
            rain_expected=rain_expected,
            high_wind_signal=high_wind,
            high_temperature_signal=high_temp,
            low_temperature_signal=low_temp,
            dry_period_signal=dry_period,
        )

        return WeatherData(
            source="Open-Meteo",
            source_type="weather_model",
            data_origin="production_live",
            location=location,
            current=current,
            forecast_days=forecast_days,
            soil=soil,
            signals=signals,
            timezone=str(raw.get("timezone", "Asia/Kolkata")),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            cached=False,
        )


open_meteo_provider = OpenMeteoProvider()
