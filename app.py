# app.py
import streamlit as st
import zipfile
import tempfile
import os
import subprocess
import geopandas as gpd
import pandas as pd
import joblib

# -------------------------------------------
# Einstellungen & Metadaten
# -------------------------------------------
st.set_page_config(
    page_title="Die Digitale Jury",
    layout="centered"
)

st.title("Die Digitale Jury - objektive Bewertung städtebaulicher Entwürfe")
st.markdown("""
Hier werden anhand von 13 Bewertungskriterien städtebauliche Entwürfe im Rahmen der Diplomarbeit **„Die Digitale Jury“** bewertet.  
Basierend auf eingelesenen Shapefiles werden städtebauliche Kriterien wie Mobilität, Freiraumanteile, ökologische Aspekte (PV, Dachbegrünung, Entsiegelung) sowie die Einbettung in den städtebaulichen Kontext automatisiert bewertet.

Die Bewertung wird auf Grundlage der vorhandenen Daten durchgeführt. Fehlende Layer führen zu `0` in der Ergebnisübersicht.

1️⃣ Lade deine Entwurfsdaten (als ZIP) hoch.  
2️⃣ Die Geodaten werden automatisch verarbeitet.  
3️⃣ Du erhältst die objektive Bewertung (1-5 Sterne) basierend auf einem trainierten Random Forest Modell.
""")

# -------------------------------------------
# trainiertes Random-Forest-Modell laden
# -------------------------------------------
MODEL_PATH = "best_rf_model.pkl"

try:
    rf_model = joblib.load(MODEL_PATH)
    st.success("✅ Bewertungsmodell erfolgreich geladen.")
except:
    st.error("❌ Bewertungsmodell (.pkl) konnte nicht geladen werden.")
    st.stop()

# -------------------------------------------
# ZIP Upload
# -------------------------------------------
uploaded_file = st.file_uploader("Entwurf als ZIP hochladen", type="zip")

if uploaded_file:
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "upload.zip")
        with open(zip_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(tmpdir)

        st.info("Dateien entpackt. Berechne Kriterien...")

        # SHP-Verknüpfungs-Skript
        subprocess.run(["python", "shpVerknuepfung.py", tmpdir], check=True)

        # Lies die Ergebnisse
        kriterien_path = os.path.join(tmpdir, "Kriterien_Ergebnisse.xlsx")
        if not os.path.exists(kriterien_path):
            st.error("Die Kriterien-Datei wurde nicht erstellt.")
            st.stop()

        df = pd.read_excel(kriterien_path)

        # Entferne K001 & K014, falls vorhanden
        for k in ["K001", "K014"]:
            if k in df.columns:
                df.drop(columns=[k], inplace=True)

        # Fehlende Werte Zero-Fill
        df = df.fillna(0)

        # Vorhersage durchführen
        kriterien_spalten = [col for col in df.columns if col.startswith("K")]
        prediction = rf_model.predict(df[kriterien_spalten])[0]

        # Ergebnis anzeigen
        st.success(f"⭐️ Ergebnis: **{int(prediction)} Sterne**")

        st.markdown("### 📊 Bewertete Kriterien")
        st.dataframe(df)

        # Download anbieten
        df["Anzahl Sterne"] = int(prediction)
        output_path = os.path.join(tmpdir, "Bewertung_Digitale_Jury.xlsx")
        df.to_excel(output_path, index=False)
        with open(output_path, "rb") as f:
            st.download_button(
                label="Ergebnis als Excel herunterladen",
                data=f,
                file_name="Bewertung_Digitale_Jury.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
