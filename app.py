import streamlit as st
import zipfile
import tempfile
import os
import shutil
import subprocess
import pandas as pd
import joblib

# Einstellungen & Metadaten

st.set_page_config(
    page_title="Die Digitale Jury",
    layout="centered"
)
st.title("Die Digitale Jury – objektive Bewertung städtebaulicher Entwürfe")
st.markdown("""
## 
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

### **Benötigte Dateien**

Bitte stelle sicher, dass deine ZIP-Datei folgende Layer enthält (soweit vorhanden):

- `Gebaeude.shp`
- `Gebaeude_Umgebung.shp`
- `Verkehrsflaechen.shp`
- `Verkehrsmittellinie.shp`
- `Dachgruen.shp`
- `PV_Anlage.shp`
- `oeffentliche_Gruenflaechen.shp`
- `private_Gruenflaechen.shp`
- `Wasser.shp`
- `Baeume_Entwurf.shp`
- `Bestandsbaeume.shp`
- `Bestandsgruen.shp`
- `Gebietsabgrenzung.shp`

---

### **Hinweise**

- Fehlende Layer führen zu einer automatischen `0`-Bewertung für das jeweilige Kriterium.
- Verwende **korrekte, vollständige Geometrien** – leere oder fehlerhafte Layer führen zu unvollständigen Ergebnissen.
- Halte dich strikt an die **Dateinamen**.
- Alle Dateien müssen im richtigen **Koordinatensystem** liegen.

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


# Random-Forest-Modell laden

MODEL_PATH = "final_RF_model.pkl"

try:
    rf_model = joblib.load(MODEL_PATH)
    st.success("✅ Bewertungsmodell erfolgreich geladen.")
except Exception as e:
    st.error(f"❌ Bewertungsmodell konnte nicht geladen werden: {e}")
    st.stop()


# ZIP Upload

uploaded_zips = st.file_uploader(
    "Entwürfe als ZIP hochladen",
    type="zip",
    accept_multiple_files=True
)

if uploaded_zips:
    for zip_file in uploaded_zips:
        st.markdown(f"---\n### Bewertung für: `{zip_file.name}`")
        st.success("ZIP erfolgreich hochgeladen.")

        with st.spinner("Entpacke & verarbeite Entwurf..."):
            with tempfile.TemporaryDirectory() as tmpdir:
                # Entpacken
                with zipfile.ZipFile(zip_file, "r") as zip_ref:
                    zip_ref.extractall(tmpdir)

                # SHP-Layer laden
                def lade_layer(name):
                    path = os.path.join(tmpdir, name)
                    return gpd.read_file(path) if os.path.exists(path) else None

                shapefiles = {
                    "Gebaeude": lade_layer("Gebaeude.shp"),
                    "Gebaeude_Umgebung": lade_layer("Gebaeude_Umgebung.shp"),
                    "Verkehrsflaechen": lade_layer("Verkehrsflaechen.shp"),
                    "Verkehrsmittellinie": lade_layer("Verkehrsmittellinie.shp"),
                    "Dachgruen": lade_layer("Dachgruen.shp"),
                    "PV_Anlage": lade_layer("PV_Anlage.shp"),
                    "oeffentliche_Gruenflaechen": lade_layer("oeffentliche_Gruenflaechen.shp"),
                    "private_Gruenflaechen": lade_layer("private_Gruenflaechen.shp"),
                    "Wasser": lade_layer("Wasser.shp"),
                    "Baeume_Entwurf": lade_layer("Baeume_Entwurf.shp"),
                    "Bestandsbaeume": lade_layer("Bestandsbaeume.shp"),
                    "Bestandsgruen": lade_layer("Bestandsgruen.shp"),
                    "Gebietsabgrenzung": lade_layer("Gebietsabgrenzung.shp")
                }

                fehlende = [name for name, layer in shapefiles.items() if layer is None]
                if fehlende:
                    st.warning(f"Fehlende Dateien: {', '.join(fehlende)}")

                if any(layer is not None for layer in shapefiles.values()):
                    # Kopiere Scripts
                    shutil.copy("shpVerknuepfung.py", tmpdir)
                    shutil.copy("Bewertungsmatrix.xlsx", tmpdir)

                    # Skript ausführen
                    try:
                        subprocess.run(["python", "shpVerknuepfung.py", tmpdir], cwd=tmpdir, capture_output=True)
                    except Exception as e:
                        st.error(f"Fehler beim Skript: {e}")
                        continue

                    # Ergebnisse einlesen
                    kriterien_path = os.path.join(tmpdir, "Kriterien_Ergebnisse.xlsx")
                    if os.path.exists(kriterien_path):
                        df = pd.read_excel(kriterien_path)
                        df = df.fillna(0)

                        # Nur relevante Spalten
                        kriterien = [col for col in df.columns if col.startswith("K")]
                        vorhersage = rf_model.predict(df[kriterien])[0]

                        sterne = int(vorhersage)
                        st.success(f"⭐️ Bewertung: {sterne} Sterne")

                        df_anzeige = df[kriterien].transpose().reset_index()
                        df_anzeige.columns = ["Kriterium", "Wert"]
                        df_anzeige["Beschreibung"] = df_anzeige["Kriterium"].map(KRITERIEN_BESCHREIBUNGEN)
                        st.dataframe(df_anzeige)

                        # Ergebnis-Download
                        df["Anzahl Sterne"] = sterne
                        output_path = os.path.join(tmpdir, f"Bewertung_{zip_file.name}.xlsx")
                        df.to_excel(output_path, index=False)
                        with open(output_path, "rb") as f:
                            st.download_button(
                                label="Ergebnis herunterladen",
                                data=f,
                                file_name=f"Bewertung_{zip_file.name}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    else:
                        st.error("Keine Bewertungsdatei erstellt.")
                else:
                    st.warning("Keine gültigen SHP-Layer im ZIP enthalten.")
