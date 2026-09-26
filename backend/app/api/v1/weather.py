from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.app.schemas.weather import (
    WeatherResponse,
    WeatherData,
    WeatherQueryRequest,
    LocationResolutionMethod,
)
from backend.app.services.location_resolver import location_resolver
from backend.app.providers.weather_provider import open_meteo_provider

router = APIRouter(prefix="/weather", tags=["Weather Intelligence"])


@router.get(
    "",
    response_model=WeatherResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch current weather, 3-day forecast, and agricultural soil/evaporative parameters",
)
async def get_weather(
    latitude: Optional[float] = Query(default=None, ge=-90.0, le=90.0, description="Latitude for GPS-level observation"),
    longitude: Optional[float] = Query(default=None, ge=-180.0, le=180.0, description="Longitude for GPS-level observation"),
    district: Optional[str] = Query(default=None, description="Indian district name (resolves to district centroid)"),
    state: Optional[str] = Query(default=None, description="Indian state name (resolves to state centroid)"),
) -> WeatherResponse:
    """
    Fetches real-time numerical weather observations and 3-day forecasts from Open-Meteo.
    Applies explicit location resolution hierarchy: GPS -> District Centroid -> State Centroid -> Fallback.
    Labels resolution method clearly to prevent implying field-level precision for centroid estimates.
    """
    location = location_resolver.resolve(
        latitude=latitude,
        longitude=longitude,
        district=district,
        state=state,
        allow_default=True,
    )

    if not location:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "LOCATION_RESOLUTION_FAILED",
                "message": "Unable to resolve location. Please specify a district, state, or valid GPS coordinates.",
            },
        )

    weather_data = await open_meteo_provider.fetch_weather(location=location)
    if not weather_data:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "WEATHER_SERVICE_UNAVAILABLE",
                "message": "Open-Meteo weather service is currently unreachable. Please try again shortly.",
            },
        )

    return WeatherResponse(
        status="ok",
        weather=weather_data,
        error=None,
    )
