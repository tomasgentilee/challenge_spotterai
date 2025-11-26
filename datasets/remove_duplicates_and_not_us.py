import pandas as pd

# Cargar el dataset original
df = pd.read_csv("datasets\\fuel-prices-for-be-assessment.csv")

# ---------------------------
# 1. Filtrar solo direcciones en Estados Unidos
# ---------------------------

# Lista oficial de abreviaturas de estados de USA
us_states = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS",
    "KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY",
    "NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV",
    "WI","WY"
}

df_us = df[df["State"].isin(us_states)].copy()

# ---------------------------
# 2. Crear clave única por dirección
# ---------------------------

df_us["address_key"] = (
    df_us["Address"].str.strip() + ", " +
    df_us["City"].str.strip() + ", " +
    df_us["State"].str.strip()
)

# ---------------------------
# 3. Eliminar direcciones repetidas
# ---------------------------

df_unique = df_us.drop_duplicates(subset=["address_key"])

# ---------------------------
# 4. Guardar el nuevo CSV
# ---------------------------

df_unique.to_csv("datasets\\fuel_prices_us_unique.csv", index=False)

print("✔ Archivo creado: fuel_prices_us_unique.csv")
print(f"✔ Filas originales: {len(df)}")
print(f"✔ Filas en USA: {len(df_us)}")
print(f"✔ Direcciones únicas: {len(df_unique)}")
