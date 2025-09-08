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
    oeff = get("oeffentliche_Gruenflaechen")
    priv = get("private_Gruenflaechen")

    fl_oeff = oeff.geometry.area.sum() if oeff is not None else 0.0
    fl_priv = priv.geometry.area.sum() if priv is not None else 0.0

    gruenflaeche = fl_oeff + fl_priv
    k["K003"] = round(gruenflaeche / gebietsflaeche, 2) if (gebietsflaeche and gebietsflaeche > 0) else np.nan
except Exception:
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

        # Nutzung normalisieren und nur Kfz-Flächen wählen
        v["Nutzung_clean"] = v["Nutzung"].astype(str).str.lower().str.replace("_", "", regex=False)
        kfz = v[v["Nutzung_clean"] == "kfzflaeche"]

        if not kfz.empty:
            # 10-m-Puffer um Kfz-Flächen, Gebäude in Nähe markieren
            kfz_puffer_union = kfz.buffer(10).unary_union
            g["an_kfz"] = g.intersects(kfz_puffer_union)

            # Höhenvergleich (nahe Kfz vs. übrige)
            hoehe_nahe = g.loc[g["an_kfz"], "Geb_Hoehe"].mean()
            hoehe_fern = g.loc[~g["an_kfz"], "Geb_Hoehe"].mean()

            if pd.notna(hoehe_nahe) and pd.notna(hoehe_fern):
                if hoehe_nahe > hoehe_fern:
                    k["K005"] = 2
                elif hoehe_nahe == hoehe_fern:
                    k["K005"] = 1
                else:
                    k["K005"] = 0
            else:
                k["K005"] = np.nan
        else:
            # Keine Kfz-Flächen identifiziert
            k["K005"] = np.nan
    else:
        # Fehlende Daten/Spalten
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
    wasser  = get("Wasser")
    oeff    = get("oeffentliche_Gruenflaechen")
    plaetze = get("oeffentliche_Plaetze")

    if wasser is not None and not wasser.empty:
        access_layers = [gdf for gdf in (oeff, plaetze) if gdf is not None and not gdf.empty]

        if access_layers:
            # Geometrien zusammenführen und Shapely-2-kompatibel vereinigen
            geoms = pd.concat([gdf.geometry for gdf in access_layers], ignore_index=True)
            access_union = geoms.union_all() if hasattr(geoms, "union_all") else geoms.unary_union
            access_buf = access_union.buffer(2)

            # Wasser an öffentlichen Grünflächen/Plätzen (mit 2 m Puffer) erlebbar?
            is_accessible = wasser.intersects(access_buf).any()
            k["K009"] = 2 if is_accessible else 1
        else:
            # Wasser vorhanden, aber keine öffentlichen Zugangsflächen
            k["K009"] = 1
    else:
        # Kein Wasser im Gebiet
        k["K009"] = 0
except Exception:
    k["K009"] = np.nan


# K010 - Entsiegelung
# Veränderung des Grünflächenanteils (neu vs. Bestand)
try:
    alt  = get("Bestandsgruen")
    oeff = get("oeffentliche_Gruenflaechen")
    priv = get("private_Gruenflaechen")

    if not (gebietsflaeche and gebietsflaeche > 0):
        k["K010"] = np.nan
    else:
        neu_gruen = (
            (oeff.geometry.area.sum() if oeff is not None else 0.0) +
            (priv.geometry.area.sum() if priv is not None else 0.0)
        )

        if alt is None:
            # Layer fehlt -> Zero-Fill (kein Bonus)
            k["K010"] = 0.0
        elif alt.empty:
            # Layer existiert, aber leer -> Anteil der neuen Grünflächen (ohne Wasser)
            k["K010"] = round(neu_gruen / gebietsflaeche, 2)
        else:
            # Klassische Differenz neu(ohne Wasser) - alt
            altf = alt.geometry.area.sum()
            k["K010"] = round((neu_gruen - altf) / gebietsflaeche, 2)
except Exception:
    k["K010"] = np.nan


# K011 - Rettungswege, Mindestwegbreite
try:
    ml = get("Verkehrsmittellinie")
    g  = get("Gebaeude")
    go = get("oeffentliche_Gruenflaechen")
    gp = get("private_Gruenflaechen")
    pl = get("oeffentliche_Plaetze") 

    if ml is None or ml.empty:
        k["K011"] = np.nan
    else:
        # Referenz-CRS wählen (für Meter-Puffer)
        ref = next((df.crs for df in (ml,g,go,gp,pl) if df is not None and df.crs is not None), "EPSG:25832")

        def align(df):
            if df is None or df.empty: return None
            if df.crs is None: return df.set_crs(ref)
            return df if df.crs == ref else df.to_crs(ref)

        ml, g, go, gp, pl = map(align, (ml, g, go, gp, pl))

        # Blocker sammeln (nur Polygone) und vereinen
        polys = []
        for df, src in ((g,"Gebaeude"), (go,"oeffentliche_Gruenflaechen"),
                        (gp,"private_Gruenflaechen"), (pl,"oeffentliche_Plaetze")):
            if df is not None and not df.empty:
                p = df[df.geometry.notna()]
                p = p[p.geometry.type.isin(["Polygon","MultiPolygon"])].copy()
                if not p.empty:
                    p["quelle"] = src
                    p["geometry"] = p.geometry.buffer(0)  # Invalids fixen
                    polys.append(p[["geometry","quelle"]])

        if not polys:
            k["K011"] = 1
        else:
            blockers = gpd.GeoDataFrame(pd.concat(polys, ignore_index=True), geometry="geometry", crs=ref)

            # 3-m-Korridor (±1.5 m) um Mittellinien
            corridors = ml.geometry.buffer(1.5).buffer(0)
            try:
                from shapely import union_all
                corridor_u = union_all(corridors)
            except Exception:
                corridor_u = corridors.unary_union

            # Exakte Schnittflächen (nur echte Fläche > Schwelle zählt)
            MIN_OVERLAP_M2 = 0.01
            cgdf = gpd.GeoDataFrame(geometry=[corridor_u], crs=ref)
            mask = blockers.intersects(corridor_u)
            inter = gpd.overlay(blockers.loc[mask], cgdf, how="intersection") if mask.any() else \
                    gpd.GeoDataFrame(columns=["geometry","quelle"], geometry="geometry", crs=ref)
            inter["area_m2"] = inter.geometry.area if not inter.empty else []

            has_overlap = (inter["area_m2"] > MIN_OVERLAP_M2).any() if not inter.empty else False
            k["K011"] = 0 if has_overlap else 1

            # Kurze Debug-Ausgabe
            tot = float(inter.loc[inter["area_m2"] > MIN_OVERLAP_M2, "area_m2"].sum()) if has_overlap else 0.0
            print(f"[K011] has_overlap={has_overlap} → Score={k['K011']} | sum>{MIN_OVERLAP_M2}m²: {tot:.6f}", flush=True)

except Exception:
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
