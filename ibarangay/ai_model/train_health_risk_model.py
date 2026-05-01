"""
Train the live iBarangay health-risk model from the thesis notebook dataset.

This trainer builds:
- a scikit-learn model artifact (`health_risk_model.joblib`)
- a metadata file that documents the training run

When the thesis notebook is available, its dataset is imported directly.
Otherwise, the trainer falls back to an embedded copy of the same seed data.
"""

from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR.parent / 'ibarangay.db'
DEFAULT_MODEL_PATH = BASE_DIR / 'health_risk_model.joblib'
DEFAULT_METADATA_PATH = BASE_DIR / 'health_risk_model.json'
DEFAULT_NOTEBOOK_PATH = Path.home() / 'Downloads' / 'thesis-ai-train.ipynb'

FEATURES = ['age', 'income', 'family_size', 'incident_count']
TARGET = 'health_risk'
RATING_COLUMNS = ['rating_service', 'rating_transparency', 'rating_response']

THESIS_NOTEBOOK_DATA = {
    'resident_id': list(range(1, 31)),
    'age': [25, 60, 45, 30, 70, 50, 33, 65, 22, 58, 40, 75, 29, 36, 68, 55, 19, 47, 62, 34, 80, 27, 39, 52, 44, 71, 31, 49, 57, 66],
    'income': [5000, 2000, 3000, 4500, 1500, 2800, 4000, 1800, 6000, 2200, 3500, 1200, 4800, 3900, 1600, 2500, 7000, 3200, 2100, 4300, 1000, 5200, 3600, 2700, 3100, 1400, 4600, 2900, 2300, 1700],
    'family_size': [3, 5, 4, 2, 6, 4, 3, 5, 2, 6, 4, 7, 3, 4, 6, 5, 2, 4, 5, 3, 8, 3, 4, 5, 4, 7, 3, 5, 6, 6],
    'health_risk': [0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 1, 1],
    'incident_count': [1, 3, 2, 0, 4, 2, 1, 3, 0, 4, 1, 5, 1, 2, 4, 3, 0, 2, 3, 1, 5, 1, 2, 3, 2, 4, 1, 3, 4, 5],
    'rating_service': [4, 2, 3, 5, 1, 2, 4, 2, 5, 2, 4, 1, 5, 4, 2, 3, 5, 4, 2, 4, 1, 5, 4, 3, 4, 2, 5, 3, 2, 2],
    'rating_transparency': [5, 2, 3, 4, 1, 2, 4, 3, 5, 2, 4, 1, 5, 4, 2, 3, 5, 4, 2, 4, 1, 5, 4, 3, 4, 2, 5, 3, 2, 2],
    'rating_response': [4, 1, 3, 5, 2, 2, 5, 2, 5, 2, 4, 1, 5, 4, 2, 3, 5, 4, 2, 4, 1, 5, 4, 3, 4, 2, 5, 3, 2, 2],
}


def _safe_float(value, default=0.0):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _rows_from_column_data(column_data):
    required_columns = ['resident_id', 'age', 'income', 'family_size', 'health_risk', 'incident_count']
    if any(column not in column_data for column in required_columns):
        return []

    row_count = len(column_data['resident_id'])
    rows = []
    for index in range(row_count):
        row = {
            'resident_id': _safe_int(column_data['resident_id'][index], index + 1),
            'age': _safe_int(column_data['age'][index], 0),
            'income': _safe_float(column_data['income'][index], 0.0),
            'family_size': max(1, _safe_int(column_data['family_size'][index], 1)),
            'health_risk': _safe_int(column_data['health_risk'][index], 0),
            'incident_count': max(0, _safe_int(column_data['incident_count'][index], 0)),
        }
        for rating_name in RATING_COLUMNS:
            row[rating_name] = min(5, max(1, _safe_int(column_data.get(rating_name, [3] * row_count)[index], 3)))
        row['overall_rating'] = round(sum(row[name] for name in RATING_COLUMNS) / len(RATING_COLUMNS), 2)
        rows.append(row)
    return rows


