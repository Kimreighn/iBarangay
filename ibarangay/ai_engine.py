import random

from ai_model import analyze_community_risk


RELIEF_STRATEGIES = {
    'balanced_class_mix': {
        'label': 'Balanced class mix',
        'focus': 'keeps support spread across all family classes',
        'class_weights': {'A': 0.55, 'B': 0.95, 'C': 1.55, 'D': 2.05},
        'size_step': 0.12,
        'health_weight': 0.08,
        'aid_penalty': 0.04,
        'jitter': 0.08,
    },
    'lower_class_priority': {
        'label': 'Lower-class priority',
        'focus': 'pushes more budget toward Class C and Class D households',
        'class_weights': {'A': 0.4, 'B': 0.8, 'C': 1.8, 'D': 2.45},
        'size_step': 0.1,
        'health_weight': 0.07,
        'aid_penalty': 0.03,
        'jitter': 0.1,
    },
    'household_size_push': {
        'label': 'Household size push',
        'focus': 'gives more weight to larger families while keeping class differences',
        'class_weights': {'A': 0.5, 'B': 0.9, 'C': 1.5, 'D': 2.0},
        'size_step': 0.18,
        'health_weight': 0.06,
        'aid_penalty': 0.04,
        'jitter': 0.09,
    },
    'health_buffer_mix': {
        'label': 'Health buffer mix',
        'focus': 'adds more budget buffer to families with higher health-risk scores',
        'class_weights': {'A': 0.48, 'B': 0.88, 'C': 1.48, 'D': 2.1},
        'size_step': 0.11,
        'health_weight': 0.13,
        'aid_penalty': 0.035,
        'jitter': 0.08,
    },
}


def _safe_float(value, default=0.0):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def _format_money(value):
    return f"{_safe_float(value):,.2f}"


def _pick_strategy(iteration):
    rotation = [
        'balanced_class_mix',
        'lower_class_priority',
        'household_size_push',
        'health_buffer_mix',
    ]
    code = rotation[max(0, int(iteration or 0)) % len(rotation)]
    return code, RELIEF_STRATEGIES[code], rotation


def _family_reasons(family):
    reasons = [f"class {getattr(family, 'class_type', 'N/A')} priority"]
    if int(getattr(family, 'size', 1) or 1) >= 5:
        reasons.append('large family size')
    if _safe_float(getattr(family, 'health_risk_score', 0.0)) >= 5:
        reasons.append('higher health-risk score')
    if _safe_float(getattr(family, 'past_aid_received', 0.0)) <= 0:
        reasons.append('low previous aid')
    return reasons[:4]


def calculate_relief_allocation(
    total_budget,
    families,
    relief_type="mixed",
    residents=None,
    emergencies=None,
    barangay_name=None,
    iteration=0,
):
    budget = _safe_float(total_budget)
    families = [family for family in (families or []) if family]

    strategy_code, strategy, rotation = _pick_strategy(iteration)
    if budget <= 0 or not families:
        return {
            'allocations': [],
            'strategy': {
                'code': strategy_code,
                'label': strategy['label'],
                'focus': strategy['focus'],
                'iteration': max(0, int(iteration or 0)) + 1,
            },
            'ai_summary': 'The AI calculator needs a positive budget and at least one family record before it can generate a class-based distribution plan.',
            'ai_recommendation': 'Update the budget or register family records in the current barangay, then run the calculator again.',
            'analysis_metadata': {
                'barangay_name': barangay_name or 'Current scope',
                'families_considered': len(families),
                'relief_type': relief_type,
                'calculation_mode': 'class_randomized_only',
            },
        }

    rng = random.Random(f"{barangay_name or 'barangay'}|{budget}|{iteration}|{len(families)}")
    scored_families = []
    total_score = 0.0

    for family in families:
        base_weight = strategy['class_weights'].get(getattr(family, 'class_type', None), 1.0)
        size_factor = 1.0 + max(0, int(getattr(family, 'size', 1) or 1) - 1) * strategy['size_step']
        health_factor = 1.0 + _safe_float(getattr(family, 'health_risk_score', 0.0)) * strategy['health_weight']
        aid_penalty = (_safe_float(getattr(family, 'past_aid_received', 0.0)) / 1000.0) * strategy['aid_penalty']
        jitter = rng.uniform(1.0 - strategy['jitter'], 1.0 + strategy['jitter'])

        final_weight = (base_weight * size_factor * health_factor * jitter) - aid_penalty
        final_weight = max(final_weight, 0.12)

        scored_families.append({
            'family': family,
            'score': final_weight,
            'reasons': _family_reasons(family),
        })
        total_score += final_weight

    raw_allocations = []
    for item in scored_families:
        share = (item['score'] / total_score) if total_score > 0 else 0
        raw_amount = share * budget
        rounded_amount = round(raw_amount / 50) * 50
        raw_allocations.append({
            'family_id': item['family'].id,
            'class_type': item['family'].class_type,
            'allocated_amount': max(0.0, rounded_amount),
            'allocation_percent': round(share * 100, 2),
            'score': round(item['score'], 4),
            'explanation': ', '.join(item['reasons']),
        })

    rounded_total = sum(item['allocated_amount'] for item in raw_allocations)
    difference = round(budget - rounded_total, 2)
    if raw_allocations and difference != 0:
        raw_allocations[0]['allocated_amount'] = round(raw_allocations[0]['allocated_amount'] + difference, 2)

    allocations = sorted(raw_allocations, key=lambda row: (-row['allocated_amount'], row['family_id']))
    top_allocation = allocations[0] if allocations else None
    class_counts = {}
    for family in families:
        class_type = getattr(family, 'class_type', 'N/A')
        class_counts[class_type] = class_counts.get(class_type, 0) + 1
    class_mix_text = ', '.join(f'Class {key}: {value}' for key, value in sorted(class_counts.items()))

    summary = (
        f"{strategy['label']} for {barangay_name or 'the selected barangay'} processed {len(families)} family record(s). "
        f"This run uses only family class, household size, health-risk score, past aid, and a randomized class-based adjustment."
    )
    if class_mix_text:
        summary += f" Family mix reviewed: {class_mix_text}."

    recommendation_parts = []
    if top_allocation:
        recommendation_parts.append(
            f"Top suggestion in this run is Family #{top_allocation['family_id']} at PHP {_format_money(top_allocation['allocated_amount'])} based on {top_allocation['explanation']}."
        )
    if len(rotation) > 1:
        next_code = rotation[(max(0, int(iteration or 0)) + 1) % len(rotation)]
        recommendation_parts.append(
            f"Run the calculator again to compare it with the {RELIEF_STRATEGIES[next_code]['label'].lower()} scenario."
        )

    return {
        'allocations': allocations,
        'strategy': {
            'code': strategy_code,
            'label': strategy['label'],
            'focus': strategy['focus'],
            'iteration': max(0, int(iteration or 0)) + 1,
        },
        'ai_summary': summary,
        'ai_recommendation': ' '.join(recommendation_parts[:2]),
        'analysis_metadata': {
            'barangay_name': barangay_name or 'Current scope',
            'families_considered': len(families),
            'relief_type': relief_type,
            'calculation_mode': 'class_randomized_only',
        },
    }


