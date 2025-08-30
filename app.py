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
import numpy as np

# --------------------------------------
# Einstellungen & Metadaten
# --------------------------------------
st.set_page_config(page_title="Die Digitale Jury", layout="centered")
st.title("Die Digitale Jury – objektive Bewertung städtebaulicher Entwürfe")
st.markdown("""
Willkommen bei der **digitalen Jury**!  
Dieses Tool bewertet städtebauliche Entwürfe **automatisch** anhand von **13 Kriterien** mit einem trainierten **Random-Forest-Modell**.

**Benötigte Layer (sofern vorhanden):**  
`Gebaeude.shp (Geb_Hoehe)`, `Gebaeude_Umgebung.shp`, `Dachgruen.shp`, `PV_Anlage.shp`,  
`Verkehrsflaechen.shp (Nutzung: Fuss_Rad / Kfz_Flaeche / Begegnungszone)`, `Verkehrsmittellinie.shp`,  
`oeffentliche_Gruenflaechen.shp (Nutzung)`, `private_Gruenflaechen.shp`, `oeffentliche_Plaetze.shp`,  
`Wasser.shp`, `Baeume_Entwurf.shp`, `Bestandsbaeume.shp`, `Bestandsgruen.shp`, `Gebietsabgrenzung.shp`.
""")

uploaded_files = st.file_uploader("Entwürfe als ZIP hochladen", type="zip", accept_multiple_files=True)

# --------------------------------------
# Modell laden (Feature-Order sichern)
# --------------------------------------
MODEL_PATH = "final_RF_model.pkl"
try:
    bundle = joblib.load(MODEL_PATH)
    if isinstance(bundle, dict) and "model" in bundle and "features" in bundle:
        rf_model = bundle["model"]
        FEATURE_ORDER = list(bundle["features"])
    else:
        rf_model = bundle
        # Fallback: exakt die Reihenfolge, mit der du trainiert hast
        FEATURE_ORDER = ["K002","K003","K004","K005","K006","K007","K008","K009","K010","K011","K012","K013","K015"]
except Exception as e:
    st.error(f"Bewertungsmodell konnte nicht geladen werden: {e}")
    st.stop()

# Wenn Modell eigene Featureliste kennt, nutze sie
FEATURE_ORDER = list(getattr(rf_model, "feature_names_in_", FEATURE_ORDER))

