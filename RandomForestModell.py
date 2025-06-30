import pandas as pd
import joblib


# Bewertungsmatrix laden
df = pd.read_excel("Bewertungsmatrix.xlsx")

# Kriterien definieren
kriterien = [col for col in df.columns if col != "Anzahl Sterne"]

# Zero-Fill
df[kriterien] = df[kriterien].fillna(0)

# Modell laden
model = joblib.load("final_RF_model.pkl")

# Nur neue Entwürfe finden
X_new = df[df["Anzahl Sterne"].isna()][kriterien]

# Vorhersage
preds = model.predict(X_new)

# Sterne direkt in die Zeile schreiben
df.loc[X_new.index, "Anzahl Sterne"] = preds

# Final speichern
df.to_excel("Bewertungsmatrix_FINAL.xlsx", index=False)

print("Bewertungsmatrix_FINAL.xlsx mit neuen Sternen gespeichert.")
