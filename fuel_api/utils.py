import pandas as pd
import numpy as np
from math import radians, cos, sin, sqrt, atan2
from sklearn.neighbors import BallTree
import requests
from decouple import config

# ---------------------------
# CONFIG
# ---------------------------
ORS_API_KEY = config("ORS_API_KEY")
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"

TRUCKSTOPS_CSV = './datasets/truckstops_geocoded.csv'
OUTPUT_CSV = "trip_plan_stops.csv"

MILES_PER_STOP = 450.0
MAX_DEVIATION_MILES = 20.0 
MIN_DEVIATION_KM = 0.35
ALPHA = 1.0
BETA = 3.0
R_earth_km = 6371.0

# ---------------------------
# CARGA DE DATOS (GLOBAL - SE EJECUTA UNA VEZ)
# ---------------------------
print("Cargando Truckstops y generando BallTree...")
try:
    GLOBAL_STATIONS_DF = pd.read_csv(TRUCKSTOPS_CSV)
    # Filtrar datos válidos
    GLOBAL_STATIONS_DF = GLOBAL_STATIONS_DF[
        GLOBAL_STATIONS_DF["latitude"].notna() & 
        GLOBAL_STATIONS_DF["longitude"].notna()
    ].reset_index(drop=True)
    
    # Crear BallTree una sola vez
    GLOBAL_STATIONS_TREE = BallTree(
        np.radians(GLOBAL_STATIONS_DF[["latitude", "longitude"]].values), 
        metric='haversine'
    )
    print(f"Datos cargados: {len(GLOBAL_STATIONS_DF)} estaciones.")
except Exception as e:
    print(f"Error cargando CSV: {e}")
    GLOBAL_STATIONS_DF = pd.DataFrame()
    GLOBAL_STATIONS_TREE = None

# ---------------------------
# UTIL (Vectorizado y Geografía)
# ---------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Calcula haversine para escalares o arrays numpy."""
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R_earth_km * c

def km_to_miles(km): return km / 1.609344
def miles_to_km(mi): return mi * 1.609344

def vectorized_segment_projection(px, py, x1, y1, x2, y2):
    """
    Calcula la distancia mínima y el factor t de un punto (px, py) 
    a múltiples segmentos definidos por arrays (x1, y1) -> (x2, y2).
    Usamos aproximación euclidiana para el factor t (proyección) por velocidad,
    y luego Haversine para la distancia real.
    """
    # Vectores segmento (vx, vy) y punto-inicio (wx, wy)
    vx, vy = x2 - x1, y2 - y1
    wx, wy = px - x1, py - y1
    
    # Producto punto y longitud cuadrada del segmento
    vv = vx*vx + vy*vy
    dot = wx*vx + wy*wy
    
    # Evitar división por cero
    with np.errstate(divide='ignore', invalid='ignore'):
        t = dot / vv
        t = np.nan_to_num(t) # Reemplazar NaN con 0 si vv es 0
    
    # Clampear t entre 0 y 1
    t = np.clip(t, 0.0, 1.0)
    
    # Punto proyectado
    projx = x1 + t*vx
    projy = y1 + t*vy
    
    # Distancia real Haversine desde el punto P hasta la proyección
    dists_km = haversine_km(py, px, projy, projx)
    
    return dists_km, t

