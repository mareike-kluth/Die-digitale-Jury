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

uploaded_files = st.file_uploader(
    "Entwürfe als ZIP hochladen",
    type="zip",
    accept_multiple_files=True
)

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
                    st.warning(f"Achtung: Folgende Layer fehlen und werden als 0 bewertet: {', '.join(fehlen)}")

                # --- Skript ausführen
                shutil.copy("shpVerknuepfung.py", tmpdir)

                result = subprocess.run(
                    ["python", "shpVerknuepfung.py", tmpdir],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True
                )

                if result.returncode != 0:
                    st.error("Fehler beim Ausführen von `shpVerknuepfung.py`!")
                    st.code(result.stderr)
                    st.stop()
                else:
                    st.success("shpVerknuepfung.py erfolgreich ausgeführt!")

                # --- Ergebnisse einlesen & Modell anwenden
                kriterien_path = os.path.join(tmpdir, "Kriterien_Ergebnisse.xlsx")
                if os.path.exists(kriterien_path):
                    df = pd.read_excel(kriterien_path).fillna(0)
                    kriterien_spalten = [col for col in df.columns if col.startswith("K")]
                    prediction = rf_model.predict(df[kriterien_spalten])[0]
                    sterne = int(prediction)
                    st.success(f"⭐️ Bewertung: **{sterne} Sterne**")

                    st.dataframe(df)

                    df["Anzahl Sterne"] = sterne
                    output_path = os.path.join(tmpdir, f"Bewertung_{zip_file.name}.xlsx")
                    df.to_excel(output_path, index=False)

                    with open(output_path, "rb") as f:
                        st.download_button(
                            "Ergebnis als Excel herunterladen",
                            data=f,
                            file_name=f"Bewertung_{zip_file.name}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                else:
                    st.error("Bewertungsmatrix wurde nicht erstellt.")
                    st.error("Es wurde keine Bewertungsdatei erstellt.")