def generate_financial_summary(month, year, total, relief, expenses):
    """Mocks an NLP summary generation based on financial data."""
    return (
        f"In {month}/{year}, the top spending category was Relief Distribution with PHP {relief:,.2f}, "
        f"followed by Project Expenses of PHP {expenses:,.2f}. "
        f"The barangay utilized its available budget of PHP {total:,.2f}."
    )


def analyze_ratings(ratings_list):
    """Mocks NLP to summarize written feedback across many ratings."""
    if not ratings_list:
        return "No feedback available."

    avg_resp = sum(r.responsiveness for r in ratings_list) / len(ratings_list)
    avg_fair = sum(r.fairness for r in ratings_list) / len(ratings_list)

    if avg_resp < 3.0 or avg_fair < 3.0:
        return "Warning: Declining performance. AI detected repeated complaints about service quality and unresponsiveness. Immediate review required."
    return "Positive trends detected: AI analysis shows strong community involvement, praised fairness, and satisfaction with recent aid distribution."


def analyze_emergency_hotspots(emgs, users=None, filter_type=None, barangay_name=None):
    community_analysis = analyze_community_risk(
        users or [],
        emgs or [],
        filter_type=filter_type,
        include_profile_details=False,
        barangay_name=barangay_name,
    )
    return community_analysis['map_risk_signals'], community_analysis['map_risk_summary']


def analyze_incident_and_health_risks(
    emgs,
    users,
    filter_type=None,
    include_profile_details=False,
    barangay_name=None,
    iteration=0,
):
    community_analysis = analyze_community_risk(
        users,
        emgs,
        filter_type=filter_type,
        include_profile_details=include_profile_details,
        barangay_name=barangay_name,
        iteration=iteration,
    )

    insight_parts = [
        community_analysis['map_risk_summary'],
        community_analysis['incident_summary'],
        f"Potential health risks: {community_analysis['health_summary']}" if community_analysis['health_summary'] else '',
    ]
    if community_analysis['predictive_alerts']:
        insight_parts.append(community_analysis['predictive_alerts'][0])

    if insight_parts:
        shift = max(0, int(iteration or 0)) % len(insight_parts)
        insight_parts = insight_parts[shift:] + insight_parts[:shift]

    return {
        'hotspots': community_analysis['map_risk_signals'],
        'insight': ' '.join(part for part in insight_parts if part),
        'incident_patterns': community_analysis['incident_patterns'],
        'health_risks': community_analysis['health_risks'],
        'incident_summary': community_analysis['incident_summary'],
        'health_summary': community_analysis['health_summary'],
        'map_risk_summary': community_analysis['map_risk_summary'],
        'map_risk_signals': community_analysis['map_risk_signals'],
        'predictive_alerts': community_analysis['predictive_alerts'],
        'risk_overview': community_analysis['risk_overview'],
        'recommendations': community_analysis['recommendations'],
        'barangay_profile': community_analysis['barangay_profile'],
        'analysis_metadata': community_analysis['analysis_metadata'],
    }
