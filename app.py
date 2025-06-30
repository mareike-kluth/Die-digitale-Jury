import streamlit as st
import zipfile
import tempfile
import os
import subprocess
import pandas as pd
import joblib

# -------------------------------------------
# Einstellungen & Metadaten
# -------------------------------------------
st.set_page_config(
    page_title="Die Digitale Jury",
    layout="centered"
)

st.title("📐 Die Digitale Jury – objektive Bewertung städtebaulicher Entwürfe")

st.markdown("""
Dieses Tool bewertet deinen Entwurf anhand von 13 objektiven Kriterien aus den Shapefiles.  
Die Kriterien werden automatisch berechnet und anschließend mit einem trainierten Random-Forest-Modell in eine Sterne-Bewertung übersetzt.

**Ablauf:**
1️⃣ ZIP hochladen  
2️⃣ Kriterien automatisch berechnen lassen  
3️⃣ Bewertung (1–5 Sterne) direkt erhalten  
""")

# -------------------------------------------
# Random-Forest-Modell laden
# -------------------------------------------
MODEL_PATH = "best_rf_model.pkl"

try:
    rf_model = joblib.load(MODEL_PATH)
    st.success("✅ Bewertungsmodell erfolgreich geladen.")
except Exception as e:
    st.error(f"❌ Modell konnte nicht geladen werden: {e}")
    st.stop()

# -------------------------------------------
# ZIP Upload
# -------------------------------------------
uploaded_file = st.file_uploader("Entwurfsdaten als ZIP hochladen", type="zip")

if uploaded_file:
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "upload.zip")
        with open(zip_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(tmpdir)

        st.info("Daten entpackt. Berechne Kriterien...")

        # SHP-Verknüpfungsskript ausführen
        subprocess.run(["python", "shpVerknuepfung.py", tmpdir], check=True)

        # Kriterien-Ergebnisse einlesen
        kriterien_path = os.path.join(tmpdir, "Kriterien_Ergebnisse.xlsx")
        if not os.path.exists(kriterien_path):
            st.error("❌ Kriterien-Datei wurde nicht erstellt. Prüfe die SHP-Daten.")
            st.stop()

        df = pd.read_excel(kriterien_path)

        # Entferne K001 & K014, falls vorhanden
        for col in ["K001", "K014"]:
            if col in df.columns:
                df.drop(columns=col, inplace=True)

        # Fehlende Werte auffüllen
        df = df.fillna(0)

        # Passende Spalten extrahieren
        kriterien_spalten = [col for col in df.columns if col.startswith("K")]

        # Vorhersage
        prediction = rf_model.predict(df[kriterien_spalten])[0]

        # Ergebnis anzeigen
        st.success(f"⭐️ **Ergebnis: {int(prediction)} Sterne**")

        st.markdown("### Details der berechneten Kriterien")
        st.dataframe(df)

        # Ergebnis speichern & Download
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
