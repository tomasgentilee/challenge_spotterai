# Fuel Route Optimizer API

Una API REST de alto rendimiento construida con **Django** que calcula rutas óptimas para camiones en todo Estados Unidos. Identifica estratégicamente los mejores puntos de carga de combustible según precio y desviación mínima de la ruta.

---

## Características Principales

- **Smart Routing:** Utiliza **OpenRouteService (ORS)** para generar geometrías de manejo precisas.  
- **Optimización de Costos:** Selección de estaciones basada en una puntuación ponderada entre *precio del combustible* y *desviación de la ruta*.  
- **Alto Rendimiento:**  
  - Índice espacial **BallTree (O(log n))** para consultas rápidas.  
  - **Vectorización con NumPy** para calcular proyecciones sobre la ruta en milisegundos (reemplaza loops lentos).  
- **Salida Visual:** Genera mapas interactivos con **Folium (Leaflet)** mostrando ruta, paradas y precios.  
- **Estimaciones Financieras:** Cálculo de distancia total, consumo de combustible (galones) y costo estimado según MPG.  

---

## Arquitectura & Optimizaciones

Este proyecto resuelve eficientemente el problema **“Point-to-Curve Distance”**.

### Procesos Internos

- **Carga de Datos:** Al iniciar el servidor, miles de estaciones se cargan en un BallTree para consultas rápidas por radio.
- **Proyección Vectorizada:**  
  El algoritmo usa broadcasting de NumPy para proyectar estaciones sobre *cientos* de segmentos de ruta simultáneamente.  
  **Resultado:** tiempo de cálculo → *de segundos a milisegundos*.
- **Simplificación de Ruta:** Se reduce el tamaño de la geometría sin perder precisión, optimizando payloads y procesamiento.

---

## Requisitos

- Python **3.8+**
- **OpenRouteService API Key** (el plan gratuito funciona)
- Dataset de estaciones de combustible:  
  `datasets/truckstops_geocoded.csv`  
  (debe incluir latitud, longitud y Retail Price)

---

## Instalación

```bash
# Clonar el repositorio
git clone https://github.com/tomasgentilee/challenge_spotterai.git
```

```bash
# Crear entorno virtual
python -m venv venv
venv\Scripts\activate
```

```bash
# Instalar dependencias
pip install -r requirements.txt
```

### Variables de Entorno

Crear un archivo **.env** en la raíz del proyecto:

```bash
ORS_API_KEY=your_open_route_service_key_here
DEBUG=True
SECRET_KEY=your_django_secret_key
```

---

## Dataset

Asegurarse de que el dataset esté ubicado en:

./datasets/truckstops_geocoded.csv

---

## Ejecutar el Servidor

Iniciar el servidor Django:

```bash
python manage.py runserver
```

---

## 🔌 Uso de la API
**Endpoint**

POST /api/generate-route/

**Request (JSON)**

```bash
{
  "origin": "Los Angeles, CA",
  "destination": "New York, NY",
}
```

**Response (Ejemplo)**

```bash
{
  "route_summary": {
    "origin": "Los Angeles, CA",
    "destination": "New York, NY",
    "total_distance_miles": 2795.4,
    "total_fuel_gallons": 279.54,
    "total_fuel_cost": 1050.25,
    "average_price_paid": 3.75
  },
  "stops": [
    {
      "Truckstop Name": "Example Travel Center",
      "City": "Flagstaff",
      "State": "AZ",
      "Retail Price": 3.65,
      "deviation_km": 0.5,
      "latitude": 35.19,
      "longitude": -111.65
    }
    // ... más paradas
  ],
  "map_url": "/media/maps/route_a1b2c3d4.html"
}
```

---

## Visualización

La API genera y almacena un archivo HTML (Folium) con el mapa interactivo:

🟢 Verde: Origen

🔴 Rojo: Destino

⛽ Naranja: Paradas de combustible optimizadas (popup: precio y desviación)

🔵 Azul: Ruta calculada

map_url apunta al archivo HTML dentro de MEDIA_ROOT (ej. /media/maps/route_*.html).