# --------------------------------------
# Verarbeitung
# --------------------------------------
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
                    "Gebaeude.shp","Gebaeude_Umgebung.shp","Verkehrsflaechen.shp","Verkehrsmittellinie.shp",
                    "Dachgruen.shp","PV_Anlage.shp","oeffentliche_Gruenflaechen.shp","private_Gruenflaechen.shp",
                    "oeffentliche_Plaetze.shp","Wasser.shp","Baeume_Entwurf.shp","Bestandsbaeume.shp",
                    "Bestandsgruen.shp","Gebietsabgrenzung.shp"
                ]
                fehlen = [ly for ly in erwartete_layer if not glob.glob(os.path.join(tmpdir, ly))]
                if fehlen:
                    st.warning("Fehlende Layer: " + ", ".join(fehlen))

                # --- Attribut-Checks (minimal)
                erwartete_attributs = {
                    "Verkehrsflaechen": ["Nutzung"],
                    "Gebaeude": ["Geb_Hoehe"],
                    "oeffentliche_Gruenflaechen": ["Nutzung"]
                }
                for layer_name, attrs in erwartete_attributs.items():
                    shp_path = os.path.join(tmpdir, f"{layer_name}.shp")
                    if os.path.exists(shp_path):
                        try:
                            layer = gpd.read_file(shp_path)
                            for attr in attrs:
                                if attr not in layer.columns:
                                    st.warning(f"`{attr}` fehlt in `{layer_name}.shp`")
                        except Exception as e:
                            st.warning(f"`{layer_name}.shp` konnte nicht gelesen werden: {e}")
                    else:
                        st.warning(f"`{layer_name}.shp` fehlt!")

                # --- Berechnungsskript starten
                try:
                    shutil.copy("shpVerknuepfung.py", tmpdir)
                except Exception as e:
                    st.error(f"`shpVerknuepfung.py` konnte nicht in das Temp-Verzeichnis kopiert werden: {e}")
                    st.stop()

                result = subprocess.run(
                    [sys.executable, "shpVerknuepfung.py", tmpdir],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True
                )
                # Log anzeigen (hilft enorm beim Debuggen)
                if result.returncode != 0:
                    st.error("Fehler beim Ausführen von shpVerknuepfung.py")
                    if result.stderr:
                        with st.expander("Fehlerdetails (stderr)"):
                            st.code(result.stderr)
                    if result.stdout:
                        with st.expander("Ausgabe (stdout)"):
                            st.code(result.stdout)
                    st.stop()
                else:
                    if result.stderr:
                        with st.expander("Log aus shpVerknuepfung.py"):
                            st.code(result.stderr)

                # --- Ergebnisse einlesen
                kriterien_path = os.path.join(tmpdir, "Kriterien_Ergebnisse.xlsx")
                if not os.path.exists(kriterien_path):
                    st.error("Bewertungsmatrix wurde nicht erstellt (Kriterien_Ergebnisse.xlsx fehlt).")
                    if result.stdout:
                        with st.expander("Ausgabe (stdout)"):
                            st.code(result.stdout)
                    st.stop()

                try:
                    df_raw = pd.read_excel(kriterien_path)
                except Exception as e:
                    st.error(f"Kriterien_Ergebnisse.xlsx konnte nicht gelesen werden: {e}")
                    st.stop()

                # --- Sichere Feature-Matrix exakt wie im Training
                # -> Spalten fehlend? mit 0 ergänzen. Extra-Spalten? ignorieren.
                X = pd.DataFrame({f: pd.to_numeric(df_raw.get(f), errors="coerce") for f in FEATURE_ORDER})
                X = X.fillna(0.0).astype(float)

                # Sanity: Anteil Nullen & Anzeige der echten Inputwerte
                zero_share = float((X.iloc[0] == 0).mean()) if not X.empty else 1.0
                st.caption(f"Null-Anteil im Featurevektor: {zero_share:.0%}")
                if zero_share >= 0.8:
                    st.warning("Sehr viele 0-Werte → wenig Signal. Prüfe fehlende Layer/CRS/`Gebietsabgrenzung`/NaNs in K-Werten.")

                # --- Vorhersage
                try:
                    y_hat = rf_model.predict(X)[0]
                    sterne = int(y_hat)
                except Exception as e:
                    st.error(f"Vorhersage fehlgeschlagen: {e}")
                    st.stop()

                st.success(f"⭐️ Bewertung: **{sterne} Sterne**")

                # Wahrscheinlichkeiten (falls Classifier)
                if hasattr(rf_model, "predict_proba"):
                    try:
                        proba = rf_model.predict_proba(X)[0]
                        classes = list(getattr(rf_model, "classes_", range(len(proba))))
                        prob_df = pd.DataFrame({"Sterne": classes, "p": proba}).sort_values("Sterne")
                        with st.expander("Vorhersage-Wahrscheinlichkeiten"):
                            st.dataframe(prob_df, hide_index=True)
                    except Exception:
                        pass

                # --- Werte anzeigen
                NAMEN = {
                    "K002":"Zukunftsfähige Mobilität", "K003":"Anteil Freiflächen",
                    "K004":"Einbettung Umgebung", "K005":"Lärmschutz",
                    "K006":"Erhalt Bestandgebäude", "K007":"PV-Anteil",
                    "K008":"Nutzungsvielfalt Freiflächen", "K009":"Zugang Wasser",
                    "K010":"Entsiegelung", "K011":"Rettungswege",
                    "K012":"Dachbegrünung", "K013":"Erhalt Baumbestand",
                    "K015":"Zonierung Freiflächen"
                }
                df_show = X.iloc[[0]].T.reset_index()
                df_show.columns = ["Kriterium", "Wert"]
                df_show["Kriterium"] = df_show["Kriterium"].map(NAMEN).fillna(df_show["Kriterium"])
                st.subheader("Eingabewerte (Modell-Features)")
                st.dataframe(df_show, hide_index=True)

                # --- Download
                out = X.copy()
                out.columns = [NAMEN.get(c, c) for c in out.columns]
                out["Anzahl Sterne"] = sterne
                output_path = os.path.join(tmpdir, f"Bewertung_{zip_file.name}.xlsx")
                out.to_excel(output_path, index=False)
                with open(output_path, "rb") as f:
                    st.download_button(
                        "Ergebnis als Excel herunterladen",
                        data=f,
                        file_name=f"Bewertung_{zip_file.name}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