def _extract_notebook_data(notebook_path: Path):
    try:
        notebook = json.loads(notebook_path.read_text(encoding='utf-8'))
    except Exception:
        return None

    for cell in notebook.get('cells', []):
        if cell.get('cell_type') != 'code':
            continue
        source = ''.join(cell.get('source', []))
        try:
            module = ast.parse(source)
        except SyntaxError:
            continue
        for node in module.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'data':
                    try:
                        parsed = ast.literal_eval(node.value)
                    except Exception:
                        try:
                            compiled = compile(ast.Expression(node.value), str(notebook_path), 'eval')
                            parsed = eval(compiled, {'__builtins__': {}}, {'list': list, 'range': range})
                        except Exception:
                            continue
                    if isinstance(parsed, dict):
                        return parsed
    return None


def _load_notebook_seed_rows(notebook_path=None):
    candidate = Path(notebook_path) if notebook_path else DEFAULT_NOTEBOOK_PATH
    if not candidate.exists():
        return [], None

    column_data = _extract_notebook_data(candidate)
    rows = _rows_from_column_data(column_data or {})
    return rows, (candidate if rows else None)


def _fallback_seed_rows():
    return _rows_from_column_data(THESIS_NOTEBOOK_DATA)


def _derive_health_risk_label(row):
    score = 0
    age = _safe_int(row.get('age'), 0)
    income = _safe_float(row.get('income'), 0.0)
    family_size = max(1, _safe_int(row.get('family_size'), 1))
    incident_count = max(0, _safe_int(row.get('incident_count'), 0))
    family_health_score = _safe_float(row.get('family_health_score'), 0.0)
    health_incident_count = max(0, _safe_int(row.get('health_incident_count'), 0))

    if age >= 65:
        score += 2
    elif age >= 45:
        score += 1

    if income <= 2000:
        score += 2
    elif income <= 3500:
        score += 1

    if family_size >= 6:
        score += 2
    elif family_size >= 4:
        score += 1

    if incident_count >= 4:
        score += 2
    elif incident_count >= 2:
        score += 1

    if family_health_score >= 7:
        score += 2
    elif family_health_score >= 4:
        score += 1

    if health_incident_count >= 2:
        score += 2
    elif health_incident_count == 1:
        score += 1

    return 1 if score >= 5 else 0


def _augment_rows(rows):
    augmented = []
    for index, row in enumerate(rows):
        for income_factor in (0.9, 1.0, 1.1):
            for incident_delta in (0, 1):
                variant = dict(row)
                variant['resident_id'] = f"{row.get('resident_id', index + 1)}-v{len(augmented) + 1}"
                variant['income'] = round(max(0.0, _safe_float(row.get('income'), 0.0) * income_factor), 2)
                variant['incident_count'] = max(0, _safe_int(row.get('incident_count'), 0) + incident_delta)
                variant['family_size'] = max(1, _safe_int(row.get('family_size'), 1) + (1 if index % 3 == 0 and incident_delta else 0))
                if 'health_risk' not in variant:
                    variant['health_risk'] = _derive_health_risk_label(variant)
                variant['overall_rating'] = round(sum(_safe_int(variant.get(name), 3) for name in RATING_COLUMNS) / len(RATING_COLUMNS), 2)
                augmented.append(variant)
    return augmented


def _load_database_rows(db_path: Path):
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    family_rows = {
        row['id']: row
        for row in cur.execute('SELECT id, size, health_risk_score FROM family').fetchall()
    }

    incident_rows = {}
    for row in cur.execute(
        'SELECT reported_by, type, COUNT(*) AS count FROM emergency GROUP BY reported_by, type'
    ).fetchall():
        incident_rows.setdefault(row['reported_by'], {'total': 0, 'health': 0, 'accident': 0})
        incident_rows[row['reported_by']]['total'] += _safe_int(row['count'], 0)
        incident_rows[row['reported_by']][row['type'] or 'accident'] = _safe_int(row['count'], 0)

    rows = []
    for user in cur.execute(
        'SELECT id, birthdate, monthly_income, family_id FROM user WHERE role = "resident"'
    ).fetchall():
        family = family_rows.get(user['family_id'])
        if not family:
            continue

        birth_year = int(str(user['birthdate'])[:4]) if user['birthdate'] else None
        age = max(0, 2026 - birth_year) if birth_year else 30
        incidents = incident_rows.get(user['id'], {'total': 0, 'health': 0, 'accident': 0})
        health_score = _safe_float(family['health_risk_score'], 0.0)
        total_incidents = max(0, _safe_int(incidents['total'], 0))

        if total_incidents >= 4 or health_score >= 7:
            ratings = (2, 2, 2)
        elif total_incidents >= 2 or health_score >= 4:
            ratings = (3, 3, 3)
        else:
            ratings = (4, 4, 4)

        row = {
            'resident_id': user['id'],
            'age': age,
            'income': _safe_float(user['monthly_income'], 0.0),
            'family_size': max(1, _safe_int(family['size'], 1)),
            'incident_count': total_incidents,
            'family_health_score': health_score,
            'health_incident_count': max(0, _safe_int(incidents.get('health'), 0)),
            'accident_incident_count': max(0, _safe_int(incidents.get('accident'), 0)),
            'rating_service': ratings[0],
            'rating_transparency': ratings[1],
            'rating_response': ratings[2],
        }
        row['health_risk'] = _derive_health_risk_label(row)
        row['overall_rating'] = round(sum(row[name] for name in RATING_COLUMNS) / len(RATING_COLUMNS), 2)
        rows.append(row)

    conn.close()
    return rows


