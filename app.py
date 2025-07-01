import streamlit as st
import zipfile
import tempfile
import os
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

uploaded_files = st.file_uploader(
    "Entwürfe als ZIP hochladen",
    type="zip",
    accept_multiple_files=True
)

if uploaded_files:
    for uploaded_file in uploaded_files:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "upload.zip")
            with open(zip_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            st.info(f"Dateien aus **{uploaded_file.name}** entpackt. Berechne Kriterien...")

            subprocess.run(["python", "shpVerknuepfung.py", tmpdir], check=True)

            kriterien_path = os.path.join(tmpdir, "Kriterien_Ergebnisse.xlsx")
            if not os.path.exists(kriterien_path):
                st.error("Kriterien-Datei wurde nicht erstellt.")
                st.stop()

            df = pd.read_excel(kriterien_path)

            for k in ["K001", "K014"]:
                if k in df.columns:
                    df.drop(columns=[k], inplace=True)

            df = df.fillna(0)

            kriterien_spalten = [col for col in df.columns if col.startswith("K")]
            prediction = rf_model.predict(df[kriterien_spalten])[0]

            st.success(f"⭐️ Ergebnis für **{uploaded_file.name}**: **{int(prediction)} Sterne**")

            st.dataframe(df)

            df["Anzahl Sterne"] = int(prediction)
            output_path = os.path.join(tmpdir, f"Bewertung_{uploaded_file.name}.xlsx")
            df.to_excel(output_path, index=False)
            with open(output_path, "rb") as f:
                st.download_button(
                    label=f"Ergebnis für **{uploaded_file.name}** herunterladen",
                    data=f,
                    file_name=f"Bewertung_{uploaded_file.name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

