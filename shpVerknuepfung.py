"""
created: 2025
@author: Mareike Kluth
purpose: Diplomarbeit - Die digitale Jury
"""
# SHP verarbeiten → K001–K015
import geopandas as gpd
import pandas as pd
import os
import numpy as np
import sys

# Projektpfad
projektpfad = sys.argv[1] if len(sys.argv) > 1 else "C:/Project_shp/"

# Hilfsfunktion zum sicheren Laden
layer_namen = [
    "Gebaeude",
    "Gebaeude_Umgebung",
    "Dachgruen",
    "PV_Anlage",
    "Verkehrsflaechen",
    "Verkehrsmittellinie",
    "oeffentliche_Gruenflaechen",
    "private_Gruenflaechen",
    "Wasser",
    "Baeume_Entwurf",
    "Bestandsbaeume",
    "Bestandsgruen",
    "Gebietsabgrenzung"
]

layers = {}
for name in layer_namen:
    path = os.path.join(projektpfad, name + ".shp")
    try:
        layers[name] = gpd.read_file(path)
    except Exception:
        layers[name] = None
        print(f"Layer '{name}.shp' ist nicht vorhanden.")

# Kriterien berechnen
k = {}   # Dictionary für alle K-Werte
# Hilfsfunktion zur sicheren Abfrage eines Layers
get = lambda name: layers.get(name, None)

# Gebietsflaeche nur berechnen, wenn Layer vorhanden
if get("Gebietsabgrenzung") is not None:
    gebietsflaeche = get("Gebietsabgrenzung").geometry.area.sum()
else:
    gebietsflaeche = np.nan

# K002 - zukunftsfaehige Mobilitaet
# Fläche für nachhaltige Mobilität: Nur "Fuss_Rad"
try:
    verkehr = get("Verkehrsflaechen")
    fuss_rad = verkehr[verkehr["Nutzung"] == "Fuss_Rad"].geometry.area.sum()
    miv = verkehr[verkehr["Nutzung"].isin(["Auto_Fuss_Rad", "Stellplatz", "halbgruener_Stellplatz"])]
    miv_flaeche = miv.geometry.area.sum()
    ratio = fuss_rad / miv_flaeche if miv_flaeche > 0 else 0
    if miv_flaeche == 0 and fuss_rad > 0:
        k["K002"] = 5
    elif ratio > 2:
        k["K002"] = 4
    elif ratio > 1:
        k["K002"] = 3
    elif ratio > 0.5:
        k["K002"] = 2
    else:
        k["K002"] = 1
except:
    k["K002"] = np.nan
    print("K002: Mobilitätsbewertung konnte nicht durchgeführt werden.")

# K003 - Anteil der Freiflaechen
try:
    gruenflaeche = sum([
        get("oeffentliche_Gruenflaechen").geometry.area.sum() if get("oeffentliche_Gruenflaechen") is not None else 0,
        get("private_Gruenflaechen").geometry.area.sum() if get("private_Gruenflaechen") is not None else 0,
        get("Wasser").geometry.area.sum() if get("Wasser") is not None else 0
    ])
    k["K003"] = round(gruenflaeche / gebietsflaeche, 2) if gebietsflaeche > 0 else np.nan
except:
    k["K003"] = np.nan
    print("K003: Anteil der Freiflächen konnte nicht berechnet werden.")

# K004 - Einbettung in die Umgebung
try:
    g = get("Gebaeude")
    b = get("Gebaeude_Umgebung")
    if g is not None and b is not None:
        koernigkeit = g.geometry.area.mean() / b.geometry.area.mean()
        if 0.75 <= koernigkeit <= 1.25:
            k["K004"] = 2
        elif 0.5 <= koernigkeit < 0.75 or 1.25 < koernigkeit <= 1.5:
            k["K004"] = 1.5
        else:
            k["K004"] = 1
    else:
        raise ValueError
except:
    k["K004"] = np.nan
    print("K004: Einbettung in Umgebung konnte nicht berechnet werden.")