def build_training_rows(db_path=DEFAULT_DB_PATH, notebook_path=None):
    notebook_rows, resolved_notebook_path = _load_notebook_seed_rows(notebook_path=notebook_path)
    seed_rows = notebook_rows or _fallback_seed_rows()
    db_rows = _load_database_rows(Path(db_path))
    base_rows = seed_rows + db_rows
    return {
        'rows': base_rows + _augment_rows(base_rows),
        'seed_rows_used': len(seed_rows),
        'database_rows_used': len(db_rows),
        'notebook_path': str(resolved_notebook_path) if resolved_notebook_path else None,
    }


def train(
    db_path=DEFAULT_DB_PATH,
    output_model_path=DEFAULT_MODEL_PATH,
    output_metadata_path=DEFAULT_METADATA_PATH,
    notebook_path=None,
):
    import joblib
    import pandas as pd
    from sklearn.cluster import KMeans
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import train_test_split

    training_bundle = build_training_rows(db_path=db_path, notebook_path=notebook_path)
    rows = training_bundle['rows']
    if len(rows) < 10:
        raise SystemExit('Not enough rows to train the health-risk model.')

    df = pd.DataFrame(rows)
    x = df[FEATURES]
    y = df[TARGET]

    stratify_target = y if len(set(y.tolist())) > 1 else None
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.2,
        random_state=42,
        stratify=stratify_target,
    )

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=1,
        random_state=42,
    )
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)

    unique_incident_counts = max(1, df['incident_count'].nunique())
    cluster_count = min(3, unique_incident_counts)
    cluster_model = None
    cluster_centers = []
    if cluster_count >= 2:
        cluster_model = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
        cluster_model.fit(df[['incident_count']])
        cluster_centers = sorted(round(float(value[0]), 4) for value in cluster_model.cluster_centers_)
    elif not df.empty:
        cluster_centers = [round(float(df['incident_count'].mean()), 4)]

    model_payload = {
        'model': model,
        'features': FEATURES,
        'target': TARGET,
        'threshold': 0.5,
        'dataset_source': 'thesis_notebook_seed_with_barangay_rows',
        'incident_cluster_model': cluster_model,
        'incident_cluster_centers': cluster_centers,
    }

    output_model_path = Path(output_model_path)
    output_metadata_path = Path(output_metadata_path)
    output_model_path.parent.mkdir(parents=True, exist_ok=True)
    output_metadata_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_payload, output_model_path)

    metadata = {
        'model_type': 'RandomForestClassifier',
        'model_path': str(output_model_path),
        'features': FEATURES,
        'target': TARGET,
        'training_rows': len(df),
        'database_rows_used': training_bundle['database_rows_used'],
        'seed_rows_used': training_bundle['seed_rows_used'],
        'source_notebook_path': training_bundle['notebook_path'],
        'accuracy': accuracy_score(y_test, predictions),
        'feature_importances': dict(zip(FEATURES, model.feature_importances_.tolist())),
        'incident_cluster_centers': cluster_centers,
        'dataset_note': 'Training follows the thesis notebook structure using age, income, family size, and incident count.',
        'rating_note': 'Service, transparency, and response ratings are retained in the dataset for thesis traceability but are not classifier inputs.',
    }
    output_metadata_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return metadata


if __name__ == '__main__':
    result = train(notebook_path=DEFAULT_NOTEBOOK_PATH if DEFAULT_NOTEBOOK_PATH.exists() else None)
    print(json.dumps(result, indent=2))
