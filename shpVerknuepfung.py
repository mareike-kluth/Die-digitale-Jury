# Bemessung der 13 Bewertungskriterien
import geopandas as gpd
import pandas as pd
import os
import numpy as np
import sys
import glob

projektpfad = sys.argv[1] if len(sys.argv) > 1 else "."

layer_namen = [
    "Gebaeude",
    "Gebaeude_Umgebung",
    "Dachgruen",
    "PV_Anlage",
    "Verkehrsflaechen",
    "Verkehrsmittellinie",
    "oeffentliche_Gruenflaechen",
    "oeffentliche_Plaetze",
    "private_Gruenflaechen",
    "Wasser",
    "Baeume_Entwurf",
    "Bestandsbaeume",
    "Bestandsgruen",
    "Gebietsabgrenzung"
]

layers = {}

for name in layer_namen:
    # Durchsuche rekursiv ALLE Unterordner
    matches = glob.glob(os.path.join(projektpfad, "**", name + ".shp"), recursive=True)
    if matches:
        path = matches[0]
        print(f" Gefunden: {path}")
        layers[name] = gpd.read_file(path)
    else:
        layers[name] = None

# Kriterien berechnen
k = {}   # Dictionary für alle K-Werte

get = lambda name: layers.get(name, None)

# Gebietsflaeche berechnen (wenn Layer vorhanden)
if get("Gebietsabgrenzung") is not None:
    gebietsflaeche = get("Gebietsabgrenzung").geometry.area.sum()
else:
    gebietsflaeche = np.nan


# K002 - Zukunftsfaehige Mobilitaet 
try:
    verkehr = get("Verkehrsflaechen")
    if verkehr is None or verkehr.empty or "Nutzung" not in verkehr.columns:
        raise ValueError("Verkehrsflaechen fehlt oder hat kein Feld 'Nutzung'.")

    # Flächen nach Kategorien
    fuss_rad   = verkehr[verkehr["Nutzung"] == "Fuss_Rad"].geometry.area.sum()
    kfz        = verkehr[verkehr["Nutzung"] == "Kfz_Flaeche"].geometry.area.sum()
    begegnung  = verkehr[verkehr["Nutzung"] == "Begegnungszone"].geometry.area.sum()

    # Auto-lastige Fläche = Auto + 0.5 * Begegnungszone
    auto_flaeche = kfz + 0.5 * begegnung

    # Verhältnis berechnen
    if auto_flaeche == 0 and fuss_rad > 0:
        # Komplett autofrei → Bestnote
        k["K002"] = 5
    else:
        ratio = fuss_rad / auto_flaeche if auto_flaeche > 0 else 0

        if ratio > 2:
            k["K002"] = 4
        elif ratio > 1:
            k["K002"] = 3
        elif ratio > 0.5:
            k["K002"] = 2
        else:
            k["K002"] = 1

except Exception as e:
    k["K002"] = np.nan
    

# K003 - Anteil der Gruenflaechen
try:
    gruenflaeche = sum([
        get("oeffentliche_Gruenflaechen").geometry.area.sum() if get("oeffentliche_Gruenflaechen") is not None else 0,
        get("private_Gruenflaechen").geometry.area.sum() if get("private_Gruenflaechen") is not None else 0,
        get("Wasser").geometry.area.sum() if get("Wasser") is not None else 0
    ])
    k["K003"] = round(gruenflaeche / gebietsflaeche, 2) if gebietsflaeche > 0 else np.nan
except:
    k["K003"] = np.nan


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


