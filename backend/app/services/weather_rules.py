from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from backend.app.schemas.weather import WeatherData


class AgronomicRuleAuditEntry(BaseModel):
    rule_id: str
    operation: str
    threshold: str
    unit: str
    source_document: str
    source_url: Optional[str] = None
    section_page: Optional[str] = None
    authoritative_status: str  # "VERIFIED_AUTHORITATIVE" or "EVIDENCE_UNAVAILABLE"
    crop_scope: str
    geographic_scope: str
    evidence: str
    implemented: bool
    rationale: str


# ==============================================================================
# AUTHORITATIVE AGRONOMIC THRESHOLD AUDIT REGISTRY
# Evaluates every candidate weather-agriculture rule against the authoritative corpus:
# 1. ICAR-IIRR Rice Integrated Pest Management 2024
# 2. IARI Wheat Package of Practices 2024
# 3. ANGRAU Chili Integrated Pest Protocol
# 4. CICR Cotton Pest Guidelines
# 5. PAU Oilseeds & Mustard Guide
# 6. UAS Bangalore Millets Package of Practices
# ==============================================================================
AGRONOMIC_RULE_AUDIT_REGISTRY: List[AgronomicRuleAuditEntry] = [
    AgronomicRuleAuditEntry(
        rule_id="RULE-SPRAY-RAIN-01",
        operation="spraying / rain",
        threshold="rain_probability >= 40% OR precipitation >= 1.0mm",
        unit="% / mm",
        source_document="None (Candidate Heuristic)",
        source_url=None,
        section_page=None,
        authoritative_status="EVIDENCE_UNAVAILABLE",
        crop_scope="Universal / General",
        geographic_scope="All-India",
        evidence="None of the 6 corpus documents specify a universal numerical rain probability cutoff for chemical spraying.",
        implemented=False,
        rationale="DO NOT implement. Expose rain probability strictly as a weather observation fact without inventing a universal spray veto.",
    ),
    AgronomicRuleAuditEntry(
        rule_id="RULE-SPRAY-WIND-02",
        operation="spraying / wind",
        threshold="wind_speed > 15 km/h",
        unit="km/h",
        source_document="None (Candidate Heuristic)",
        source_url=None,
        section_page=None,
        authoritative_status="EVIDENCE_UNAVAILABLE",
        crop_scope="Universal / General",
        geographic_scope="All-India",
        evidence="No numeric wind speed threshold is defined in the authoritative agricultural POP documents.",
        implemented=False,
        rationale="DO NOT implement. Report wind speed as a physical weather fact; do not fabricate universal chemical spraying directives.",
    ),
    AgronomicRuleAuditEntry(
        rule_id="RULE-IRRIG-RAIN-03",
        operation="irrigation / rainfall",
        threshold="rain_probability >= 50% OR precipitation > 5mm",
        unit="% / mm",
        source_document="None (Candidate Heuristic)",
        source_url=None,
        section_page=None,
        authoritative_status="EVIDENCE_UNAVAILABLE",
        crop_scope="Universal / General",
        geographic_scope="All-India",
        evidence="IARI Wheat POP specifies irrigation by physiological stage (CRI at 20-25 DAS, tillering, etc.), not by a 5mm rainfall threshold.",
        implemented=False,
        rationale="DO NOT implement. Present rainfall probability and volume as weather facts; rely on crop-stage irrigation POPs.",
    ),
    AgronomicRuleAuditEntry(
        rule_id="RULE-IRRIG-ET0-04",
        operation="irrigation / ET0",
        threshold="ET0 > 5.0 mm/day",
        unit="mm/day",
        source_document="None (Candidate Heuristic)",
        source_url=None,
        section_page=None,
        authoritative_status="EVIDENCE_UNAVAILABLE",
        crop_scope="Universal / General",
        geographic_scope="All-India",
        evidence="Reference evapotranspiration (ET0) is an atmospheric metric from FAO-56, not defined as an actionable irrigation threshold in the corpus POPs.",
        implemented=False,
        rationale="DO NOT implement. Expose ET0 purely as an atmospheric evaporative demand fact.",
    ),
    AgronomicRuleAuditEntry(
        rule_id="RULE-IRRIG-SOIL-05",
        operation="irrigation / soil moisture",
        threshold="soil_moisture < 0.20 m3/m3",
        unit="m3/m3",
        source_document="None (Candidate Heuristic)",
        source_url=None,
        section_page=None,
        authoritative_status="EVIDENCE_UNAVAILABLE",
        crop_scope="Universal / General",
        geographic_scope="All-India",
        evidence="No volumetric soil moisture sensor thresholds are defined in the current agricultural knowledge documents.",
        implemented=False,
        rationale="DO NOT implement. Expose soil moisture observations without converting to universal irrigation prescriptions.",
    ),
    AgronomicRuleAuditEntry(
        rule_id="RULE-HARVEST-RAIN-06",
        operation="harvesting / rain",
        threshold="rain_probability >= 40%",
        unit="%",
        source_document="None (Candidate Heuristic)",
        source_url=None,
        section_page=None,
        authoritative_status="EVIDENCE_UNAVAILABLE",
        crop_scope="Universal / General",
        geographic_scope="All-India",
        evidence="Harvest timing in corpus is governed by maturity indicators (grain moisture, days after sowing), not rain probability.",
        implemented=False,
        rationale="DO NOT implement. Report weather risk factor; do not issue universal harvest postponement orders.",
    ),
    AgronomicRuleAuditEntry(
        rule_id="RULE-THERMAL-HEAT-07",
        operation="heat stress",
        threshold="temperature > 40 C",
        unit="Celsius",
        source_document="None (Candidate Heuristic)",
        source_url=None,
        section_page=None,
        authoritative_status="EVIDENCE_UNAVAILABLE",
        crop_scope="Universal / General",
        geographic_scope="All-India",
        evidence="Crop heat sensitivity varies significantly by phenological stage and crop species; no universal 40 C threshold in corpus.",
        implemented=False,
        rationale="DO NOT implement. Provide temperature observation and signal; do not issue universal agronomic heat directives.",
    ),
    AgronomicRuleAuditEntry(
        rule_id="RULE-THERMAL-COLD-08",
        operation="frost / cold stress",
        threshold="temperature < 5 C",
        unit="Celsius",
        source_document="None (Candidate Heuristic)",
        source_url=None,
        section_page=None,
        authoritative_status="EVIDENCE_UNAVAILABLE",
        crop_scope="Universal / General",
        geographic_scope="All-India",
        evidence="Yellow rust in wheat correlates with cold humid weather, but no universal 5 C frost rule exists in corpus.",
        implemented=False,
        rationale="DO NOT implement. Report temperature observations as neutral facts.",
    ),
]


