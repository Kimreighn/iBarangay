# iBarangay AI Model

This folder contains the AI-based analysis component for the objective:

> Integrate an AI-based analysis component to identify patterns in incident records and potential health risks within the community.

## Runtime model

`community_risk_model.py` is used by the Flask app. It analyzes:

- Incident patterns by report type and purok.
- Repeated incident concentrations.
- Resident health-risk indicators using age, income, household size, family health score, and incident history.

The runtime model is dependency-light so the app can run with the current Flask requirements.
The live system exposes the analysis through `/api/emergency/analysis` and the resident, official, and BIO map dashboards.

If a trained artifact exists, the runtime health-risk scorer will load it from:

- `ai_model/health_risk_model.joblib`
- `ai_model/health_risk_model.json`

If those files are missing, the app falls back to the built-in heuristic scorer.

## Trained artifact builder

`train_health_risk_model.py` now creates a real `RandomForestClassifier` artifact for the live app. The trainer follows the structure of `thesis-ai-train.ipynb`:

- thesis notebook seed rows for residents
- classifier inputs: `age`, `income`, `family_size`, and `incident_count`
- optional barangay rows from `ibarangay.db`
- small augmented variants to give the model more training coverage
- KMeans incident clustering stored alongside the classifier metadata

```powershell
pip install pandas scikit-learn
python ai_model/train_health_risk_model.py
```

If `~/Downloads/thesis-ai-train.ipynb` exists, the trainer imports its dataset directly. If not, it uses the embedded copy of the same notebook seed data.

After training, the live runtime can use the generated model file automatically.
