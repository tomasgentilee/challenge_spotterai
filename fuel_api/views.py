import os
import uuid
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import folium

# Asegúrate de que plan_trip devuelve 4 valores ahora
from .utils import geocode_us_location, plan_trip

@api_view(["POST"])
def generate_route(request):
    origin = request.data.get("origin")
    destination = request.data.get("destination")

    if not origin or not destination:
        return Response(
            {"error": "Se requieren 'origin' y 'destination'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- 1. Geocodificación ---
    try:
        origin_coords = geocode_us_location(origin)
        destination_coords = geocode_us_location(destination)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if not origin_coords or not destination_coords:
        return Response({"error": "Ubicación no encontrada en USA"}, status=status.HTTP_404_NOT_FOUND)

    lat1, lon1 = origin_coords["lat"], origin_coords["lon"]
    lat2, lon2 = destination_coords["lat"], destination_coords["lon"]

    # --- 2. Planificación (Utils) ---
    try:
        # Desempaquetamos los 4 valores (incluyendo total_miles)
        stops, route_pts, opt_route_pts, total_miles = plan_trip(lat1, lon1, lat2, lon2)
    except Exception as e:
        print(f"[ERROR] {e}")
        return Response({"error": "Error de cálculo de ruta"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # --- 3. Cálculos de Combustible y Costos ---
    MPG = 10.0
    total_gallons = total_miles / MPG
    
    # Calcular precio promedio del combustible en esta ruta
    # Si hay paradas, usamos el promedio de sus precios.
    # Si no hay paradas (viaje corto), usamos un precio base estimado (ej. $3.80) o 0.
    avg_fuel_price = 0.0
    if stops:
        avg_fuel_price = sum(s["Retail Price"] for s in stops) / len(stops)
    else:
        # Fallback opcional si el viaje es < 450 millas y no para
        avg_fuel_price = 3.80 

    total_money_spent = total_gallons * avg_fuel_price

    # --- 4. Mapa (Folium) ---
    mid_lat, mid_lon = (lat1 + lat2) / 2, (lon1 + lon2) / 2
    m = folium.Map(location=[mid_lat, mid_lon], zoom_start=6)

    folium.Marker([lat1, lon1], tooltip=f"Start: {origin}", icon=folium.Icon(color="green", icon="play")).add_to(m)
    folium.Marker([lat2, lon2], tooltip=f"End: {destination}", icon=folium.Icon(color="red", icon="stop")).add_to(m)

    final_route = opt_route_pts if opt_route_pts else route_pts
    if final_route:
        folium.PolyLine(final_route, weight=5, opacity=0.7, color="blue").add_to(m)

    for i, stop in enumerate(stops, 1):
        info = (f"<b>Stop #{i}</b><br>{stop['Truckstop Name']}<br>"
                f"Price: ${stop['Retail Price']}<br>Dev: {stop['deviation_km']:.1f}km")
        folium.Marker(
            [stop["latitude"], stop["longitude"]],
            popup=folium.Popup(info, max_width=200),
            icon=folium.Icon(color="orange", icon="gas-pump", prefix="fa")
        ).add_to(m)

    # Guardar Mapa
    output_dir = os.path.join(settings.MAPS_ROOT)
    os.makedirs(output_dir, exist_ok=True)

    filename = f"route_{uuid.uuid4().hex}.html"
    filepath = os.path.join(output_dir, filename)
    
    m.save(filepath)

    map_url = f"{settings.MEDIA_URL}{filename}"

    # --- 5. Respuesta Final ---
    return Response({
        "route_summary": {
            "origin": origin,
            "destination": destination,
            "total_distance_miles": round(total_miles, 2),
            "total_fuel_gallons": round(total_gallons, 2),
            "total_fuel_cost": round(total_money_spent, 2),
            "average_price_paid": round(avg_fuel_price, 3)
        },
        "stops": stops,
        "map_url": map_url,
    })