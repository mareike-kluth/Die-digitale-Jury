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
#######
Willkommen bei der **digitalen Jury**!  
Dieses Tool bewertet städtebauliche Entwürfe **automatisch** anhand von **13 Kriterien** mit einem trainierten **Random-Forest-Modell**.

---

### **So funktioniert es**

**Entwurf vorbereiten:**  
Speichere deine Geodaten im **Shapefile-Format** (`.shp`) mit den **exakten Dateinamen** (siehe unten).  
Jedes `.shp` benötigt seine zugehörigen Begleitdateien (`.shx`, `.dbf`, `.prj`).  
Diese müssen **alle zusammen** in **einer ZIP-Datei** gepackt werden.

Die Kriterien werden automatisch berechnet, fehlende Werte werden mit `0` ersetzt.  
Die **Digitale Jury** vergibt jedem Entwurf eine objektive Bewertung von **1 bis 5 Sternen**.

---

### **Benötigte Dateien und Datenstruktur**

Bitte stelle sicher, dass deine ZIP-Datei folgende Layer enthält (sofern vorhanden):

**Wichtig:** 
In jeder Shapefile müssen die unten genannten **Spalten (Felder)** in der Attributtabelle korrekt vorhanden sein.  
Jedes Objekt, wie z. B. ein Gebäude oder eine Fläche, ist dabei eine **Zeile** in der Tabelle.  
Die **Layer-Namen**, **Spalten-Namen** und **Attributwerte** müssen **exakt** so geschrieben sein wie unten angegeben.
Alle Dateien müssen im passenden **Koordinatensystem** vorliegen.

Verwende **korrekte, vollständige Geometrien** – leere oder fehlerhafte Layer führen zu unvollständigen Ergebnissen.
Wenn eine Spalte fehlt oder falsch benannt ist, kann das entsprechende Kriterium **nicht berechnet werden** und wird automatisch mit `0` bewertet.


| Layer | Benötigte Spalten |
|-----------------------------|------------------------------|
| `Gebaeude.shp` | `Geb_Hoehe` |
| `Gebaeude_Umgebung.shp` | – |
| `Dachgruen.shp` | – | 
| `PV_Anlage.shp` | – | 
| `Verkehrsflaechen.shp` | `Nutzung` mit `Fuss_Rad`, `Auto_Fuss_Rad` und `Stellplatz`
| `Verkehrsmittellinie.shp` | – |
| `oeffentliche_Gruenflaechen.shp` | `Nutzung` | 
| `private_Gruenflaechen.shp` | – |
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
    rf_model = joblib.load(MODEL_PATH)
except Exception as e:
    st.error(f"Bewertungsmodell konnte nicht geladen werden: {e}")
    st.stop()

if uploaded_files:
    for zip_file in uploaded_files:
        st.write(f"Hochgeladen: `{zip_file.name}`")
        with st.spinner("Verarbeite Entwurf ..."):
            with tempfile.TemporaryDirectory() as tmpdir:
                # --- Entpacken
                with zipfile.ZipFile(zip_file, "r") as zip_ref:
                    zip_ref.extractall(tmpdir)

                # --- Erwartete Layer prüfen
                erwartete_layer = [
                    "Gebaeude.shp", "Gebaeude_Umgebung.shp", "Verkehrsflaechen.shp", "Verkehrsmittellinie.shp",
                    "Dachgruen.shp", "PV_Anlage.shp", "oeffentliche_Gruenflaechen.shp", "private_Gruenflaechen.shp",
                    "Wasser.shp", "Baeume_Entwurf.shp", "Bestandsbaeume.shp", "Bestandsgruen.shp", "Gebietsabgrenzung.shp"
                ]

                fehlen = []
                for layer in erwartete_layer:
                    if not glob.glob(os.path.join(tmpdir, layer)):
                        fehlen.append(layer)

                if fehlen:
                    st.warning(f"Achtung: Folgende Layer fehlen: {', '.join(fehlen)}")

               
                import geopandas as gpd

                # --- Layer- & Attribut-Check ---                               
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
                
                # --- Skript ausführen
                shutil.copy("shpVerknuepfung.py", tmpdir)

                # --- Skript ausführen
                shutil.copy("shpVerknuepfung.py", tmpdir)
                
                result = subprocess.run(
                    [sys.executable, "shpVerknuepfung.py", tmpdir],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True
                )


                # --- Ergebnisse einlesen & Modell anwenden
                kriterien_path = os.path.join(tmpdir, "Kriterien_Ergebnisse.xlsx")
                if os.path.exists(kriterien_path):
                    df = pd.read_excel(kriterien_path).fillna(0)

                    # Mapping: Kürzel zu Beschreibung
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

                    kriterien_spalten = [col for col in df.columns if col.startswith("K")]
                    prediction = rf_model.predict(df[kriterien_spalten])[0]
                    sterne = int(prediction)
                    st.success(f"⭐️ Bewertung: **{sterne} Sterne**")
                
                    # Für Anzeige in der App
                    df_long = df[kriterien_spalten].transpose().reset_index()
                    df_long.columns = ["Kriterium", "Bewertung"]
                    df_long["Kriterium"] = df_long["Kriterium"].map(KRITERIEN_BESCHREIBUNGEN)
                    st.dataframe(df_long)
                
                    # Für Excel-Download → Spalten umbenennen
                    df_umbenannt = df.rename(columns=KRITERIEN_BESCHREIBUNGEN)
                    df_umbenannt["Anzahl Sterne"] = sterne
                
                    output_path = os.path.join(tmpdir, f"Bewertung_{zip_file.name}.xlsx")
                    df_umbenannt.to_excel(output_path, index=False)
                
                    with open(output_path, "rb") as f:
                        st.download_button(
                            "Ergebnis als Excel herunterladen",
                            data=f,
                            file_name=f"Bewertung_{zip_file.name}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                else:
                    st.error("Bewertungsmatrix wurde nicht erstellt.")
