import pandas as pd
import time
import requests
import json
import os

# ===============================
# CONFIG
# ===============================
INPUT_CSV = "datasets/fuel_prices_us_unique.csv"
OUTPUT_CSV = "datasets/truckstops_geocoded.csv"
CACHE_FILE = "geocode_cache.json"
SAVE_EVERY = 50
USER_AGENT = "Mozilla/5.0 (compatible; GeocoderBot/1.0)"

# ===============================
# CACHE
# ===============================
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)
else:
    cache = {}

def normalize(text):
    return text.lower().strip() if text else ""

# ===============================
# GEOCODER
# ===============================
def geocode(query):
    q_norm = normalize(query)
    if q_norm in cache:
        return cache[q_norm]

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 1}
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                lat, lon = data[0]["lat"], data[0]["lon"]
                cache[q_norm] = (lat, lon)
                return lat, lon

    except:
        pass

    cache[q_norm] = None
    return None


# ===============================
# CARGA DE DATOS
# ===============================
df = pd.read_csv(INPUT_CSV)

if os.path.exists(OUTPUT_CSV):
    df_out = pd.read_csv(OUTPUT_CSV)
else:
    df_out = df.copy()
    df_out["latitude"] = None
    df_out["longitude"] = None


# ===============================
# PROCESAMIENTO
# ===============================
changes_since_save = 0

for i in range(len(df_out)):
    if pd.notna(df_out.at[i, "latitude"]) and pd.notna(df_out.at[i, "longitude"]):
        continue

    name = df_out.at[i, "Truckstop Name"]
    city = df_out.at[i, "City"]
    state = df_out.at[i, "State"]
    address = df_out.at[i, "Address"]

    # Estrategias optimizadas
    queries = [
        f"{address}, {city}, {state}, USA",
        f"{name}, {city}, {state}, USA",
        f"{city}, {state}, USA",
        f"{state}, USA"
    ]

    coords = None
    for q in queries:
        coords = geocode(q)
        if coords:
            break
        time.sleep(1)  # rate limit Nominatim

    if coords:
        lat, lon = coords
        df_out.at[i, "latitude"] = lat
        df_out.at[i, "longitude"] = lon
        print(f"{i} ✓ {name}, {city}, {state} → {coords}")
    else:
        print(f"{i} ✗ No encontrado: {name} - {city}, {state}")

    changes_since_save += 1

    if changes_since_save >= SAVE_EVERY:
        df_out.to_csv(OUTPUT_CSV, index=False)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        print(f"💾 Guardado incremental en fila {i}")
        changes_since_save = 0


# ===============================
# GUARDADO FINAL
# ===============================
df_out.to_csv(OUTPUT_CSV, index=False)
with open(CACHE_FILE, "w", encoding="utf-8") as f:
    json.dump(cache, f, indent=2)

print("🚀 Geocodificación completada.")
