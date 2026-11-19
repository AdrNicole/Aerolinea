"""Coordenadas de los 25 aeropuertos del dataset (latitud, longitud).

El dataset no trae ubicaciones; estas son las coordenadas aproximadas de
cada aeropuerto real (codigo IATA), agregadas para dibujar el mapa.
"""

COORDENADAS = {
    # Peru
    "LIM": (-12.0219, -77.1143),   # Lima - Jorge Chavez
    "CUZ": (-13.5357, -71.9388),   # Cusco - Velasco Astete
    "AQP": (-16.3411, -71.5831),   # Arequipa - Rodriguez Ballon
    "PIU": (-5.2058, -80.6164),    # Piura - Concha Iberico
    "TRU": (-8.0814, -79.1088),    # Trujillo - Martinez de Pinillos
    "IQT": (-3.7847, -73.3088),    # Iquitos - Secada Vignetta
    "JUL": (-15.4671, -70.1582),   # Juliaca - Inca Manco Capac
    "TPP": (-6.5087, -76.3732),    # Tarapoto - Guillermo del Castillo
    "CIX": (-6.7875, -79.8281),    # Chiclayo - Jose Quinones
    "PCL": (-8.3779, -74.5743),    # Pucallpa - David Abensur
    "AYP": (-13.1548, -74.2043),   # Ayacucho - Alfredo Mendivil
    "TCQ": (-18.0533, -70.2758),   # Tacna - Carlos Ciriani
    "PEM": (-12.6136, -69.2286),   # Puerto Maldonado - Padre Aldamiz
    "JAU": (-11.7831, -75.4734),   # Jauja - Francisco Carle
    "TBP": (-3.5525, -80.3814),    # Tumbes - Pedro Canga
    "CJA": (-7.1392, -78.4894),    # Cajamarca - Armando Revoredo
    # Internacionales
    "SCL": (-33.3930, -70.7858),   # Santiago
    "BOG": (4.7016, -74.1469),     # Bogota
    "EZE": (-34.8222, -58.5358),   # Buenos Aires
    "GRU": (-23.4356, -46.4731),   # Sao Paulo
    "MIA": (25.7959, -80.2870),    # Miami
    "MEX": (19.4363, -99.0721),    # Ciudad de Mexico
    "PTY": (9.0714, -79.3835),     # Ciudad de Panama
    "UIO": (-0.1292, -78.3575),    # Quito
    "MAD": (40.4983, -3.5676),     # Madrid
}


def lon_lat(iata: str) -> list[float]:
    """[longitud, latitud], el orden que usa pydeck."""
    lat, lon = COORDENADAS[iata]
    return [lon, lat]


CIUDADES = {
    "LIM": "Lima", "CUZ": "Cusco", "AQP": "Arequipa", "PIU": "Piura", "TRU": "Trujillo",
    "IQT": "Iquitos", "JUL": "Juliaca", "TPP": "Tarapoto", "CIX": "Chiclayo", "PCL": "Pucallpa",
    "AYP": "Ayacucho", "TCQ": "Tacna", "PEM": "Puerto Maldonado", "JAU": "Jauja", "TBP": "Tumbes",
    "CJA": "Cajamarca", "SCL": "Santiago", "BOG": "Bogotá", "EZE": "Buenos Aires",
    "GRU": "São Paulo", "MIA": "Miami", "MEX": "Ciudad de México", "PTY": "Ciudad de Panamá",
    "UIO": "Quito", "MAD": "Madrid",
}

PAISES = {"SCL": "Chile", "BOG": "Colombia", "EZE": "Argentina", "GRU": "Brasil", "MIA": "Estados Unidos",
          "MEX": "México", "PTY": "Panamá", "UIO": "Ecuador", "MAD": "España"}   # el resto: Peru


def pais(iata: str) -> str:
    return PAISES.get(iata, "Perú")


def nombre_ruta(ruta: str) -> str:
    """'LIM-MAD' -> 'Lima → Madrid'  (tambien acepta 'LIM ⇄ MAD')."""
    sep = " ⇄ " if "⇄" in ruta else "-"
    flecha = " ⇄ " if sep == " ⇄ " else " → "
    return flecha.join(CIUDADES.get(c, c) for c in ruta.split(sep))
