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
import base64
from pathlib import Path
import streamlit.components.v1 as components


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

# Kriterien-Handbuch (PDF) anzeigen/Download 

st.subheader("Kriterien-Handbuch (PDF)")

DEFAULT_PDF_PATH = Path("assets/Kriterien_Handbuch.pdf")

col1, col2 = st.columns([2, 1])
with col1:
    uploaded_pdf = st.file_uploader(
        "Optional: eigenes PDF mit Kriterien-Erklärungen hochladen",
        type=["pdf"],
        accept_multiple_files=False,
        key="pdf_kriterien_upload"
    )

pdf_bytes = None
pdf_name = None

if uploaded_pdf is not None:
    pdf_bytes = uploaded_pdf.read()
    pdf_name = uploaded_pdf.name
elif DEFAULT_PDF_PATH.exists():
    pdf_bytes = DEFAULT_PDF_PATH.read_bytes()
    pdf_name = DEFAULT_PDF_PATH.name

if pdf_bytes:
    # Download-Button
    with col2:
        st.download_button(
            label="PDF herunterladen",
            data=pdf_bytes,
            file_name=pdf_name or "Kriterien_Handbuch.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    # Inline-Viewer
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    pdf_html = f'''
        <iframe
            src="data:application/pdf;base64,{b64}#toolbar=1&navpanes=0&view=fitH"
            width="100%"
            height="800"
            style="border:none;"
        ></iframe>
    '''
    with st.expander("Kriterien-Handbuch öffnen", expanded=True):
        components.html(pdf_html, height=820, scrolling=False)
else:
    st.info("Kein Kriterien-Handbuch gefunden. Lade eine PDF hoch oder lege sie unter `assets/Kriterien_Handbuch.pdf` ab.")


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
                # --- Erwartete Layer prüfen (einmalige Sammelmeldung) ---
                erwartete_layer = [
                    "Gebaeude.shp","Gebaeude_Umgebung.shp","Verkehrsflaechen.shp","Verkehrsmittellinie.shp",
                    "Dachgruen.shp","PV_Anlage.shp","oeffentliche_Gruenflaechen.shp","private_Gruenflaechen.shp",
                    "oeffentliche_Plaetze.shp","Wasser.shp","Baeume_Entwurf.shp","Bestandsbaeume.shp",
                    "Bestandsgruen.shp","Gebietsabgrenzung.shp"
                ]
                
                missing_layers = [ly for ly in erwartete_layer if not os.path.exists(os.path.join(tmpdir, ly))]
                if missing_layers:
                    st.warning("Fehlende Layer: " + ", ".join(missing_layers))
                
                # --- Attribut-Checks (nur für vorhandene Layer; keine zweite 'fehlt!'-Meldung) ---
                erwartete_attributs = {
                    "Verkehrsflaechen": ["Nutzung"],
                    "Gebaeude": ["Geb_Hoehe"],
                    "oeffentliche_Gruenflaechen": ["Nutzung"],
                }
                
                for layer_name, attrs in erwartete_attributs.items():
                    shp_path = os.path.join(tmpdir, f"{layer_name}.shp")
                
                    # Wenn der Layer fehlt, hier NICHT nochmal warnen (bereits oben gesammelt)
                    if not os.path.exists(shp_path):
                        continue
                
                    try:
                        layer = gpd.read_file(shp_path)
                    except Exception as e:
                        st.warning(f"`{layer_name}.shp` konnte nicht gelesen werden: {e}")
                        continue
                
                    missing_attrs_in_layer = [a for a in attrs if a not in layer.columns]
                    if missing_attrs_in_layer:
                        st.warning(
                            f"In `{layer_name}.shp` fehlen folgende Attribute: {', '.join(missing_attrs_in_layer)}"
                        )

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

