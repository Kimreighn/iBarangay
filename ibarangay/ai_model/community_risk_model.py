import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from time_utils import ph_today


BASE_DIR = Path(__file__).resolve().parent
TRAINED_MODEL_PATH = BASE_DIR / 'health_risk_model.joblib'
TRAINED_MODEL_METADATA_PATH = BASE_DIR / 'health_risk_model.json'
_TRAINED_MODEL_CACHE = None
_TRAINED_MODEL_METADATA_CACHE = None


def _safe_float(value, default=0.0):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def _age_from_birthdate(birthdate):
    if not birthdate:
        return None
    if isinstance(birthdate, datetime):
        birthdate = birthdate.date()
    if not isinstance(birthdate, date):
        return None
    today = ph_today()
    return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))


def _risk_level(score):
    if score >= 75:
        return 'critical'
    if score >= 55:
        return 'high'
    if score >= 35:
        return 'moderate'
    return 'low'


def _format_purok(purok):
    return str(purok) if purok not in [None, '', 'Unknown'] else 'Unknown'


def _distance(lat1, lng1, lat2, lng2):
    return ((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2) ** 0.5


def _pick_variant(options, iteration=0, offset=0):
    if not options:
        return ''
    index = (max(0, int(iteration or 0)) + offset) % len(options)
    return options[index]


def _load_trained_health_model():
    global _TRAINED_MODEL_CACHE
    if _TRAINED_MODEL_CACHE is not None:
        return _TRAINED_MODEL_CACHE

    if not TRAINED_MODEL_PATH.exists():
        _TRAINED_MODEL_CACHE = False
        return _TRAINED_MODEL_CACHE

    try:
        import joblib
        _TRAINED_MODEL_CACHE = joblib.load(TRAINED_MODEL_PATH)
    except Exception:
        _TRAINED_MODEL_CACHE = False
    return _TRAINED_MODEL_CACHE


def _load_trained_health_model_metadata():
    global _TRAINED_MODEL_METADATA_CACHE
    if _TRAINED_MODEL_METADATA_CACHE is not None:
        return _TRAINED_MODEL_METADATA_CACHE

    if not TRAINED_MODEL_METADATA_PATH.exists():
        _TRAINED_MODEL_METADATA_CACHE = {}
        return _TRAINED_MODEL_METADATA_CACHE

    try:
        _TRAINED_MODEL_METADATA_CACHE = json.loads(TRAINED_MODEL_METADATA_PATH.read_text(encoding='utf-8'))
    except Exception:
        _TRAINED_MODEL_METADATA_CACHE = {}
    return _TRAINED_MODEL_METADATA_CACHE


def _incident_counts_by_reporter(emergencies):
    counts = defaultdict(lambda: {'total': 0, 'health': 0, 'accident': 0})
    for emergency in emergencies:
        reporter_id = getattr(emergency, 'reported_by', None)
        if reporter_id is None:
            continue
        emergency_type = getattr(emergency, 'type', '') or 'unknown'
        counts[reporter_id]['total'] += 1
        counts[reporter_id][emergency_type] += 1
    return counts


def _analyze_purok_health_patterns(emergencies):
    """Analyze health incident patterns by purok location"""
    purok_patterns = defaultdict(lambda: {
        'total_incidents': 0,
        'health_incidents': 0,
        'accident_incidents': 0,
        'residents_count': 0,
        'health_rate': 0.0,
        'accident_rate': 0.0
    })

    for emergency in emergencies:
        purok = getattr(emergency, 'purok', None)
        if purok is None:
            purok = 'Unknown'

        purok_patterns[purok]['total_incidents'] += 1

        emergency_type = getattr(emergency, 'type', '').lower()
        if emergency_type == 'health':
            purok_patterns[purok]['health_incidents'] += 1
        elif emergency_type == 'accident':
            purok_patterns[purok]['accident_incidents'] += 1

    # Calculate rates
    for purok, pattern in purok_patterns.items():
        if pattern['total_incidents'] > 0:
            pattern['health_rate'] = pattern['health_incidents'] / pattern['total_incidents']
            pattern['accident_rate'] = pattern['accident_incidents'] / pattern['total_incidents']

    return dict(purok_patterns)


def _calculate_community_health_indicators(users, emergencies):
    """Calculate overall community health indicators"""
    total_residents = sum(1 for user in users if getattr(user, 'role', None) == 'resident')
    total_emergencies = len(emergencies)
    health_emergencies = sum(1 for e in emergencies if getattr(e, 'type', '').lower() == 'health')

    # Calculate average incidents per resident
    avg_incidents_per_resident = total_emergencies / max(total_residents, 1)

    # Calculate health emergency rate
    health_rate = health_emergencies / max(total_emergencies, 1)

    # Analyze age distribution
    ages = []
    for user in users:
        if getattr(user, 'role', None) == 'resident':
            age = _age_from_birthdate(getattr(user, 'birthdate', None))
            if age is not None:
                ages.append(age)

    avg_age = sum(ages) / max(len(ages), 1) if ages else 40
    senior_count = sum(1 for age in ages if age >= 60)

    return {
        'total_residents': total_residents,
        'total_emergencies': total_emergencies,
        'health_emergencies': health_emergencies,
        'avg_incidents_per_resident': avg_incidents_per_resident,
        'community_health_rate': health_rate,
        'avg_age': avg_age,
        'senior_count': senior_count,
        'senior_rate': senior_count / max(total_residents, 1)
    }


def estimate_community_health_risk_score(user, purok_health_patterns, community_indicators):
    """Estimate health risk score based on community patterns and personal factors"""
    age = _age_from_birthdate(getattr(user, 'birthdate', None))
    monthly_income = _safe_float(getattr(user, 'monthly_income', 0.0))
    family = getattr(user, 'family', None)
    family_size = int(getattr(family, 'size', 1) or 1)
    purok = getattr(user, 'purok', None)

    score = 0
    factors = []

    # Personal health risk factors
    if age is not None:
        if age >= 70:
            score += 30
            factors.append('senior resident age 70+')
        elif age >= 60:
            score += 20
            factors.append('senior resident age 60+')
        elif age >= 45:
            score += 10
            factors.append('middle-age health monitoring')

    if monthly_income and monthly_income <= 5000:
        score += 15
        factors.append('low socioeconomic status')

    if family_size >= 6:
        score += 12
        factors.append('large household size')

    # Community pattern factors
    purok_pattern = purok_health_patterns.get(purok, {})
    if purok_pattern.get('health_rate', 0) > 0.5:
        score += 20
        factors.append('high health incident rate in purok')
    elif purok_pattern.get('health_rate', 0) > 0.3:
        score += 12
        factors.append('elevated health incident rate in purok')

    if purok_pattern.get('total_incidents', 0) >= 5:
        score += 15
        factors.append('frequent incidents in purok')

    # Community-wide factors
    if community_indicators['community_health_rate'] > 0.6:
        score += 10
        factors.append('high community health emergency rate')

    if community_indicators['senior_rate'] > 0.3:
        score += 8
        factors.append('high senior population in community')

    # Apply trained model if available
    trained_model_payload = _load_trained_health_model()
    if trained_model_payload and isinstance(trained_model_payload, dict):
        model = trained_model_payload.get('model')
        features = trained_model_payload.get('features') or [
            'age', 'income', 'family_size', 'purok_health_rate', 'community_health_rate'
        ]
        feature_map = {
            'age': age or community_indicators['avg_age'],
            'income': monthly_income,
            'family_size': family_size,
            'purok_health_rate': purok_pattern.get('health_rate', 0),
            'community_health_rate': community_indicators['community_health_rate'],
        }
        try:
            row = [[feature_map.get(feature_name, 0) for feature_name in features]]
            try:
                import pandas as pd
                row = pd.DataFrame(row, columns=features)
            except Exception:
                pass
            if hasattr(model, 'predict_proba'):
                probability = float(model.predict_proba(row)[0][1])
            else:
                probability = float(model.predict(row)[0])
            model_score = max(0.0, min(100.0, probability * 100.0))
            blended_score = round((score * 0.6) + (model_score * 0.4), 2)
            factors = ['AI community health model'] + factors
            return blended_score, factors[:5]
        except Exception:
            pass

    return min(score, 100), factors


def build_purok_health_risk_profiles(emergencies, users, limit=8):
    """Analyze health risks at the purok/community level based on incident patterns"""
    purok_patterns = _analyze_purok_health_patterns(emergencies)
    community_indicators = _calculate_community_health_indicators(users, emergencies)

    purok_profiles = []

    for purok, pattern in purok_patterns.items():
        if purok == 'Unknown' or pattern['total_incidents'] == 0:
            continue

        # Calculate purok-level health risk score
        score = 0
        factors = []

        # Incident frequency factors
        if pattern['total_incidents'] >= 10:
            score += 25
            factors.append('very high incident frequency')
        elif pattern['total_incidents'] >= 5:
            score += 15
            factors.append('high incident frequency')

        # Health incident rate factors
        health_rate = pattern['health_rate']
        if health_rate >= 0.6:
            score += 30
            factors.append('critical health incident rate')
        elif health_rate >= 0.4:
            score += 20
            factors.append('high health incident rate')
        elif health_rate >= 0.25:
            score += 10
            factors.append('elevated health incident rate')

        # Accident patterns
        accident_rate = pattern.get('accident_rate', 0)
        if accident_rate >= 0.7:
            score += 15
            factors.append('predominantly accident incidents')

        # Community context
        if community_indicators['community_health_rate'] > 0.5:
            score += 10
            factors.append('high community health emergency rate')

        # Resident density consideration
        resident_count = sum(1 for user in users
                           if getattr(user, 'role', None) == 'resident'
                           and getattr(user, 'purok', None) == purok)
        if resident_count > 0:
            incidents_per_resident = pattern['total_incidents'] / resident_count
            if incidents_per_resident >= 2:
                score += 15
                factors.append('high incidents per resident')
            elif incidents_per_resident >= 1:
                score += 8
                factors.append('elevated incidents per resident')

        risk_level = _risk_level(score)

        purok_profiles.append({
            'purok': purok,
            'resident_count': resident_count,
            'total_incidents': pattern['total_incidents'],
            'health_incidents': pattern['health_incidents'],
            'accident_incidents': pattern['accident_incidents'],
            'health_rate': health_rate,
            'incidents_per_resident': incidents_per_resident if resident_count > 0 else 0,
            'risk_score': score,
            'risk_level': risk_level,
            'factors': factors[:4],
        })

    return sorted(purok_profiles, key=lambda item: item['risk_score'], reverse=True)[:limit]


def build_health_risk_profiles(users, emergencies, limit=8):
    """Legacy function - now delegates to purok-level analysis"""
    purok_profiles = build_purok_health_risk_profiles(emergencies, users, limit)

    # Convert purok profiles to individual profiles for backward compatibility
    profiles = []
    for purok_profile in purok_profiles:
        # Find residents in this purok to create individual profiles
        purok_residents = [user for user in users
                          if getattr(user, 'role', None) == 'resident'
                          and getattr(user, 'purok', None) == purok_profile['purok']]

        for resident in purok_residents[:2]:  # Limit to 2 residents per purok
            profiles.append({
                'user_id': getattr(resident, 'id', None),
                'full_name': getattr(resident, 'full_name', 'Unknown'),
                'purok': purok_profile['purok'],
                'age': _age_from_birthdate(getattr(resident, 'birthdate', None)),
                'family_size': int(getattr(getattr(resident, 'family', None), 'size', 1) or 1),
                'monthly_income': _safe_float(getattr(resident, 'monthly_income', 0.0)),
                'incident_count': purok_profile['total_incidents'],
                'health_incident_count': purok_profile['health_incidents'],
                'risk_score': purok_profile['risk_score'],
                'risk_level': purok_profile['risk_level'],
                'factors': purok_profile['factors'],
            })

    return sorted(profiles, key=lambda item: item['risk_score'], reverse=True)[:limit]


def analyze_incident_patterns(emergencies, filter_type=None, iteration=0):
    filtered = [e for e in emergencies if not filter_type or getattr(e, 'type', None) == filter_type]
    if not filtered:
        return {
            'total_records': 0,
            'type_counts': {},
            'purok_counts': {},
            'repeated_puroks': [],
            'summary': f"No {filter_type or 'incident'} records are available for pattern analysis.",
        }

    type_counts = Counter((getattr(e, 'type', None) or 'unknown') for e in filtered)
    purok_counts = Counter(_format_purok(getattr(e, 'purok', None)) for e in filtered)
    most_common_type, most_common_type_count = type_counts.most_common(1)[0]
    top_purok, top_purok_count = purok_counts.most_common(1)[0]
    repeated_puroks = [
        {'purok': purok, 'count': count}
        for purok, count in purok_counts.most_common()
        if count > 1
    ]

    summary_options = [
        (
            f"Community incident analysis: {len(filtered)} records reviewed across {len(purok_counts)} purok(s). "
            f"Most frequent incidents are {most_common_type} ({most_common_type_count}). "
            f"Highest activity concentration is Purok {top_purok} with {top_purok_count} records."
        ),
        (
            f"Barangay incident pattern scan: {len(filtered)} report(s) analyzed from {len(purok_counts)} purok(s). "
            f"The leading incident type is {most_common_type} with {most_common_type_count} case(s). "
            f"Purok {top_purok} shows the highest incident concentration at {top_purok_count} record(s)."
        ),
        (
            f"Community safety review: {len(filtered)} incident record(s) examined across {len(purok_counts)} purok(s). "
            f"{most_common_type.capitalize()} incidents lead with {most_common_type_count} report(s), "
            f"while Purok {top_purok} has the highest incident density at {top_purok_count} record(s)."
        ),
    ]
    summary = _pick_variant(summary_options, iteration)
    if repeated_puroks:
        repeated = ', '.join(f"Purok {item['purok']} ({item['count']})" for item in repeated_puroks[:3])
        repeated_options = [
            f" Repeated activity detected in {repeated}.",
            f" Recurring pressure points were also seen in {repeated}.",
            f" The repeat-report pattern is strongest in {repeated}.",
        ]
        summary += _pick_variant(repeated_options, iteration, offset=1)

    return {
        'total_records': len(filtered),
        'type_counts': dict(type_counts),
        'purok_counts': dict(purok_counts),
        'repeated_puroks': repeated_puroks,
        'summary': summary,
    }


def _cluster_emergencies(emergencies, threshold=0.0012):
    clusters = []
    for emergency in emergencies:
        lat = getattr(emergency, 'lat', None)
        lng = getattr(emergency, 'lng', None)
        if lat is None or lng is None:
            continue

        matched_cluster = None
        for cluster in clusters:
            if _distance(lat, lng, cluster['lat'], cluster['lng']) < threshold:
                matched_cluster = cluster
                break

        if not matched_cluster:
            matched_cluster = {
                'lat': lat,
                'lng': lng,
                'count': 0,
                'type_counts': Counter(),
                'puroks': [],
                'timestamps': [],
                'latitudes': [],
                'longitudes': [],
            }
            clusters.append(matched_cluster)

        matched_cluster['lat'] = (
            (matched_cluster['lat'] * matched_cluster['count']) + lat
        ) / (matched_cluster['count'] + 1)
        matched_cluster['lng'] = (
            (matched_cluster['lng'] * matched_cluster['count']) + lng
        ) / (matched_cluster['count'] + 1)
        matched_cluster['count'] += 1
        matched_cluster['type_counts'][getattr(emergency, 'type', None) or 'unknown'] += 1
        matched_cluster['puroks'].append(_format_purok(getattr(emergency, 'purok', None)))
        matched_cluster['timestamps'].append(getattr(emergency, 'timestamp', None))
        matched_cluster['latitudes'].append(lat)
        matched_cluster['longitudes'].append(lng)

    return [cluster for cluster in clusters if cluster['count'] > 1]


def _resident_map_points(users):
    return [
        {
            'lat': getattr(user, 'lat', None),
            'lng': getattr(user, 'lng', None),
            'purok': getattr(user, 'purok', None),
        }
        for user in users
        if getattr(user, 'role', None) == 'resident' and getattr(user, 'lat', None) is not None and getattr(user, 'lng', None) is not None
    ]


def _community_center(resident_points, emergencies):
    coords = [(point['lat'], point['lng']) for point in resident_points]
    coords.extend(
        (getattr(emergency, 'lat', None), getattr(emergency, 'lng', None))
        for emergency in emergencies
        if getattr(emergency, 'lat', None) is not None and getattr(emergency, 'lng', None) is not None
    )
    coords = [(lat, lng) for lat, lng in coords if lat is not None and lng is not None]
    if not coords:
        return None

    lat_total = sum(lat for lat, _ in coords)
    lng_total = sum(lng for _, lng in coords)
    return lat_total / len(coords), lng_total / len(coords)


def _count_nearby_households(cluster, resident_points, radius=0.0018):
    return sum(
        1
        for point in resident_points
        if _distance(cluster['lat'], cluster['lng'], point['lat'], point['lng']) <= radius
    )


def _risk_priority(signal):
    level_order = {'critical': 0, 'high': 1, 'moderate': 2, 'low': 3}
    return level_order.get(signal['risk_level'], 4), -signal['count']


def _build_map_risk_signal(cluster, resident_points, community_center, iteration=0):
    dominant_type, dominant_count = cluster['type_counts'].most_common(1)[0]
    nearby_households = _count_nearby_households(cluster, resident_points)
    top_purok = Counter(cluster['puroks']).most_common(1)[0][0] if cluster['puroks'] else 'Unknown'
    distance_from_center = 0.0
    if community_center:
        distance_from_center = _distance(cluster['lat'], cluster['lng'], community_center[0], community_center[1])

    count = cluster['count']
    accident_count = cluster['type_counts'].get('accident', 0)
    health_count = cluster['type_counts'].get('health', 0)
    lat_spread = max(cluster['latitudes']) - min(cluster['latitudes']) if cluster['latitudes'] else 0.0
    lng_spread = max(cluster['longitudes']) - min(cluster['longitudes']) if cluster['longitudes'] else 0.0
    compact_cluster = (lat_spread + lng_spread) <= 0.0016

    category = 'incident_prone_area'
    label = 'Incident-prone area'
    risk_level = 'moderate'
    summary = _pick_variant([
        f"Repeated reports are concentrated in Purok {top_purok}. This zone should stay on active incident monitoring.",
        f"Purok {top_purok} is showing a recurring cluster on the map, so it should remain under active watch.",
        f"The AI keeps circling back to Purok {top_purok} as a repeat-report zone that needs closer monitoring.",
    ], iteration, offset=count)
    predictive_note = _pick_variant([
        f"If response coverage stays unchanged, another emergency report is likely to surface around Purok {top_purok}.",
        f"If nothing shifts operationally, the next mapped report may appear again near Purok {top_purok}.",
        f"The current pattern suggests another report could emerge from the same Purok {top_purok} zone if conditions stay the same.",
    ], iteration, offset=dominant_count)
    validation_note = ''

    if count >= 3 and accident_count >= max(2, dominant_count - 1) and nearby_households >= 2 and distance_from_center >= 0.0025 and compact_cluster:
        category = 'possible_landslide_watch'
        label = 'Possible landslide watch'
        risk_level = 'critical' if count >= 4 else 'high'
        summary = _pick_variant([
            f"Clustered reports near the outer edge of the barangay map suggest possible slope or access-risk exposure in Purok {top_purok}. The hotspot sits near {nearby_households} mapped household(s).",
            f"The AI sees an outer-map cluster in Purok {top_purok} that resembles a possible slope or access-risk watch zone beside {nearby_households} mapped household(s).",
            f"Purok {top_purok} is being tagged for possible landslide-style watch conditions because repeated outer-zone reports are forming near {nearby_households} household(s).",
        ], iteration, offset=nearby_households)
        predictive_note = _pick_variant([
            f"If rain or ground access conditions worsen, Purok {top_purok} may need pre-emptive evacuation checks or road clearing.",
            f"Should weather or terrain conditions decline, Purok {top_purok} may need early inspection, clearing, or evacuation readiness.",
            f"If the same terrain stress continues, responders may need to prepare advance checks and route clearing around Purok {top_purok}.",
        ], iteration, offset=count)
        validation_note = 'Terrain-related tags are heuristic and should be field-validated by barangay responders.'
    elif health_count >= max(2, dominant_count):
        category = 'community_health_watch'
        label = 'Community health watch'
        risk_level = 'critical' if count >= 4 else 'high'
        summary = _pick_variant([
            f"Health-related reports are repeatedly concentrated in Purok {top_purok}, close to {nearby_households} mapped household(s).",
            f"Purok {top_purok} keeps surfacing as the main health-watch cluster, with the hotspot sitting near {nearby_households} mapped household(s).",
            f"The map points to Purok {top_purok} as the strongest recurring health-report zone near {nearby_households} household(s).",
        ], iteration, offset=health_count)
        predictive_note = _pick_variant([
            f"Without household visits and medical follow-up, more health complaints may emerge from Purok {top_purok}.",
            f"If health outreach does not tighten, additional complaints may keep rising from Purok {top_purok}.",
            f"The current pattern suggests more health-related follow-ups may be needed soon in Purok {top_purok}.",
        ], iteration, offset=count)
    elif accident_count >= 2:
        category = 'incident_prone_area'
        label = 'Incident-prone area'
        risk_level = 'high' if count >= 3 else 'moderate'
        summary = _pick_variant([
            f"Accident-related reports repeatedly converge in Purok {top_purok}, marking it as an incident-prone area.",
            f"The strongest accident cluster is centered on Purok {top_purok}, which the AI is tagging as incident-prone.",
            f"Purok {top_purok} continues to gather repeated accident points, making it the clearest incident-prone zone in this run.",
        ], iteration, offset=accident_count)
        predictive_note = _pick_variant([
            f"Without traffic, lighting, or access interventions, another accident report may occur in Purok {top_purok}.",
            f"If road, access, or lighting conditions stay unchanged, Purok {top_purok} may produce another accident report.",
            f"The repeat-incident signal suggests Purok {top_purok} could face another accident case without preventive action.",
        ], iteration, offset=count)
    elif nearby_households >= 3:
        category = 'high_exposure_watch'
        label = 'High-exposure watch zone'
        risk_level = 'high' if count >= 3 else 'moderate'
        summary = _pick_variant([
            f"This hotspot overlaps with {nearby_households} mapped household(s), so even isolated emergencies could affect multiple residents quickly.",
            f"The flagged zone brushes against {nearby_households} mapped household(s), which increases exposure even when incident counts are still moderate.",
            f"Because {nearby_households} mapped household(s) sit near this hotspot, the next emergency here could affect several residents at once.",
        ], iteration, offset=nearby_households)
        predictive_note = _pick_variant([
            f"Preparedness supplies should stay close to Purok {top_purok} because the surrounding households raise the impact of the next report.",
            f"Keeping response supplies near Purok {top_purok} would reduce pressure if another nearby report appears.",
            f"The household density near Purok {top_purok} suggests response materials should stay close for the next alert.",
        ], iteration, offset=count)

    return {
        'lat': round(cluster['lat'], 6),
        'lng': round(cluster['lng'], 6),
        'count': count,
        'purok': top_purok,
        'dominant_type': dominant_type,
        'dominant_count': dominant_count,
        'risk_category': category,
        'risk_label': label,
        'risk_level': risk_level,
        'summary': summary,
        'predictive_note': predictive_note,
        'nearby_households': nearby_households,
        'radius': 150 + max(0, count - 2) * 35 + nearby_households * 15,
        'validation_note': validation_note,
    }


def analyze_map_risks(users, emergencies, filter_type=None, limit=4, iteration=0):
    filtered = [e for e in emergencies if not filter_type or getattr(e, 'type', None) == filter_type]
    if not filtered:
        return (
            "Map-based AI review: no incident coordinates are available for the current analysis scope.",
            [],
        )

    resident_points = _resident_map_points(users)
    clusters = _cluster_emergencies(filtered)
    if not clusters:
        return (
            "Map-based AI review: no recurring hotspot is strong enough yet to classify as a watch zone.",
            [],
        )

    community_center = _community_center(resident_points, filtered)
    signals = [
        _build_map_risk_signal(cluster, resident_points, community_center, iteration=iteration)
        for cluster in clusters
    ]
    signals = sorted(signals, key=_risk_priority)[:limit]
    top_signal = signals[0]

    summary = _pick_variant([
        f"Map-based AI review: {len(signals)} watch zone(s) detected. Highest concern is {top_signal['risk_label']} around Purok {top_signal['purok']} with {top_signal['count']} recurring report(s).",
        f"Map analysis complete: {len(signals)} watch zone(s) are active, led by {top_signal['risk_label']} in Purok {top_signal['purok']} with {top_signal['count']} repeating report(s).",
        f"The map AI found {len(signals)} watch zone(s). The strongest current signal is {top_signal['risk_label']} near Purok {top_signal['purok']} after {top_signal['count']} recurring report(s).",
    ], iteration, offset=len(signals))
    if any(signal['risk_category'] == 'possible_landslide_watch' for signal in signals):
        summary += _pick_variant([
            " Possible landslide tags are heuristic and should be verified on site.",
            " Landslide-style labels are heuristic and still need field validation.",
            " Any landslide-style alert in this run should be treated as a heuristic field-check signal.",
        ], iteration, offset=1)

    return summary, signals


def _health_summary(profiles, include_profile_details, iteration=0):
    if not profiles:
        return _pick_variant([
            "Community health analysis: No significant health risk patterns detected in current incident data.",
            "Health pattern review: Current incident records show no elevated community health concerns.",
            "The AI health analysis found no concerning patterns in the community's incident records.",
        ], iteration)

    # Analyze purok-level patterns from the profiles
    purok_risks = {}
    for profile in profiles:
        purok = profile.get('purok', 'Unknown')
        if purok not in purok_risks:
            purok_risks[purok] = {'score': profile['risk_score'], 'level': profile['risk_level'], 'count': 1}
        else:
            purok_risks[purok]['count'] += 1
            # Keep the highest risk level for the purok
            if profile['risk_score'] > purok_risks[purok]['score']:
                purok_risks[purok]['score'] = profile['risk_score']
                purok_risks[purok]['level'] = profile['risk_level']

    high_risk_puroks = [purok for purok, data in purok_risks.items() if data['level'] in ['high', 'critical']]
    top_purok = max(purok_risks.items(), key=lambda x: x[1]['score']) if purok_risks else None

    if include_profile_details and top_purok:
        purok, data = top_purok
        factors = ', '.join(profiles[0]['factors']) if profiles[0]['factors'] else 'community health indicators'
        purok_info = f" in Purok {purok}" if purok != 'Unknown' else " in unmapped areas"
        return _pick_variant([
            f"Community health analysis: {len(purok_risks)} purok(s) analyzed{purok_info}; {len(high_risk_puroks)} show high or critical health risk patterns. Primary concern is {data['level']} health risk due to {factors}.",
            f"Health pattern analysis: {len(purok_risks)} purok(s) evaluated{purok_info}, with {len(high_risk_puroks)} exhibiting concerning health indicators. The most urgent area shows {data['level']} risk because of {factors}.",
            f"AI community health scan: {len(purok_risks)} purok(s) assessed{purok_info}, including {len(high_risk_puroks)} with elevated health risk patterns. Top priority is {data['level']} risk due to {factors}.",
        ], iteration, offset=len(high_risk_puroks))

    purok_info = f" concentrated in Purok {top_purok[0]}" if top_purok and top_purok[0] != 'Unknown' else ""
    return _pick_variant([
        f"Community health analysis: {len(purok_risks)} purok(s) show elevated risk patterns{purok_info}; {len(high_risk_puroks)} are high or critical priority. Area details limited for community privacy.",
        f"Health pattern analysis: {len(purok_risks)} purok(s) exhibit concerning health indicators{purok_info}, with {len(high_risk_puroks)} in high or critical categories. Location details protected for privacy.",
        f"AI community health scan: {len(purok_risks)} purok(s) display health risk patterns{purok_info}, including {len(high_risk_puroks)} high/critical cases. Area details withheld for privacy.",
    ], iteration, offset=len(high_risk_puroks))


def _risk_overview(profiles):
    levels = Counter(profile['risk_level'] for profile in profiles)
    return {
        'flagged_residents': len(profiles),
        'high_or_critical': sum(1 for profile in profiles if profile['risk_level'] in ['high', 'critical']),
        'critical': levels.get('critical', 0),
        'high': levels.get('high', 0),
        'moderate': levels.get('moderate', 0),
        'top_risk_score': profiles[0]['risk_score'] if profiles else 0,
    }


def _unique_messages(messages, limit=3):
    unique = []
    seen = set()
    for message in messages:
        cleaned = (message or '').strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique.append(cleaned)
        if len(unique) >= limit:
            break
    return unique


def _rotate_messages(messages, iteration=0, limit=None):
    cleaned = [message for message in messages if message]
    if not cleaned:
        return []

    shift = max(0, int(iteration or 0)) % len(cleaned)
    rotated = cleaned[shift:] + cleaned[:shift]
    return rotated[:limit] if limit else rotated


def _build_predictive_alerts(patterns, map_risk_signals, profiles, filter_type=None, iteration=0):
    alerts = []

    if map_risk_signals:
        alerts.append(map_risk_signals[0]['predictive_note'])

    type_counts = patterns.get('type_counts') or {}
    if type_counts:
        top_type, top_count = max(type_counts.items(), key=lambda item: item[1])
        if top_type == 'health':
            alerts.append(
                _pick_variant([
                    f"Community health alert: Health incidents are rising ({top_count} cases) - consider preventive health programs in affected puroks.",
                    f"Health trend warning: {top_count} health-related incidents suggest community health outreach may be needed soon.",
                    f"Preventive health signal: With {top_count} health cases recorded, community health monitoring should be strengthened.",
                ], iteration, offset=top_count)
            )
        elif top_type == 'accident':
            alerts.append(
                _pick_variant([
                    f"Safety alert: Accident incidents are prevalent ({top_count} cases) - review community safety measures and infrastructure.",
                    f"Incident trend: {top_count} accident reports indicate potential safety concerns requiring community attention.",
                    f"Community safety signal: {top_count} accidents recorded suggest infrastructure and safety reviews may be beneficial.",
                ], iteration, offset=top_count)
            )

    high_risk_count = sum(1 for profile in profiles if profile['risk_level'] in ['high', 'critical'])
    if high_risk_count:
        # Group by purok for community-level alerts
        purok_risks = {}
        for profile in profiles:
            if profile['risk_level'] in ['high', 'critical']:
                purok = profile.get('purok', 'Unknown')
                if purok not in purok_risks:
                    purok_risks[purok] = 0
                purok_risks[purok] += 1

        if purok_risks:
            riskiest_purok = max(purok_risks.items(), key=lambda x: x[1])
            alerts.append(
                _pick_variant([
                    f"Community health focus: Purok {riskiest_purok[0]} has {riskiest_purok[1]} resident(s) with elevated health risks - prioritize community health programs there.",
                    f"Targeted health alert: {riskiest_purok[1]} resident(s) in Purok {riskiest_purok[0]} show concerning health patterns requiring community intervention.",
                    f"Health priority zone: Purok {riskiest_purok[0]} identified with {riskiest_purok[1]} high-risk resident(s) - community health support recommended.",
                ], iteration, offset=riskiest_purok[1])
            )
        else:
            alerts.append(
                _pick_variant([
                    f"Community health monitoring: {high_risk_count} resident(s) across the barangay show elevated health risk patterns.",
                    f"Health oversight needed: {high_risk_count} resident(s) have been identified with concerning health risk indicators.",
                    f"Community health attention: {high_risk_count} resident(s) require monitoring due to elevated health risk patterns.",
                ], iteration, offset=high_risk_count)
            )

    unique_alerts = _unique_messages(alerts, limit=5)
    return _rotate_messages(unique_alerts, iteration=iteration, limit=3)


def _build_recommendations(patterns, profiles, map_risk_signals, filter_type=None, iteration=0):
    recommendations = []
    repeated_puroks = patterns.get('repeated_puroks') or []
    type_counts = patterns.get('type_counts') or {}
    risk_overview = _risk_overview(profiles)

    if map_risk_signals:
        top_signal = map_risk_signals[0]
        recommendations.append(
            _pick_variant([
                f"Validate the {top_signal['risk_label'].lower()} around Purok {top_signal['purok']} and pre-position responders nearby.",
                f"Send a field check toward Purok {top_signal['purok']} and stage responders close to the {top_signal['risk_label'].lower()}.",
                f"Use Purok {top_signal['purok']} as the first field-validation point and keep responders positioned near the {top_signal['risk_label'].lower()}.",
            ], iteration, offset=top_signal['count'])
        )

    if repeated_puroks:
        top_purok = repeated_puroks[0]
        response_focus = 'health monitoring visits' if filter_type == 'health' else 'incident-response follow-ups'
        recommendations.append(
            _pick_variant([
                f"Prioritize Purok {top_purok['purok']} for {response_focus}; it has {top_purok['count']} recurring reports in the reviewed records.",
                f"Focus the next round of {response_focus} on Purok {top_purok['purok']}, where {top_purok['count']} recurring reports were logged.",
                f"Move Purok {top_purok['purok']} to the front of the action list for {response_focus} because it already has {top_purok['count']} repeat reports.",
            ], iteration, offset=top_purok['count'])
        )
    elif patterns.get('total_records', 0):
        top_purok_counts = patterns.get('purok_counts') or {}
        if top_purok_counts:
            purok, count = max(top_purok_counts.items(), key=lambda item: item[1])
            recommendations.append(
                _pick_variant([
                    f"Keep Purok {purok} under observation; it currently has the highest single-area activity with {count} record(s).",
                    f"Maintain active watch over Purok {purok} because it still leads the barangay in single-area activity at {count} record(s).",
                    f"Purok {purok} should stay on the monitoring board since it holds the highest current activity count at {count} record(s).",
                ], iteration, offset=count)
            )
    else:
        recommendations.append(
            _pick_variant([
                "Collect more incident records so the AI analysis can detect stronger community trends.",
                "Add more mapped reports over time so the AI can separate weak patterns from real barangay trends.",
                "Keep encoding incident reports because the AI needs a deeper record base to strengthen the next trend scan.",
            ], iteration)
        )

    if type_counts and len(type_counts) > 1:
        top_type, top_count = max(type_counts.items(), key=lambda item: item[1])
        recommendations.append(
            _pick_variant([
                f"Prepare resources for {top_type} cases first because they account for the largest share of reviewed incidents ({top_count}).",
                f"Shift the first resource block toward {top_type} cases, since they make up the largest slice of reviewed incidents ({top_count}).",
                f"Front-load supplies for {top_type} response because that case type currently leads the reviewed records at {top_count}.",
            ], iteration, offset=top_count)
        )

    if risk_overview['high_or_critical'] > 0:
        # Group high-risk residents by purok for community interventions
        purok_risks = {}
        for profile in profiles:
            if profile['risk_level'] in ['high', 'critical']:
                purok = profile.get('purok', 'Unknown')
                if purok not in purok_risks:
                    purok_risks[purok] = 0
                purok_risks[purok] += 1

        if purok_risks:
            riskiest_purok = max(purok_risks.items(), key=lambda x: x[1])
            recommendations.append(
                _pick_variant([
                    f"Launch community health program in Purok {riskiest_purok[0]} where {riskiest_purok[1]} high-risk resident(s) are concentrated.",
                    f"Prioritize Purok {riskiest_purok[0]} for community health interventions with {riskiest_purok[1]} high-risk cases identified.",
                    f"Focus health outreach efforts on Purok {riskiest_purok[0]}, home to {riskiest_purok[1]} residents with elevated health risks.",
                ], iteration, offset=riskiest_purok[1])
            )
        else:
            recommendations.append(
                _pick_variant([
                    f"Implement community-wide health monitoring for {risk_overview['high_or_critical']} resident(s) showing elevated risk patterns.",
                    f"Establish health monitoring protocols for {risk_overview['high_or_critical']} resident(s) with concerning risk indicators.",
                    f"Develop targeted health support plans for {risk_overview['high_or_critical']} resident(s) flagged with high or critical risk levels.",
                ], iteration, offset=risk_overview['high_or_critical'])
            )
    elif profiles:
        recommendations.append(
            _pick_variant([
                "Continue community health surveillance and update resident health data to maintain accurate risk assessments.",
                "Maintain ongoing health monitoring programs and refresh community health records for better risk prediction.",
                "Sustain community health tracking and update resident profiles to keep health risk analysis current.",
            ], iteration)
        )
    else:
        recommendations.append(
            _pick_variant([
                "No significant community health patterns detected; continue routine health data collection for early warning.",
                "Current health indicators are stable; maintain regular resident health record updates for proactive monitoring.",
                "Community health status appears normal; continue updating health data to enable early risk detection.",
            ], iteration)
        )

    if len(map_risk_signals) > 1:
        secondary_signal = map_risk_signals[1]
        recommendations.append(
            _pick_variant([
                f"Schedule a second validation sweep near Purok {secondary_signal['purok']} because another {secondary_signal['risk_label'].lower()} is forming there.",
                f"After the top hotspot, send the next field pass toward Purok {secondary_signal['purok']} where a second {secondary_signal['risk_label'].lower()} is still active.",
                f"Queue a follow-up inspection for Purok {secondary_signal['purok']} since the map also shows a secondary {secondary_signal['risk_label'].lower()} there.",
            ], iteration, offset=secondary_signal['count'])
        )

    unique_recommendations = _unique_messages(recommendations, limit=6)
    return _rotate_messages(unique_recommendations, iteration=iteration, limit=4)


def _privacy_safe_profiles(profiles, include_profile_details):
    if include_profile_details:
        return profiles

    return [
        {
            'purok': profile['purok'],
            'risk_score': profile['risk_score'],
            'risk_level': profile['risk_level'],
            'incident_count': profile['incident_count'],
            'health_incident_count': profile['health_incident_count'],
            'factors': profile['factors'],
        }
        for profile in profiles
    ]


def _build_barangay_profile(users, emergencies, barangay_name):
    residents = [user for user in users if getattr(user, 'role', None) == 'resident']
    mapped_households = sum(
        1
        for user in residents
        if getattr(user, 'lat', None) is not None and getattr(user, 'lng', None) is not None
    )
    return {
        'barangay_name': barangay_name or 'Current scope',
        'resident_count': len(residents),
        'mapped_households': mapped_households,
        'incident_records_reviewed': len(emergencies),
    }


def analyze_community_risk(users, emergencies, filter_type=None, include_profile_details=False, barangay_name=None, iteration=0):
    patterns = analyze_incident_patterns(emergencies, filter_type=filter_type, iteration=iteration)
    health_profiles = build_health_risk_profiles(users, emergencies)
    risk_overview = _risk_overview(health_profiles)
    map_risk_summary, map_risk_signals = analyze_map_risks(users, emergencies, filter_type=filter_type, iteration=iteration)
    predictive_alerts = _build_predictive_alerts(patterns, map_risk_signals, health_profiles, filter_type=filter_type, iteration=iteration)
    trained_metadata = _load_trained_health_model_metadata()
    trained_model_loaded = bool(_load_trained_health_model())

    return {
        'incident_patterns': patterns,
        'health_risks': _privacy_safe_profiles(health_profiles, include_profile_details),
        'incident_summary': patterns['summary'],
        'health_summary': _health_summary(health_profiles, include_profile_details, iteration=iteration),
        'map_risk_summary': map_risk_summary,
        'map_risk_signals': map_risk_signals,
        'predictive_alerts': predictive_alerts,
        'risk_overview': risk_overview,
        'recommendations': _build_recommendations(patterns, health_profiles, map_risk_signals, filter_type=filter_type, iteration=iteration),
        'barangay_profile': _build_barangay_profile(users, emergencies, barangay_name),
        'analysis_metadata': {
            'component': 'AI-based incident and health risk analysis',
            'runtime_model': 'community_risk_model',
            'analysis_scope': filter_type or 'all',
            'barangay_name': barangay_name or 'Current scope',
            'analysis_variant': max(0, int(iteration or 0)) + 1,
            'trained_health_model_loaded': trained_model_loaded,
            'trained_health_model_type': trained_metadata.get('model_type'),
            'trained_health_model_rows': trained_metadata.get('training_rows'),
            'trained_health_model_accuracy': trained_metadata.get('accuracy'),
            'field_validation_note': 'Terrain-related tags such as landslide watch are heuristic and should be validated on site.',
        },
    }