# ----- K005 - Laermschutz ------
try:
    g = get("Gebaeude")
    v = get("Verkehrsflaechen")
    if g is not None and v is not None and "Geb_Hoehe" in g.columns:
        g["Geb_Hoehe"] = pd.to_numeric(g["Geb_Hoehe"], errors="coerce")
        miv = v[v["Nutzung"].isin(["Auto_Fuss_Rad"])]
        if not miv.empty:
            miv_puffer = miv.buffer(10)
            g["an_miv"] = g.intersects(miv_puffer.geometry.union_all())

            hoehe_miv = g[g["an_miv"]]["Geb_Hoehe"].mean()
            hoehe_sonstige = g[~g["an_miv"]]["Geb_Hoehe"].mean()

            if pd.notna(hoehe_miv) and pd.notna(hoehe_sonstige):
                if hoehe_miv > hoehe_sonstige:
                    k["K005"] = 2
                elif hoehe_miv == hoehe_sonstige:
                    k["K005"] = 1
                else:
                    k["K005"] = 0
            else:
                k["K005"] = np.nan
        else:
            k["K005"] = np.nan
    else:
        raise ValueError
except:
    k["K005"] = np.nan
    print("K005: Lärmschutzbewertung konnte nicht berechnet werden.")

# K006 - Erhalt Bestandsgebaeude
# Anteil neuer Gebäude, die auf Bestand stehen
try:
    gebaeude = get("Gebaeude")
    gebaeude_bestand = get("Gebaeude_Umgebung")
    gebietsgrenze = get("Gebietsabgrenzung")
    if gebaeude is not None and gebaeude_bestand is not None and gebietsgrenze is not None:
        bestand_clip = gpd.clip(gebaeude_bestand, gebietsgrenze)
        g_poly = gebaeude[gebaeude.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
        bestand_poly = bestand_clip[bestand_clip.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
        bestand_poly = bestand_poly.reset_index(drop=False).rename(columns={"index": "bestand_id"})
        bestand_poly["geometry"] = bestand_poly.geometry.buffer(0.20)
        ueberlappung = gpd.overlay(g_poly, bestand_poly, how="intersection", keep_geom_type=False)
        anzahl_neu = g_poly.shape[0]
        anzahl_ueberlappt = ueberlappung["bestand_id"].nunique()
        k["K006"] = round(min(anzahl_ueberlappt / anzahl_neu, 1), 2) if anzahl_neu > 0 else np.nan
    else:
        raise ValueError
except:
    k["K006"] = np.nan
    print("K006: Erhalt Bestandsgebäude konnte nicht berechnet werden.")

# K007 - energetische Standards: Anteil PV-Anlagen
# Verhältnis PV-Fläche zu gesamter Gebäudefläche (als Dachfläche angenommen)
try:
    g = get("Gebaeude")
    pv = get("PV_Anlage")
    if g is not None and pv is not None:
        flaeche_gesamt = g.geometry.area.sum()
        flaeche_pv = pv.geometry.area.sum()
        k["K007"] = round(flaeche_pv / flaeche_gesamt, 2) if flaeche_gesamt > 0 else np.nan
    else:
        raise ValueError
except:
    k["K007"] = np.nan
    print("K007: Anteil PV-Anlagen konnte nicht berechnet werden.")

# K008 - vielfaeltige Freiflaechen
try:
    oeff = get("oeffentliche_Gruenflaechen")
    if oeff is not None and "Nutzung" in oeff.columns:
        nutzungen = oeff["Nutzung"].dropna().unique()
        k["K008"] = len(nutzungen)
    else:
        raise ValueError
except:
    k["K008"] = np.nan
    print("K008: Vielfältige Freiflächen konnten nicht berechnet werden.")

# K009 - Zugang zum Wasser
# Skala: 0 = kein Wasser, 1 = funktional, 2 = erlebbar
try:
    wasser = get("Wasser")
    oeff = get("oeffentliche_Gruenflaechen")
    if wasser is not None and oeff is not None:
        buffer = oeff.copy()
        buffer["geometry"] = buffer.geometry.buffer(2)
        wasser["an_oeff"] = wasser.intersects(buffer.geometry.union_all())
        if wasser["an_oeff"].any():
            k["K009"] = 2
        else:
            k["K009"] = 1
    elif wasser is not None:
        k["K009"] = 1
    else:
        k["K009"] = 0
except:
    k["K009"] = np.nan
    print("K009: Zugang zum Wasser konnte nicht bewertet werden.")

# K010 - Entsiegelung
# Veränderung des Grünflächenanteils (neu vs. Bestand)
try:
    alt = get("Bestandsgruen")
    oeff = get("oeffentliche_Gruenflaechen")
    priv = get("private_Gruenflaechen")
    if alt is not None and (oeff is not None or priv is not None):
        altf = alt.geometry.area.sum() if alt is not None else 0
        neu = (oeff.geometry.area.sum() if oeff is not None else 0) + (priv.geometry.area.sum() if priv is not None else 0)
        k["K010"] = round((neu - altf) / gebietsflaeche, 2) if gebietsflaeche > 0 else np.nan
    else:
        raise ValueError
except:
    k["K010"] = np.nan
    print("K010: Entsiegelung konnte nicht berechnet werden.")

# K011 - Rettungswege, Mindestwegbreite
try:
    mittellinie = get("Verkehrsmittellinie")
    g = get("Gebaeude")
    oeff = get("oeffentliche_Gruenflaechen")
    priv = get("private_Gruenflaechen")
    if mittellinie is not None and (g is not None or oeff is not None or priv is not None):
        puffer = mittellinie.copy()
        puffer["geometry"] = puffer.geometry.buffer(1.5)
        ziel = pd.concat([
            df for df in [g, oeff, priv] if df is not None
        ], ignore_index=True)
        u = gpd.overlay(puffer, ziel, how="intersection", keep_geom_type=False)
        k["K011"] = 0 if not u.empty else 1
    else:
        raise ValueError
except:
    k["K011"] = np.nan
    print("K011: Rettungswege konnten nicht überprüft werden.")

# K012 - Anteil Dachbegruenung
# Gesamte Gebäudefläche = angenommene Dachfläche
try:
    dach = get("Dachgruen")
    g = get("Gebaeude")
    if g is not None and dach is not None:
        flaeche_gesamt = g.geometry.area.sum()
        flaeche_dach = dach.geometry.area.sum()
        k["K012"] = round(flaeche_dach / flaeche_gesamt, 2) if flaeche_gesamt > 0 else np.nan
    else:
        raise ValueError
except:
    k["K012"] = np.nan
    print("K012: Dachbegrünung konnte nicht berechnet werden.")

# K013 - Erhalt Baumbestand
try:
    neu = get("Baeume_Entwurf")
    alt = get("Bestandsbaeume")
    if neu is not None and alt is not None and not neu.empty and not alt.empty:
        preserved = gpd.sjoin_nearest(neu, alt, how="left", max_distance=1, distance_col="dist")
        anzahl = preserved.dropna(subset=["dist"]).shape[0]
        k["K013"] = round(anzahl / neu.shape[0], 2)
    else:
        raise ValueError
except:
    k["K013"] = np.nan
    print("K013: Erhalt Baumbestand konnte nicht berechnet werden.")


# K015 - Zonierung Freiflaechen
try:
    hat_oeff = get("oeffentliche_Gruenflaechen") is not None and not get("oeffentliche_Gruenflaechen").empty
    hat_priv = get("private_Gruenflaechen") is not None and not get("private_Gruenflaechen").empty
    k["K015"] = 1 if hat_oeff and hat_priv else 0
except:
    k["K015"] = np.nan
    print("K015: Zonierung Freiflächen konnte nicht bewertet werden.")

# Endausgabe der Kriterienbewertung aller Kriterien
df_kriterien = pd.DataFrame([k])
df_kriterien.to_excel(os.path.join(projektpfad, "Kriterien_Ergebnisse.xlsx"), index=False)
print("Kriterienbewertung", k)
