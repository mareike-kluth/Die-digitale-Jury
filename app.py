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
Dieses Tool bewertet Entwürfe anhand von 13 Kriterien mit einem trainierten Random-Forest-Modell.
Lade deine Entwurfsdaten (ZIP) hoch. Die Kriterien werden berechnet, fehlende Werte mit 0 ersetzt,
und die Sternebewertung wird automatisch ermittelt.
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

uploaded_file = st.file_uploader("ZIP-Datei mit SHP-Daten hochladen", type="zip")

if uploaded_file:
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "upload.zip")
        with open(zip_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(tmpdir)

        st.info("Dateien entpackt. Berechne Kriterien...")

        subprocess.run(["python", "shpVerknuepfung.py", tmpdir], check=True)

        kriterien_path = os.path.join(tmpdir, "Kriterien_Ergebnisse.xlsx")
        if not os.path.exists(kriterien_path):
            st.error("❌ Kriterien-Datei wurde nicht erstellt.")
            st.stop()

        df = pd.read_excel(kriterien_path)

        for k in ["K001", "K014"]:
            if k in df.columns:
                df.drop(columns=[k], inplace=True)

        df = df.fillna(0)

        kriterien_spalten = [col for col in df.columns if col.startswith("K")]
        prediction = rf_model.predict(df[kriterien_spalten])[0]

        st.success(f"⭐️ Ergebnis: **{int(prediction)} Sterne**")

        st.dataframe(df)

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
