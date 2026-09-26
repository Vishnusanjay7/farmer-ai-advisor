from typing import Optional, Tuple, Dict, Any
from backend.app.schemas.weather import LocationMetadataDTO, LocationResolutionMethod


class LocationResolver:
    """
    Resolves geographic locations for weather queries with strict safety and provenance labelling.
    Applies strict precedence:
    1. Explicit GPS coordinates (field-level when available)
    2. District name -> District Centroid
    3. State name -> State Centroid
    4. Safe Default Fallback
    """

    # Canonical Indian Agricultural District Centroids
    DISTRICT_CENTROIDS: Dict[str, Tuple[float, float, str]] = {
        # District Name -> (Latitude, Longitude, State)
        "Indore": (22.7196, 75.8577, "Madhya Pradesh"),
        "Bhopal": (23.2599, 77.4126, "Madhya Pradesh"),
        "Ujjain": (23.1765, 75.7885, "Madhya Pradesh"),
        "Ludhiana": (30.9010, 75.8573, "Punjab"),
        "Karnal": (29.6857, 76.9905, "Haryana"),
        "Amritsar": (31.6340, 74.8723, "Punjab"),
        "Bathinda": (30.2110, 74.9455, "Punjab"),
        "Jalandhar": (31.3260, 75.5762, "Punjab"),
        "Rohtak": (28.8955, 76.6066, "Haryana"),
        "Hisar": (29.1492, 75.7217, "Haryana"),
        "Guntur": (16.3067, 80.4365, "Andhra Pradesh"),
        "Warangal": (17.9689, 79.5941, "Telangana"),
        "Kurnool": (15.8281, 78.0373, "Andhra Pradesh"),
        "Vijayawada": (16.5062, 80.6480, "Andhra Pradesh"),
        "Coimbatore": (11.0168, 76.9558, "Tamil Nadu"),
        "Madurai": (9.9252, 78.1198, "Tamil Nadu"),
        "Tiruppur": (11.1085, 77.3411, "Tamil Nadu"),
        "Salem": (11.6643, 78.1460, "Tamil Nadu"),
        "Erode": (11.3410, 77.7172, "Tamil Nadu"),
        "Mysuru": (12.2958, 76.6394, "Karnataka"),
        "Mandya": (12.5244, 76.8967, "Karnataka"),
        "Hubli": (15.3647, 75.1240, "Karnataka"),
        "Pune": (18.5204, 73.8567, "Maharashtra"),
        "Nashik": (19.9975, 73.7898, "Maharashtra"),
        "Nagpur": (21.1458, 79.0882, "Maharashtra"),
        "Solapur": (17.6599, 75.9064, "Maharashtra"),
        "Barabanki": (26.9268, 81.1834, "Uttar Pradesh"),
        "Varanasi": (25.3176, 82.9739, "Uttar Pradesh"),
        "Agra": (27.1767, 78.0081, "Uttar Pradesh"),
        "Patna": (25.5941, 85.1376, "Bihar"),
        "Bhubaneswar": (20.2961, 85.8245, "Odisha"),
        "Cuttack": (20.4625, 85.8828, "Odisha"),
        "Sambalpur": (21.4669, 83.9812, "Odisha"),
        "Rajkot": (22.3039, 70.8022, "Gujarat"),
        "Junagadh": (21.5222, 70.4579, "Gujarat"),
        "Surat": (21.1702, 72.8311, "Gujarat"),
        "Jaipur": (26.9124, 75.7873, "Rajasthan"),
        "Jodhpur": (26.2389, 73.0243, "Rajasthan"),
        "Kota": (25.2138, 75.8648, "Rajasthan"),
        "Burdwan": (23.2324, 87.8615, "West Bengal"),
        "Hooghly": (22.9038, 88.3968, "West Bengal"),
    }

    # Canonical Indian State Centroids
    STATE_CENTROIDS: Dict[str, Tuple[float, float]] = {
        "Punjab": (31.1471, 75.3412),
        "Haryana": (29.0588, 76.0856),
        "Madhya Pradesh": (22.9734, 78.6569),
        "Uttar Pradesh": (26.8467, 80.9462),
        "Tamil Nadu": (11.1271, 78.6569),
        "Telangana": (18.1124, 79.0193),
        "Andhra Pradesh": (15.9129, 79.7400),
        "Maharashtra": (19.7515, 75.7139),
        "Karnataka": (15.3173, 75.7139),
        "Gujarat": (22.2587, 71.1924),
        "Rajasthan": (27.0238, 74.2179),
        "West Bengal": (22.9868, 87.8550),
        "Bihar": (25.0961, 85.3131),
        "Odisha": (20.9517, 85.0985),
        "Kerala": (10.8505, 76.2711),
        "Assam": (26.2006, 92.9376),
    }

    DEFAULT_FALLBACK = (28.6139, 77.2090, "New Delhi (National Capital Region)", "Delhi")

    def resolve(
        self,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        district: Optional[str] = None,
        state: Optional[str] = None,
        allow_default: bool = True,
    ) -> Optional[LocationMetadataDTO]:
        """
        Resolves location according to strict precedence rules.
        """
        # 1. GPS Precedence
        if latitude is not None and longitude is not None:
            resolved_label = f"GPS Coordinates ({latitude:.4f}, {longitude:.4f})"
            if district:
                resolved_label += f" [{district}]"
            elif state:
                resolved_label += f" [{state}]"
            return LocationMetadataDTO(
                latitude=latitude,
                longitude=longitude,
                resolved_name=resolved_label,
                resolution_method=LocationResolutionMethod.GPS_COORDINATES,
                state=state,
                district=district,
            )

        # 2. District Centroid Precedence
        if district:
            # Case-insensitive lookup
            for d_name, (d_lat, d_lon, d_state) in self.DISTRICT_CENTROIDS.items():
                if d_name.lower() == district.strip().lower():
                    return LocationMetadataDTO(
                        latitude=d_lat,
                        longitude=d_lon,
                        resolved_name=f"{d_name} District Centroid",
                        resolution_method=LocationResolutionMethod.DISTRICT_CENTROID,
                        state=d_state,
                        district=d_name,
                    )

        # 3. State Centroid Precedence
        if state:
            for s_name, (s_lat, s_lon) in self.STATE_CENTROIDS.items():
                if s_name.lower() == state.strip().lower():
                    return LocationMetadataDTO(
                        latitude=s_lat,
                        longitude=s_lon,
                        resolved_name=f"{s_name} State Centroid",
                        resolution_method=LocationResolutionMethod.STATE_CENTROID,
                        state=s_name,
                        district=None,
                    )

        # 4. Safe Default Fallback
        if allow_default:
            f_lat, f_lon, f_name, f_state = self.DEFAULT_FALLBACK
            return LocationMetadataDTO(
                latitude=f_lat,
                longitude=f_lon,
                resolved_name=f_name,
                resolution_method=LocationResolutionMethod.DEFAULT_FALLBACK,
                state=f_state,
                district=None,
            )

        return None


location_resolver = LocationResolver()