# ---------------------------
# 1) Obtener ruta ORS (Optimizado)
# ---------------------------
def get_route_geojson(start_lat, start_lon, end_lat, end_lon, simplify=True): # Default True
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}
    
    # Empezamos con un radio grande (5000m) para evitar reintentos innecesarios
    # si los puntos están en áreas rurales (común en logística).
    radiuses_initial = [5000, 5000] 

    body = {
        "coordinates": [[start_lon, start_lat], [end_lon, end_lat]],
        "instructions": False,
        "geometry_simplify": simplify,
        "radiuses": radiuses_initial
    }

    try:
        resp = requests.post(ORS_DIRECTIONS_URL, json=body, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        
        # Si falla (ej. código 3), intentamos fallback sin radios (snap ilimitado o default)
        # o aumentamos timeout. Aquí simplificamos para reducir peticiones.
        if resp.status_code != 200:
            # Fallback simple: intentar sin 'radiuses' para dejar que ORS decida
            del body["radiuses"]
            resp = requests.post(ORS_DIRECTIONS_URL, json=body, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            
    except Exception as e:
        print(f"[ORS ERROR] {e}")

    # Fallback final: línea recta (mock)
    print("[SAFE FALLBACK] Creando línea recta por fallo de API.")
    return {
        "features": [{
            "geometry": {
                "coordinates": [[start_lon, start_lat], [end_lon, end_lat]],
                "type": "LineString"
            }
        }]
    }

def get_route_geojson_with_waypoints(coords_list):
    # Lógica similar pero para múltiples puntos
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}
    # Radio generoso para todos los waypoints para evitar errores de "Point not found"
    radiuses = [5000] * len(coords_list)

    body = {
        "coordinates": coords_list,
        "instructions": False,
        "geometry_simplify": True, # Simplificar también aquí acelera la bajada
        "radiuses": radiuses
    }

    try:
        resp = requests.post(ORS_DIRECTIONS_URL, json=body, headers=headers, timeout=20)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    return None

# ---------------------------
# 2) Procesamiento de Ruta
# ---------------------------
def route_points_and_cumdist(route_geojson):
    coords = route_geojson["features"][0]["geometry"]["coordinates"]
    # Coords vienen en [Lon, Lat], convertimos a Lat, Lon para lógica interna si prefieres,
    # pero aquí mantenemos coherencia. Usaremos Numpy arrays directamente.
    
    coords_arr = np.array(coords) # Shape (N, 2) -> Lon, Lat
    lons = coords_arr[:, 0]
    lats = coords_arr[:, 1]
    
    # Distancia acumulada vectorizada
    # Shift arrays para calcular distancia entre i e i-1
    if len(lats) > 1:
        dists = haversine_km(lats[:-1], lons[:-1], lats[1:], lons[1:])
        cumdist = np.concatenate(([0.0], np.cumsum(dists)))
    else:
        cumdist = np.array([0.0])
        
    pts = list(zip(lats, lons)) # Lista de tuplas (lat, lon) para compatibilidad
    return pts, cumdist, lats, lons

# ---------------------------
# 3) Lógica de Paradas (Vectorizada)
# ---------------------------
def point_on_route_at_distance(pts, cumdist, target_km):
    if target_km >= cumdist[-1]:
        return pts[-1], len(pts)-1, 1.0
    
    # searchsorted es muy rápido (búsqueda binaria)
    idx = np.searchsorted(cumdist, target_km)
    prev = max(0, idx - 1)
    
    start_km = cumdist[prev]
    end_km = cumdist[idx]
    seg_len = end_km - start_km
    
    frac = 0.0
    if seg_len > 0:
        frac = (target_km - start_km) / seg_len
        
    lat1, lon1 = pts[prev]
    lat2, lon2 = pts[idx]
    
    lat = lat1 + frac * (lat2 - lat1)
    lon = lon1 + frac * (lon2 - lon1)
    
    return (lat, lon), prev, frac

def best_station_for_stop(stop_point, stop_route_index, prev_route_km, 
                          route_lats, route_lons, route_cumdist, current_max_deviation_miles):
    
    lat_target, lon_target = stop_point
    radius_km = miles_to_km(current_max_deviation_miles)
    
    # 1. Query espacial rápida con BallTree (Global)
    q_rad = np.radians([[lat_target, lon_target]]) # Shape (1, 2)
    idxs = GLOBAL_STATIONS_TREE.query_radius(q_rad, r=radius_km/R_earth_km)[0]
    
    if len(idxs) == 0: 
        return None

    # Candidatos subset
    candidates = GLOBAL_STATIONS_DF.iloc[idxs].copy()
    
    # 2. Definir ventana de segmentos de ruta (Optimization)
    # Al usar simplify=True, hay menos puntos, una ventana de 100 es suficiente y segura
    window = 200 
    n_pts = len(route_lats)
    start_seg = max(0, stop_route_index - window)
    end_seg = min(n_pts - 2, stop_route_index + window)
    
    if start_seg > end_seg: # Caso borde
        start_seg = 0
        end_seg = max(0, n_pts - 2)

    # Extraer coordenadas del segmento relevante como Arrays
    # x = Lon, y = Lat
    # Segmentos van de i a i+1
    seg_lons1 = route_lons[start_seg:end_seg+1]
    seg_lats1 = route_lats[start_seg:end_seg+1]
    seg_lons2 = route_lons[start_seg+1:end_seg+2]
    seg_lats2 = route_lats[start_seg+1:end_seg+2]
    
    # Arrays de distancias acumuladas base para estos segmentos
    seg_base_cumdist = route_cumdist[start_seg:end_seg+1]
    seg_lengths = route_cumdist[start_seg+1:end_seg+2] - seg_base_cumdist

    best_candidates_list = []

    # Iteramos sobre candidatos (normalmente son pocos, ej. < 50)
    # Pero vectorizamos el cálculo contra TODOS los segmentos de la ventana a la vez
    for idx_cand, cand in candidates.iterrows():
        c_lat, c_lon = cand["latitude"], cand["longitude"]
        
        # MAGIA VECTORIZADA: Calculamos dist a 200 segmentos simultáneamente
        dists, ts = vectorized_segment_projection(
            c_lon, c_lat, 
            seg_lons1, seg_lats1, 
            seg_lons2, seg_lats2
        )
        
        # Encontrar el segmento con la distancia mínima para este candidato
        min_idx_local = np.argmin(dists)
        min_dist_km = dists[min_idx_local]
        best_t = ts[min_idx_local]
        
        # Calcular KM proyectado en ruta
        proj_km = seg_base_cumdist[min_idx_local] + best_t * seg_lengths[min_idx_local]
        
        # Filtro de progresión (no ir hacia atrás)
        if proj_km < prev_route_km - 1e-3:
            continue
            
        min_dist_km = max(min_dist_km, MIN_DEVIATION_KM) # Floor deviation
        
        score = min_dist_km * ALPHA + cand["Retail Price"] * BETA
        
        best_candidates_list.append({
            "data": cand,
            "deviation_km": min_dist_km,
            "proj_route_km": proj_km,
            "score": score
        })

    if not best_candidates_list:
        return None
        
    # Ordenar por score y devolver el mejor
    best_candidates_list.sort(key=lambda x: x["score"])
    best_obj = best_candidates_list[0]
    best_cand = best_obj["data"]
    
    return {
        "idx": int(best_cand.name), # o ID original
        "Truckstop Name": best_cand.get("Truckstop Name"),
        "City": best_cand.get("City"),
        "State": best_cand.get("State"),
        "Retail Price": float(best_cand.get("Retail Price")),
        "latitude": float(best_cand.get("latitude")),
        "longitude": float(best_cand.get("longitude")),
        "deviation_km": float(best_obj["deviation_km"]),
        "proj_route_km": float(best_obj["proj_route_km"]),
        "score": float(best_obj["score"])
    }

# ---------------------------
# PLAN TRIP (Main)
# ---------------------------
def plan_trip(start_lat, start_lon, end_lat, end_lon):
    # 1) Ruta base SIMPLIFICADA (Rápida)
    route_geo = get_route_geojson(start_lat, start_lon, end_lat, end_lon, simplify=True)
    pts_list, cumdist_arr, lats_arr, lons_arr = route_points_and_cumdist(route_geo)
    
    total_km = cumdist_arr[-1]
    total_miles = km_to_miles(total_km)

    # 2) Target stops
    n_stops = int(np.floor(total_miles / MILES_PER_STOP))
    if n_stops == 0:
        return [], pts_list, pts_list

    stop_km_markers = [miles_to_km((i+1) * MILES_PER_STOP) for i in range(n_stops)]
    
    results = []
    prev_proj_km = 0.0
    
    # 3) Buscar paradas
    for stop_km in stop_km_markers:
        # Encontrar punto aproximado en la ruta simplificada
        stop_pt, idx_seg, frac = point_on_route_at_distance(pts_list, cumdist_arr, stop_km)
        
        best = None
        # Radios crecientes pasados como argumento (no global variable modification)
        for r_miles in [MAX_DEVIATION_MILES, 50, 100, 150]:
            best = best_station_for_stop(
                stop_pt, idx_seg, prev_proj_km, 
                lats_arr, lons_arr, cumdist_arr, 
                r_miles # Pasamos el radio dinámico
            )
            if best:
                break
        
        if best:
            results.append(best)
            prev_proj_km = best["proj_route_km"]

    # 4) Recalcular ruta final pasando por los waypoints
    # Esto es necesario si quieres la geometría exacta de entrada/salida a las gasolineras
    final_route_pts = pts_list
    
    if results:
        stops_coords = [[s["longitude"], s["latitude"]] for s in results]
        coords_list = [[start_lon, start_lat]] + stops_coords + [[end_lon, end_lat]]
        
        # Llamada optimizada
        route_with_stops_geo = get_route_geojson_with_waypoints(coords_list)
        if route_with_stops_geo:
            final_route_pts, _, _, _ = route_points_and_cumdist(route_with_stops_geo)
        else:
            print("[WARN] No se pudo calcular la ruta final detallada. Usando ruta base.")

    return results, pts_list, final_route_pts, total_miles

# ---------------------------
# GEOCODIFICACIÓN US
# ---------------------------
USER_AGENT = "Mozilla/5.0 (compatible; RoutePlanner/1.0)"
def geocode_us_location(address):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "countrycodes":"us","limit":1}
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data: return None
        return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}
    except Exception as e:
        print(f"[geocode_us_location] {e}")
        return None