# K005 - Lärmschutz 
try:
    g = get("Gebaeude")
    v = get("Verkehrsflaechen")

    if g is not None and v is not None and "Geb_Hoehe" in g.columns and "Nutzung" in v.columns:
        # Kopien & Datentypen
        g = g.copy()
        v = v.copy()
        g["Geb_Hoehe"] = pd.to_numeric(g["Geb_Hoehe"], errors="coerce")

        # Nutzung vereinheitlichen (für robuste Abfragen)
        v["Nutzung_clean"] = (
            v["Nutzung"].astype(str).str.strip().str.lower().str.replace("_", "", regex=False)
        )

        # MIV-Flächen: Kfz_Flaeche ∪ Begegnungszone
        miv_mask = (
            v["Nutzung"].isin(["Kfz_Flaeche", "Begegnungszone"]) |
            v["Nutzung_clean"].isin(["kfzflaeche", "begegnungszone"])
        )
        miv = v.loc[miv_mask]

        if not miv.empty:
            # 10-m-Puffer um MIV-Flächen und Gebäude in der Nähe markieren
            miv_union = miv.buffer(10).unary_union
            g["an_miv"] = g.intersects(miv_union)

            # Höhenvergleich (nur mit validen Höhen)
            hoehe_miv = g.loc[g["an_miv"], "Geb_Hoehe"].mean()
            hoehe_sonstige = g.loc[~g["an_miv"], "Geb_Hoehe"].mean()

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
except Exception:
    k["K005"] = np.nan


# K006 - Erhalt Bestandsgebaeude
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
    

# K008 - Nutzungsvielfalt Freiflaechen
try:
    oeff = get("oeffentliche_Gruenflaechen")
    plaetze = get("oeffentliche_Plaetze")

    kategorien = set()

    # Nutzungen aus öffentlichen Grünflächen
    if oeff is not None and not oeff.empty and "Nutzung" in oeff.columns:
        cats = (
            oeff["Nutzung"]
            .dropna()
            .astype(str).str.strip().str.lower()
        )
        kategorien.update([c for c in cats if c != ""])

    # +1, wenn öffentliche Plätze vorhanden (Layer existiert und hat mind. ein Feature)
    platz_bonus = 1 if (plaetze is not None and not plaetze.empty) else 0

    gesamt = len(kategorien) + platz_bonus
    k["K008"] = gesamt if gesamt > 0 else np.nan

except Exception:
    k["K008"] = np.nan
    

# K009 - Zugang zum Wasser 
try:
    wasser = get("Wasser")
    oeff = get("oeffentliche_Gruenflaechen")
    if wasser is not None and not wasser.empty and oeff is not None and not oeff.empty:
        oeff_union = oeff.unary_union.buffer(2)  # Puffer nur einmal, Union ist stabil
        wasser["an_oeff"] = wasser.intersects(oeff_union)

        if wasser["an_oeff"].any():
            k["K009"] = 2  # Erlebbar
        else:
            k["K009"] = 1  # Funktional
    elif wasser is not None and not wasser.empty:
        k["K009"] = 1
    else:
        k["K009"] = 0
except Exception as e:
    k["K009"] = np.nan
    

# K010 - Entsiegelung
# Veränderung des Grünflächenanteils (neu vs. Bestand)
try:
    alt = get("Bestandsgruen")
    oeff = get("oeffentliche_Gruenflaechen")
    priv = get("private_Gruenflaechen")

    # Keine neuen Grünflächen vorhanden -> keine Verbesserung
    if oeff is None and priv is None:
        k["K010"] = 0.0
    else:
        neu = (
            (oeff.geometry.area.sum() if oeff is not None else 0.0) +
            (priv.geometry.area.sum() if priv is not None else 0.0)
        )

        if gebietsflaeche and gebietsflaeche > 0:
            # Wenn Bestandsgrün vorhanden: klassische Differenz
            if alt is not None and not alt.empty:
                altf = alt.geometry.area.sum()
                k["K010"] = round((neu - altf) / gebietsflaeche, 2)
            else:
                # Kein Bestandsgrün: positiv werten (Proxy = neu / Gebietsfläche)
                k["K010"] = round(neu / gebietsflaeche, 2)
        else:
            k["K010"] = np.nan
except Exception:
    k["K010"] = np.nan
    

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
    

# K015 - Zonierung Freiflaechen
try:
    hat_oeff = get("oeffentliche_Gruenflaechen") is not None and not get("oeffentliche_Gruenflaechen").empty
    hat_priv = get("private_Gruenflaechen") is not None and not get("private_Gruenflaechen").empty
    k["K015"] = 1 if hat_oeff and hat_priv else 0
except:
    k["K015"] = np.nan
   
# Endausgabe der Kriterienbewertung aller Kriterien
df_kriterien = pd.DataFrame([k])
df_kriterien.to_excel(os.path.join(projektpfad, "Kriterien_Ergebnisse.xlsx"), index=False)