class WeatherObservationSummary(BaseModel):
    """
    Summarizes neutral weather facts and observations.
    DOES NOT contain ungrounded or invented agronomic prescriptions.
    """
    location_name: str
    resolution_method: str
    current_temp: float
    current_humidity: int
    current_condition: str
    current_wind_speed: float
    rain_expected: bool
    precipitation_sum_3d: float
    max_rain_probability_3d: int
    et0_today: Optional[float] = None
    signals_summary: List[str] = Field(default_factory=list)


def summarize_weather_facts(weather: WeatherData) -> WeatherObservationSummary:
    """
    Extracts neutral meteorological facts from Open-Meteo data without making agronomic claims.
    """
    signals = []
    if weather.signals.rain_expected:
        signals.append("Rain or showers predicted in forecast window")
    if weather.signals.high_wind_signal:
        signals.append(f"Elevated wind speeds up to {max((d.wind_speed_max for d in weather.forecast_days), default=weather.current.wind_speed)} km/h")
    if weather.signals.high_temperature_signal:
        signals.append(f"High temperature conditions exceeding 38 C")
    if weather.signals.low_temperature_signal:
        signals.append(f"Low temperature conditions below 10 C")
    if weather.signals.dry_period_signal:
        signals.append("Dry period forecast with low precipitation probability")

    precip_3d = sum(d.precipitation_sum for d in weather.forecast_days)
    max_rain_prob = max((d.precipitation_probability_max for d in weather.forecast_days), default=0)
    et0_today = weather.forecast_days[0].et0_evapotranspiration if weather.forecast_days else None

    return WeatherObservationSummary(
        location_name=weather.location.resolved_name,
        resolution_method=weather.location.resolution_method.value,
        current_temp=weather.current.temperature,
        current_humidity=weather.current.relative_humidity,
        current_condition=weather.current.weather_description,
        current_wind_speed=weather.current.wind_speed,
        rain_expected=weather.signals.rain_expected,
        precipitation_sum_3d=round(precip_3d, 1),
        max_rain_probability_3d=max_rain_prob,
        et0_today=et0_today,
        signals_summary=signals,
    )
