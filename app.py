import streamlit as st
import zipfile
import tempfile
import os
import shutil
import subprocess
import pandas as pd
import geopandas as gpd
import joblib
import glob
import sys


# Einstellungen & Metadaten

st.set_page_config(
    page_title="Die Digitale Jury",
    layout="centered"
)
st.title("Die Digitale Jury – objektive Bewertung städtebaulicher Entwürfe")
st.markdown("""
######
Willkommen bei der **digitalen Jury**!  
Dieses Tool bewertet städtebauliche Entwürfe **automatisch** anhand von **13 Kriterien** mit einem trainierten **Random-Forest-Modell**.

---

### **So funktioniert es**

**Entwurf vorbereiten:**  
Speichere deine Geodaten der Entwürfe im **Shapefile-Format** (`.shp`) mit den **exakten Dateinamen** (siehe Tabelle unten).  
Jedes `.shp` benötigt seine zugehörigen Begleitdateien (`.shx`, `.dbf`, `.prj`).  
Diese müssen **alle zusammen** in **einer ZIP-Datei** gepackt werden.

Die Kriterien werden automatisch berechnet, fehlende Werte werden mit `0` ersetzt.  
Die **Digitale Jury** vergibt jedem Entwurf eine objektive Bewertung von **1 bis 5 Sternen**.

---

### **Benötigte Dateien und Datenstruktur**

**Wichtig:** 
In jeder Shapefile müssen die unten genannten **Spalten (Felder)** in der Attributtabelle korrekt vorhanden sein.  
Jedes Objekt, wie z. B. ein Gebäude oder eine Fläche, ist dabei eine **Zeile** in der Tabelle.  
Die **Layer-Namen**, **Spalten-Namen** und **Attributwerte** müssen **exakt** so geschrieben sein, wie unten angegeben. Beachte auch die Groß- und Kleinschreibung. 
Alle Dateien müssen im passenden **Koordinatensystem** vorliegen.

Verwende **korrekte, vollständige Geometrien** – leere oder fehlerhafte Layer führen zu unvollständigen Ergebnissen.
Wenn ein Layer oder Attribut fehlt oder falsch benannt ist, kann das entsprechende Kriterium **nicht berechnet werden** und wird automatisch mit `0` bewertet.

Bitte stelle sicher, dass deine ZIP-Datei folgende Layer enthält (sofern vorhanden):

| Layer | Benötigte Spalten |
|-----------------------------|------------------------------|
| `Gebaeude.shp` | `Geb_Hoehe` |
| `Gebaeude_Umgebung.shp` | – |
| `Dachgruen.shp` | – | 
| `PV_Anlage.shp` | – | 
| `Verkehrsflaechen.shp` | `Nutzung` mit `Fuss_Rad`, `Kfz_Flaeche`, `Begegnungszone`
| `Verkehrsmittellinie.shp` | – |
| `oeffentliche_Gruenflaechen.shp` | `Nutzung` | 
| `private_Gruenflaechen.shp` | – |
| `oeffentliche_Plaetze` | – |
| `Wasser.shp` | – |
| `Baeume_Entwurf.shp` | – | 
| `Bestandsbaeume.shp` | – | 
| `Bestandsgruen.shp` | – | 
| `Gebietsabgrenzung.shp` | – | 

---


### **Hochladen**

Nutze das Upload-Feld unten, um deine **ZIP-Datei** hochzuladen.  
Du kannst auch **mehrere ZIPs gleichzeitig** hochladen, um Entwürfe direkt zu vergleichen.

---

### **Ergebnis & Download**

Nach der automatischen Bewertung kannst du:
- alle berechneten Kriterien und die Sternebewertung einsehen
- die Ergebnisse als **Excel-Datei herunterladen**

""")


uploaded_files = st.file_uploader(
    "Entwürfe als ZIP hochladen",
    type="zip",
    accept_multiple_files=True
)

MODEL_PATH = "final_RF_model.pkl"

try:
    bundle = joblib.load(MODEL_PATH)
    if isinstance(bundle, dict) and "model" in bundle and "features" in bundle:
        rf_model = bundle["model"]
        FEATURE_ORDER = bundle["features"]
    else:
        rf_model = bundle  # altes Format
        # >>> EXAKT die Trainings-Featureliste angeben (z. B. ohne K001 & K014) <<<
        FEATURE_ORDER = ["K002","K003","K004","K005","K006","K007","K008","K009","K010","K011","K012","K013","K015"]
except Exception as e:
    st.error(f"Bewertungsmodell konnte nicht geladen werden: {e}")
    st.stop()

if uploaded_files:
    for zip_file in uploaded_files:
        st.write(f"Hochgeladen: `{zip_file.name}`")
        with st.spinner("Verarbeite Entwurf ..."):
            with tempfile.TemporaryDirectory() as tmpdir:
                # Entpacken
                with zipfile.ZipFile(zip_file, "r") as zip_ref:
                    zip_ref.extractall(tmpdir)

                # Erwartete Layer prüfen
                erwartete_layer = [
                    "Gebaeude.shp", "Gebaeude_Umgebung.shp", "Verkehrsflaechen.shp", "Verkehrsmittellinie.shp",
                    "Dachgruen.shp", "PV_Anlage.shp", "oeffentliche_Gruenflaechen.shp", "private_Gruenflaechen.shp",
                    "oeffentliche_Plaetze.shp", "Wasser.shp", "Baeume_Entwurf.shp", "Bestandsbaeume.shp",
                    "Bestandsgruen.shp", "Gebietsabgrenzung.shp"
                ]
                fehlen = [layer for layer in erwartete_layer if not glob.glob(os.path.join(tmpdir, layer))]
                if fehlen:
                    st.warning(f"Achtung: Folgende Layer fehlen: {', '.join(fehlen)}")

                # Layer- & Attribut-Check
                erwartete_attributs = {
                    "Verkehrsflaechen": ["Nutzung"],
                    "Gebaeude": ["Geb_Hoehe"],
                    "oeffentliche_Gruenflaechen": ["Nutzung"]
                }
                for layer_name, attrs in erwartete_attributs.items():
                    shp_path = os.path.join(tmpdir, f"{layer_name}.shp")
                    if os.path.exists(shp_path):
                        layer = gpd.read_file(shp_path)
                        for attr in attrs:
                            if attr not in layer.columns:
                                st.warning(f" `{attr}` fehlt in `{layer_name}.shp`")
                    else:
                        st.warning(f" `{layer_name}.shp` fehlt!")

                # Skript ausführen (berechnet K002–K015 und schreibt Kriterien_Ergebnisse.xlsx)
                shutil.copy("shpVerknuepfung.py", tmpdir)
                result = subprocess.run(
                    [sys.executable, "shpVerknuepfung.py", tmpdir],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True
                )
                if result.stderr:
                    st.info("Log aus shpVerknuepfung.py:")
                    st.code(result.stderr)

                # Ergebnisse einlesen & Modell anwenden
                kriterien_path = os.path.join(tmpdir, "Kriterien_Ergebnisse.xlsx")
                if os.path.exists(kriterien_path):
                    df = pd.read_excel(kriterien_path).fillna(0)

                    # --- Feature-Matrix exakt wie im Training herstellen ---
                    for col in FEATURE_ORDER:
                        if col not in df.columns:
                            df[col] = 0.0
                    df_features = df[FEATURE_ORDER].copy()

                    # Diagnose: Null-Anteil
                    zero_share = (df_features == 0).mean(axis=1).iloc[0] if not df_features.empty else 1.0
                    st.write(f"🧪 Null-Anteil im Featurevektor: {zero_share:.0%}")
                    if zero_share >= 0.8:
                        st.warning("Sehr viele 0-Werte → wenig Signal. Ergebnis kann in die Mehrheitsklasse kippen (z. B. 2 Sterne).")

                    # Vorhersage
                    try:
                        prediction = rf_model.predict(df_features)[0]
                        sterne = int(prediction)
                        st.success(f"⭐️ Bewertung: **{sterne} Sterne**")
                    except Exception as e:
                        st.error(f"Vorhersage fehlgeschlagen: {e}")
                        st.stop()

                    # Für UI-Tabelle: schöne Bezeichnungen
                    KRITERIEN_BESCHREIBUNGEN = {
                        "K002": "Zukunftsfähige Mobilität",
                        "K003": "Anteil Freiflächen",
                        "K004": "Einbettung in die Umgebung",
                        "K005": "Lärmschutz",
                        "K006": "Erhalt Bestandgebäude",
                        "K007": "Energetische Standards (PV-Anlagen auf dem Dach)",
                        "K008": "Vielfältige Nutzungen der Freiflächen",
                        "K009": "Zugang Wasser",
                        "K010": "Entsiegelung",
                        "K011": "Rettungswege, Mindestwegbreite",
                        "K012": "Anteil Dachbegrünung",
                        "K013": "Erhalt Baumbestand",
                        "K015": "Freiflächen Zonierung"
                    }

                    st.subheader("Eingabewerte (an das Modell übergeben)")
                    df_long = df_features.iloc[[0]].T.reset_index()
                    df_long.columns = ["Kriterium", "Wert"]
                    df_long["Kriterium"] = df_long["Kriterium"].map(KRITERIEN_BESCHREIBUNGEN).fillna(df_long["Kriterium"])
                    st.dataframe(df_long)

                    # Für Excel-Download → Spalten umbenennen
                    df_export = df_features.copy()
                    df_export.columns = [KRITERIEN_BESCHREIBUNGEN.get(c, c) for c in df_export.columns]
                    df_export["Anzahl Sterne"] = sterne

                    output_path = os.path.join(tmpdir, f"Bewertung_{zip_file.name}.xlsx")
                    df_export.to_excel(output_path, index=False)

                    with open(output_path, "rb") as f:
                        st.download_button(
                            "Ergebnis als Excel herunterladen",
                            data=f,
                            file_name=f"Bewertung_{zip_file.name}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                else:
                    st.error("Bewertungsmatrix wurde nicht erstellt.")
