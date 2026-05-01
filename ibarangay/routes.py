from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for, current_app, send_from_directory, make_response
from models import db, User, Family, Event, FinancialReport, Announcement, Rating, RatingSchedule, RatingScheduleWindow, Emergency, Summons, Post, PostLike, HistoryLog, WelfareDistribution, ReliefDistribution, PushSubscription
from ai_engine import (
    calculate_relief_allocation, generate_financial_summary, analyze_ratings, 
    analyze_incident_and_health_risks
)
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta, date
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
import calendar
import re
import os, uuid, json
from time_utils import ph_now, ph_today, ph_year, serialize_ph_datetime, serialize_utc_datetime, utc_now

try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None

    class WebPushException(Exception):
        pass

def log_action(user_id, action):
    if not user_id: return
    db.session.add(HistoryLog(user_id=user_id, action=action))
    db.session.commit()

def calculate_class(income):
    if income > 30000: return 'A'
    if income > 20000: return 'B'
    if income > 10000: return 'C'
    return 'D'

main = Blueprint('main', __name__)
FULL_DIRECTORY_ROLES = {'bio', 'official', 'superadmin'}
SEARCHABLE_DIRECTORY_ROLES = ('resident', 'official', 'bio')
WELFARE_MANAGER_ROLES = {'bio', 'official', 'superadmin'}
WELFARE_STATUSES = ('planned', 'approved', 'released', 'cancelled')


def is_official_account(user):
    return bool(user and (user.role == 'official' or (user.role == 'bio' and user.is_approved)))


def official_position_label(user):
    if not user:
        return None
    if user.position:
        return user.position
    if user.role in ['official', 'bio']:
        return 'Barangay Official'
    return None


def get_session_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    user = User.query.get(user_id)
    if not user:
        session.clear()
    return user


def get_age(birthdate):
    if not birthdate:
        return None
    today = ph_today()
    return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))


def normalize_barangay_name(value):
    return ' '.join((value or '').strip().lower().split())


def belongs_to_same_barangay(user, target_user):
    if not user or not target_user or user.role == 'superadmin':
        return True
    user_barangay = normalize_barangay_name(user.barangay_name)
    target_barangay = normalize_barangay_name(target_user.barangay_name)
    if user_barangay and target_barangay:
        return user_barangay == target_barangay
    return True


def is_within_viewer_barangay_scope(viewer, target_user):
    if not viewer or viewer.role == 'superadmin':
        return True

    viewer_barangay = normalize_barangay_name(getattr(viewer, 'barangay_name', None))
    if not viewer_barangay:
        return True

    target_barangay = normalize_barangay_name(getattr(target_user, 'barangay_name', None))
    return bool(target_barangay) and viewer_barangay == target_barangay


def filter_users_to_viewer_barangay(viewer, users):
    return [target_user for target_user in users if is_within_viewer_barangay_scope(viewer, target_user)]


def filter_emergencies_to_viewer_barangay(viewer, emergencies, users_by_id=None):
    if not viewer or viewer.role == 'superadmin':
        return emergencies

    viewer_barangay = normalize_barangay_name(getattr(viewer, 'barangay_name', None))
    if not viewer_barangay:
        return emergencies

    filtered = []
    for emergency in emergencies:
        reporter = None
        if users_by_id is not None:
            reporter = users_by_id.get(getattr(emergency, 'reported_by', None))
        elif getattr(emergency, 'reported_by', None):
            reporter = User.query.get(emergency.reported_by)

        if reporter and is_within_viewer_barangay_scope(viewer, reporter):
            filtered.append(emergency)

    return filtered


def is_web_push_configured():
    return bool(
        webpush
        and current_app.config.get('WEB_PUSH_PUBLIC_KEY')
        and current_app.config.get('WEB_PUSH_PRIVATE_KEY')
    )


def get_web_push_unavailable_reason():
    if not webpush:
        return 'pywebpush is not installed on the server.'
    if not current_app.config.get('WEB_PUSH_PUBLIC_KEY') or not current_app.config.get('WEB_PUSH_PRIVATE_KEY'):
        return 'Web push keys are not configured on the server.'
    return ''


def jsonify_no_store(payload, status=200):
    response = make_response(jsonify(payload), status)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response


def unique_active_users(users):
    unique = []
    seen = set()
    for user in users or []:
        if not user or not getattr(user, 'id', None):
            continue
        if getattr(user, 'is_active', True) is False:
            continue
        if user.id in seen:
            continue
        seen.add(user.id)
        unique.append(user)
    return unique


def build_push_payload(title, body, event_key, url_path, tag=None, require_interaction=False):
    return json.dumps({
        'title': title,
        'body': body,
        'eventKey': event_key,
        'url': url_path,
        'tag': tag or f'ibarangay-{event_key}',
        'icon': '/static/default-avatar.svg',
        'badge': '/static/default-avatar.svg',
        'requireInteraction': bool(require_interaction),
        'vibrate': [200, 100, 200] if require_interaction else [120, 60, 120],
    })


def send_push_notifications(users, title, body, *, event_key, url_path='/', tag=None, require_interaction=False):
    recipients = unique_active_users(users)
    if not recipients or not is_web_push_configured():
        return 0

    user_ids = [user.id for user in recipients]
    subscriptions = PushSubscription.query.filter(PushSubscription.user_id.in_(user_ids)).all()
    if not subscriptions:
        return 0

    vapid_private_key = current_app.config.get('WEB_PUSH_PRIVATE_KEY')
    vapid_claims = {
        'sub': current_app.config.get('WEB_PUSH_SUBJECT', 'mailto:alerts@ibarangay.local')
    }
    payload = build_push_payload(title, body, event_key, url_path, tag=tag, require_interaction=require_interaction)
    stale_ids = []
    delivered = 0

    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': subscription.endpoint,
                    'keys': {
                        'p256dh': subscription.p256dh,
                        'auth': subscription.auth,
                    }
                },
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims,
            )
            delivered += 1
        except WebPushException as error:
            response = getattr(error, 'response', None)
            status_code = getattr(response, 'status_code', None)
            if status_code in (404, 410):
                stale_ids.append(subscription.id)
            else:
                current_app.logger.warning('Web push delivery failed for subscription %s: %s', subscription.id, error)
        except Exception as error:
            current_app.logger.warning('Unexpected web push delivery failure for subscription %s: %s', subscription.id, error)

    if stale_ids:
        PushSubscription.query.filter(PushSubscription.id.in_(stale_ids)).delete(synchronize_session=False)
        db.session.commit()

    return delivered


def normalize_duplicate_key(value):
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', (value or '').lower()).split())


def can_manage_welfare(user):
    return bool(user and user.role in WELFARE_MANAGER_ROLES)


def normalize_welfare_status(value):
    status = (value or 'planned').strip().lower()
    return status if status in WELFARE_STATUSES else None


def generate_welfare_reference_code():
    return f"WEL-{ph_now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def parse_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int_list(values):
    if not isinstance(values, list):
        return []

    parsed = []
    seen = set()
    for value in values:
        try:
            parsed_value = int(value)
        except (TypeError, ValueError):
            continue
        if parsed_value in seen:
            continue
        seen.add(parsed_value)
        parsed.append(parsed_value)
    return parsed


def build_welfare_reference_codes(base_reference, count):
    normalized = (base_reference or '').strip().upper()
    if count <= 1:
        reference_codes = [normalized or generate_welfare_reference_code()]
    elif normalized:
        reference_codes = [f"{normalized}-{index:03d}" for index in range(1, count + 1)]
    else:
        reference_codes = [generate_welfare_reference_code() for _ in range(count)]

    existing_codes = {
        row.reference_code
        for row in WelfareDistribution.query.filter(WelfareDistribution.reference_code.in_(reference_codes)).all()
    }
    if existing_codes:
        return None, 'Reference code already exists. Use a unique value.'

    return reference_codes, None


def welfare_family_credit(family_id, status, amount):
    if not family_id or status != 'released':
        return 0.0
    return max(0.0, parse_float(amount, 0.0))


def sync_family_aid_totals(old_family_id, old_status, old_amount, new_family_id, new_status, new_amount):
    old_credit = welfare_family_credit(old_family_id, old_status, old_amount)
    new_credit = welfare_family_credit(new_family_id, new_status, new_amount)

    if old_family_id and old_credit:
        old_family = Family.query.get(old_family_id)
        if old_family:
            old_family.past_aid_received = max(0.0, parse_float(old_family.past_aid_received, 0.0) - old_credit)

    if new_family_id and new_credit:
        new_family = Family.query.get(new_family_id)
        if new_family:
            new_family.past_aid_received = parse_float(new_family.past_aid_received, 0.0) + new_credit


def serialize_welfare_distribution(distribution, viewer=None):
    resident = distribution.resident
    creator = distribution.creator
    return {
        'id': distribution.id,
        'reference_code': distribution.reference_code,
        'resident_id': distribution.resident_id,
        'resident_name': resident.full_name if resident else 'Unknown Resident',
        'resident_barangay': resident.barangay_name if resident else None,
        'purok': resident.purok if resident else None,
        'family_id': distribution.family_id,
        'resident_class_type': resident.family.class_type if resident and resident.family else None,
        'assistance_type': distribution.assistance_type,
        'program_name': distribution.program_name,
        'amount': round(parse_float(distribution.amount, 0.0), 2),
        'quantity': parse_float(distribution.quantity, 0.0),
        'unit': distribution.unit,
        'status': distribution.status,
        'source_funds': distribution.source_funds,
        'distributed_on': distribution.distributed_on.isoformat() if distribution.distributed_on else None,
        'notes': distribution.notes,
        'created_by': distribution.created_by,
        'created_by_name': creator.full_name if creator else None,
        'created_at': serialize_utc_datetime(distribution.created_at),
        'updated_at': serialize_utc_datetime(distribution.updated_at),
        'can_edit': can_manage_welfare(viewer),
    }


def build_welfare_summary(distributions):
    type_totals = {}
    status_totals = {status: 0 for status in WELFARE_STATUSES}
    beneficiary_ids = set()
    released_total = 0.0
    scheduled_total = 0.0
    latest_released_date = None

    for distribution in distributions:
        status = normalize_welfare_status(distribution.status) or 'planned'
        amount = parse_float(distribution.amount, 0.0)

        status_totals[status] = status_totals.get(status, 0) + 1
        beneficiary_ids.add(distribution.resident_id)

        if status in ('planned', 'approved', 'released'):
            scheduled_total += amount

        if status == 'released':
            released_total += amount
            if distribution.distributed_on and (
                latest_released_date is None or distribution.distributed_on > latest_released_date
            ):
                latest_released_date = distribution.distributed_on

        label = distribution.assistance_type or 'Other'
        if label not in type_totals:
            type_totals[label] = {
                'assistance_type': label,
                'count': 0,
                'released_amount': 0.0,
                'scheduled_amount': 0.0,
            }

        type_totals[label]['count'] += 1
        if status in ('planned', 'approved', 'released'):
            type_totals[label]['scheduled_amount'] += amount
        if status == 'released':
            type_totals[label]['released_amount'] += amount

    breakdown = sorted(
        type_totals.values(),
        key=lambda row: (-row['released_amount'], -row['count'], row['assistance_type'].lower())
    )
    for row in breakdown:
        row['released_amount'] = round(row['released_amount'], 2)
        row['scheduled_amount'] = round(row['scheduled_amount'], 2)

    return {
        'total_records': len(distributions),
        'beneficiary_count': len(beneficiary_ids),
        'released_records': status_totals.get('released', 0),
        'pending_records': status_totals.get('planned', 0) + status_totals.get('approved', 0),
        'cancelled_records': status_totals.get('cancelled', 0),
        'released_total': round(released_total, 2),
        'scheduled_total': round(scheduled_total, 2),
        'latest_released_date': latest_released_date.isoformat() if latest_released_date else None,
        'status_totals': status_totals,
        'type_breakdown': breakdown[:6],
    }


def get_rating_schedule_for_barangay(barangay_name):
    barangay_key = normalize_barangay_name(barangay_name)
    if not barangay_key:
        return None
    return RatingSchedule.query.filter_by(barangay_key=barangay_key).first()


def get_rating_schedule_windows_for_barangay(barangay_name):
    barangay_key = normalize_barangay_name(barangay_name)
    if not barangay_key:
        return []

    windows = RatingScheduleWindow.query.filter_by(barangay_key=barangay_key).order_by(RatingScheduleWindow.window_number.asc()).all()
    if windows:
        return windows

    legacy_schedule = get_rating_schedule_for_barangay(barangay_name)
    return [legacy_schedule] if legacy_schedule else []


def is_valid_month_day(month, day):
    if month < 1 or month > 12:
        return False
    return 1 <= day <= calendar.monthrange(2024, month)[1]


def parse_schedule_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def is_rating_window_open(window, today=None):
    if not window:
        return False

    today = today or ph_today()
    current = (today.month, today.day)
    start = (window.start_month, window.start_day)
    end = (window.end_month, window.end_day)

    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def is_rating_schedule_open(schedule, today=None):
    if not schedule:
        return False
    if isinstance(schedule, list):
        return any(is_rating_window_open(window, today) for window in schedule)
    return is_rating_window_open(schedule, today)


def format_rating_window(window):
    if not window:
        return None
    return f"{calendar.month_name[window.start_month]} {window.start_day} to {calendar.month_name[window.end_month]} {window.end_day}"


def format_rating_schedule(schedule):
    if not schedule:
        return None
    if isinstance(schedule, list):
        return '; '.join(
            f"Window {index + 1}: {format_rating_window(window)}"
            for index, window in enumerate(schedule)
        )
    return format_rating_window(schedule)


def serialize_rating_window(window, index=0):
    return {
        'window_number': getattr(window, 'window_number', index + 1),
        'start_month': window.start_month,
        'start_day': window.start_day,
        'end_month': window.end_month,
        'end_day': window.end_day,
        'schedule_text': format_rating_window(window),
        'is_open': is_rating_window_open(window),
    }


def serialize_rating_schedule(schedule):
    is_open = is_rating_schedule_open(schedule)
    if not schedule:
        return {
            'is_configured': False,
            'is_open': False,
            'windows': [],
            'message': 'Ratings are closed until the BIO sets the official rating schedule.'
        }

    windows = schedule if isinstance(schedule, list) else [schedule]
    first_window = windows[0]
    schedule_text = format_rating_schedule(schedule)
    schedule_updated_at = max((window.updated_at for window in windows if window.updated_at), default=None)
    return {
        'is_configured': True,
        'is_open': is_open,
        'barangay_name': first_window.barangay_name,
        'start_month': first_window.start_month,
        'start_day': first_window.start_day,
        'end_month': first_window.end_month,
        'end_day': first_window.end_day,
        'windows': [serialize_rating_window(window, index) for index, window in enumerate(windows)],
        'schedule_text': schedule_text,
        'updated_at': serialize_utc_datetime(schedule_updated_at),
        'message': f"Ratings are {'open' if is_open else 'closed'}. Schedule: {schedule_text}."
    }


def get_bios_for_barangay(barangay_name):
    normalized = normalize_barangay_name(barangay_name)
    if not normalized:
        return []
    return [
        user for user in User.query.filter_by(role='bio').all()
        if normalize_barangay_name(user.barangay_name) == normalized
    ]


def find_barangay_bio_conflict(barangay_name):
    bios = get_bios_for_barangay(barangay_name)
    if not bios:
        return None

    approved = next((bio for bio in bios if bio.is_approved), None)
    if approved:
        return f"A BIO system already exists for {approved.barangay_name or barangay_name}. Ask the current BIO to add another BIO from their officials instead."

    pending = bios[0]
    return f"A BIO request for {pending.barangay_name or barangay_name} is already pending Superadmin approval."


def find_bio_identity_conflict(full_name, position):
    normalized_name = normalize_duplicate_key(full_name)
    normalized_position = normalize_duplicate_key(position)
    if not normalized_name or not normalized_position:
        return None

    for bio in User.query.filter_by(role='bio').all():
        if (
            normalize_duplicate_key(bio.full_name) == normalized_name and
            normalize_duplicate_key(bio.position) == normalized_position
        ):
            return "A BIO with the same full name and position is already registered or pending approval."
    return None


def build_superadmin_barangay_overview():
    barangays = {}

    def ensure_barangay(name):
        display_name = (name or '').strip()
        normalized = normalize_barangay_name(display_name)
        if not normalized:
            return None
        if normalized not in barangays:
            barangays[normalized] = {
                'id': normalized.replace(' ', '-'),
                'name': display_name,
                'residents': 0,
                'officials': 0,
                'bios': 0,
                'pending_bios': 0,
                'posts': 0,
                'reports': 0,
                'incident_reports': 0,
                'health_reports': 0,
                'announcements': 0,
                'events': 0,
                'financial_reports': 0,
                'welfare_distributions': 0,
                'summons': 0,
                'ratings': 0,
                'total_members': 0,
                'other_records': 0,
                'status': 'No BIO yet',
            }
        return barangays[normalized]

    users = User.query.all()
    user_barangays = {}

    for user in users:
        entry = ensure_barangay(user.barangay_name)
        if not entry:
            continue

        user_barangays[user.id] = normalize_barangay_name(user.barangay_name)
        if user.role == 'resident':
            entry['residents'] += 1
            entry['total_members'] += 1
        elif user.role == 'official':
            entry['officials'] += 1
            entry['total_members'] += 1
        elif user.role == 'bio':
            if user.is_approved:
                entry['bios'] += 1
                entry['officials'] += 1
                entry['total_members'] += 1
            else:
                entry['pending_bios'] += 1

    for post in Post.query.all():
        barangay_id = user_barangays.get(post.author_id)
        if barangay_id:
            barangays[barangay_id]['posts'] += 1

    for emergency in Emergency.query.all():
        barangay_id = user_barangays.get(emergency.reported_by)
        if not barangay_id:
            continue
        entry = barangays[barangay_id]
        entry['reports'] += 1
        if emergency.type == 'health':
            entry['health_reports'] += 1
        else:
            entry['incident_reports'] += 1

    for announcement in Announcement.query.all():
        barangay_id = user_barangays.get(announcement.created_by)
        if barangay_id:
            barangays[barangay_id]['announcements'] += 1

    for event in Event.query.all():
        barangay_id = user_barangays.get(event.created_by)
        if barangay_id:
            barangays[barangay_id]['events'] += 1

    for report in FinancialReport.query.all():
        barangay_id = user_barangays.get(report.uploaded_by)
        if barangay_id:
            barangays[barangay_id]['financial_reports'] += 1

    for distribution in WelfareDistribution.query.all():
        barangay_id = user_barangays.get(distribution.resident_id) or user_barangays.get(distribution.created_by)
        if barangay_id:
            barangays[barangay_id]['welfare_distributions'] += 1

    for summon in Summons.query.all():
        barangay_id = user_barangays.get(summon.official_id) or user_barangays.get(summon.resident_id)
        if barangay_id:
            barangays[barangay_id]['summons'] += 1

    for rating in Rating.query.all():
        barangay_id = user_barangays.get(rating.official_id)
        if barangay_id:
            barangays[barangay_id]['ratings'] += 1

    for entry in barangays.values():
        entry['other_records'] = (
            entry['announcements'] +
            entry['events'] +
            entry['financial_reports'] +
            entry['welfare_distributions'] +
            entry['summons'] +
            entry['ratings']
        )
        if entry['bios'] > 0:
            entry['status'] = 'Controlled'
        elif entry['pending_bios'] > 0:
            entry['status'] = 'Pending BIO approval'

    return sorted(barangays.values(), key=lambda item: item['name'].lower())


def parse_json_list(raw_value):
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def normalize_target_users(raw_targets):
    if not isinstance(raw_targets, list):
        return []

    normalized = []
    seen = set()
    for target in raw_targets:
        target_id = None
        name = ''

        if isinstance(target, dict):
            target_id = target.get('id')
            name = (target.get('name') or target.get('full_name') or '').strip()
        elif isinstance(target, str):
            name = target.strip()

        try:
            target_id = int(target_id) if target_id not in [None, ''] else None
        except (TypeError, ValueError):
            target_id = None

        if target_id:
            user = User.query.get(target_id)
            if user:
                name = user.full_name
            else:
                target_id = None

        if not name:
            continue

        key = target_id or name.lower()
        if key in seen:
            continue
        seen.add(key)

        item = {'name': name}
        if target_id:
            item['id'] = target_id
        normalized.append(item)

    return normalized


def normalize_target_puroks(raw_puroks):
    if raw_puroks in [None, '', 'all', 'All', 'ALL']:
        return []
    if not isinstance(raw_puroks, list):
        raw_puroks = [raw_puroks]

    normalized = []
    seen = set()
    for purok in raw_puroks:
        if purok in [None, '', 'all', 'All', 'ALL']:
            continue
        try:
            value = int(purok)
        except (TypeError, ValueError):
            continue
        if value < 1 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)

    return normalized


def get_announcement_targets(announcement):
    targets = normalize_target_users(parse_json_list(announcement.target_users))
    if announcement.target_user and not any(target.get('id') == announcement.target_user for target in targets):
        user = User.query.get(announcement.target_user)
        if user:
            targets.append({'id': user.id, 'name': user.full_name})
    return targets


def get_announcement_puroks(announcement):
    puroks = normalize_target_puroks(parse_json_list(announcement.target_puroks))
    if puroks:
        return puroks
    if announcement.target_purok not in [None, '']:
        return normalize_target_puroks([announcement.target_purok])
    return []


def can_view_announcement(user, announcement):
    if not user:
        return True
    if user.role in ['bio', 'superadmin']:
        return True

    targets = get_announcement_targets(announcement)
    if targets:
        return any(
            target.get('id') == user.id or
            normalize_duplicate_key(target.get('name')) == normalize_duplicate_key(user.full_name)
            for target in targets
        )

    puroks = get_announcement_puroks(announcement)
    if puroks:
        try:
            return int(user.purok) in puroks
        except (TypeError, ValueError):
            return False

    return True


def serialize_announcement(announcement):
    targets = get_announcement_targets(announcement)
    puroks = get_announcement_puroks(announcement)
    return {
        'id': announcement.id,
        'message': announcement.message,
        'purok': announcement.target_purok,
        'target_puroks': puroks,
        'user': announcement.target_user,
        'target_users': targets,
        'target_names': [target['name'] for target in targets],
        'created_by': announcement.created_by,
        'date': serialize_utc_datetime(announcement.date_posted)
    }


def get_announcement_push_recipients(announcement):
    return [
        user for user in User.query.filter(User.role.in_(['resident', 'official']), User.is_active == True).all()
        if can_view_announcement(user, announcement)
    ]


def get_post_push_recipients(post):
    return User.query.filter(
        User.role.in_(['resident', 'official', 'bio']),
        User.is_active == True,
        User.id != post.author_id
    ).all()


def get_emergency_push_recipients(emergency):
    reporter = User.query.get(emergency.reported_by) if emergency.reported_by else None
    candidates = User.query.filter(User.role.in_(['bio', 'official']), User.is_active == True).all()
    if not reporter:
        return candidates
    return [user for user in candidates if is_within_viewer_barangay_scope(user, reporter)]


def detach_or_delete_user_records(user_id):
    authored_posts = Post.query.filter_by(author_id=user_id).all()
    for post in authored_posts:
        PostLike.query.filter_by(post_id=post.id).delete(synchronize_session=False)
        db.session.delete(post)

    PostLike.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    PushSubscription.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    WelfareDistribution.query.filter_by(resident_id=user_id).delete(synchronize_session=False)
    WelfareDistribution.query.filter_by(created_by=user_id).delete(synchronize_session=False)

    for emergency in Emergency.query.filter_by(reported_by=user_id).all():
        emergency.reported_by = None

    for summon in Summons.query.filter(
        (Summons.resident_id == user_id) | (Summons.official_id == user_id)
    ).all():
        if summon.resident_id == user_id:
            summon.resident_id = None
        if summon.official_id == user_id:
            summon.official_id = None

    for rating in Rating.query.filter_by(official_id=user_id).all():
        rating.official_id = None
    for rating in Rating.query.filter_by(rater_id=user_id).all():
        rating.rater_id = None

    for schedule in RatingSchedule.query.filter_by(updated_by=user_id).all():
        schedule.updated_by = None
    for schedule_window in RatingScheduleWindow.query.filter_by(updated_by=user_id).all():
        schedule_window.updated_by = None

    for announcement in Announcement.query.filter(
        (Announcement.created_by == user_id) | (Announcement.target_user == user_id)
    ).all():
        if announcement.created_by == user_id:
            announcement.created_by = None
        if announcement.target_user == user_id:
            announcement.target_user = None

    for announcement in Announcement.query.all():
        targets = [
            target for target in get_announcement_targets(announcement)
            if str(target.get('id')) != str(user_id)
        ]
        announcement.target_users = json.dumps(targets)
        if targets:
            announcement.target_purok = None
            announcement.target_puroks = json.dumps([])

    for event in Event.query.filter_by(created_by=user_id).all():
        event.created_by = None

    for report in FinancialReport.query.filter_by(uploaded_by=user_id).all():
        report.uploaded_by = None

    for log in HistoryLog.query.filter_by(user_id=user_id).all():
        log.user_id = None


def get_users_for_barangay(barangay_name):
    normalized_barangay = normalize_barangay_name(barangay_name)
    if not normalized_barangay:
        return []
    return [
        user for user in User.query.all()
        if normalize_barangay_name(user.barangay_name) == normalized_barangay
    ]


def wipe_barangay_records(barangay_name):
    normalized_barangay = normalize_barangay_name(barangay_name)
    barangay_users = get_users_for_barangay(barangay_name)
    user_ids = [user.id for user in barangay_users]
    if not normalized_barangay or not user_ids:
        return {'user_count': 0, 'barangay_name': barangay_name}

    user_id_set = set(user_ids)
    user_id_strings = {str(user_id) for user_id in user_ids}
    family_ids = sorted({user.family_id for user in barangay_users if user.family_id})
    post_ids = [
        post_id for (post_id,) in db.session.query(Post.id)
        .filter(Post.author_id.in_(user_ids))
        .all()
    ]
    announcement_ids = []
    for announcement in Announcement.query.all():
        target_ids = {
            str(target.get('id'))
            for target in get_announcement_targets(announcement)
            if target.get('id') not in [None, '']
        }
        if (
            announcement.created_by in user_id_set or
            announcement.target_user in user_id_set or
            target_ids.intersection(user_id_strings)
        ):
            announcement_ids.append(announcement.id)

    deletable_family_ids = []
    for family_id in family_ids:
        linked_user_ids = {
            linked_user_id for (linked_user_id,) in db.session.query(User.id)
            .filter(User.family_id == family_id)
            .all()
        }
        if linked_user_ids and linked_user_ids.issubset(user_id_set):
            deletable_family_ids.append(family_id)

    if post_ids:
        PostLike.query.filter(
            (PostLike.post_id.in_(post_ids)) | (PostLike.user_id.in_(user_ids))
        ).delete(synchronize_session=False)
    else:
        PostLike.query.filter(PostLike.user_id.in_(user_ids)).delete(synchronize_session=False)

    PushSubscription.query.filter(PushSubscription.user_id.in_(user_ids)).delete(synchronize_session=False)
    WelfareDistribution.query.filter(
        (WelfareDistribution.resident_id.in_(user_ids)) |
        (WelfareDistribution.created_by.in_(user_ids)) |
        (WelfareDistribution.family_id.in_(family_ids))
    ).delete(synchronize_session=False)

    if family_ids:
        ReliefDistribution.query.filter(ReliefDistribution.family_id.in_(family_ids)).delete(synchronize_session=False)

    Emergency.query.filter(Emergency.reported_by.in_(user_ids)).delete(synchronize_session=False)
    Summons.query.filter(
        (Summons.resident_id.in_(user_ids)) | (Summons.official_id.in_(user_ids))
    ).delete(synchronize_session=False)
    Rating.query.filter(
        (Rating.official_id.in_(user_ids)) |
        (Rating.rater_id.in_(user_ids)) |
        (Rating.family_id.in_(family_ids))
    ).delete(synchronize_session=False)

    if announcement_ids:
        Announcement.query.filter(Announcement.id.in_(announcement_ids)).delete(synchronize_session=False)

    Event.query.filter(Event.created_by.in_(user_ids)).delete(synchronize_session=False)
    FinancialReport.query.filter(FinancialReport.uploaded_by.in_(user_ids)).delete(synchronize_session=False)
    HistoryLog.query.filter(HistoryLog.user_id.in_(user_ids)).delete(synchronize_session=False)
    RatingScheduleWindow.query.filter(
        (RatingScheduleWindow.barangay_key == normalized_barangay) |
        (RatingScheduleWindow.updated_by.in_(user_ids))
    ).delete(synchronize_session=False)
    RatingSchedule.query.filter(
        (RatingSchedule.barangay_key == normalized_barangay) |
        (RatingSchedule.updated_by.in_(user_ids))
    ).delete(synchronize_session=False)

    if post_ids:
        Post.query.filter(Post.id.in_(post_ids)).delete(synchronize_session=False)

    User.query.filter(User.id.in_(user_ids)).delete(synchronize_session=False)

    if deletable_family_ids:
        Family.query.filter(Family.id.in_(deletable_family_ids)).delete(synchronize_session=False)

    return {
        'user_count': len(user_ids),
        'barangay_name': barangay_name,
    }


def get_bio_barangay_wipe_details(current_bio):
    barangay_name = (current_bio.barangay_name or '').strip() if current_bio else ''
    normalized_barangay = normalize_barangay_name(barangay_name)
    expected_confirmation = f'DELETE {barangay_name}' if barangay_name else ''
    return barangay_name, normalized_barangay, expected_confirmation


def execute_bio_barangay_wipe(current_bio, confirmation_text):
    barangay_name, normalized_barangay, expected_confirmation = get_bio_barangay_wipe_details(current_bio)
    if not normalized_barangay:
        return None, 'Your BIO account has no barangay assigned.', 400

    if normalize_barangay_name(confirmation_text) != normalize_barangay_name(expected_confirmation):
        return None, f"Type '{expected_confirmation}' exactly to continue.", 400

    try:
        wipe_summary = wipe_barangay_records(barangay_name)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Failed to wipe barangay %s', barangay_name)
        return None, 'Unable to delete the barangay page right now.', 500

    return wipe_summary, None, 200


def parse_post_mentions(raw_mentions):
    mentions = []
    for mention in parse_json_list(raw_mentions):
        if isinstance(mention, str) and mention.strip():
            mentions.append(mention.strip())
        elif isinstance(mention, dict):
            name = (mention.get('name') or mention.get('full_name') or '').strip()
            if name:
                mentions.append(name)
    return mentions


def normalize_post_mentions(raw_mentions):
    if not isinstance(raw_mentions, list):
        return []

    normalized = []
    seen = set()
    for mention in raw_mentions:
        mention_id = None
        name = ''

        if isinstance(mention, str):
            name = mention.strip()
        elif isinstance(mention, dict):
            mention_id = mention.get('id')
            name = (mention.get('name') or mention.get('full_name') or '').strip()

        if not name:
            continue

        key = mention_id if mention_id not in [None, ''] else name.lower()
        if key in seen:
            continue
        seen.add(key)

        entry = {'name': name}
        if mention_id not in [None, '']:
            entry['id'] = mention_id
        normalized.append(entry)

    return normalized


def can_view_full_profile(viewer, target):
    if not viewer or not target:
        return False
    return viewer.id == target.id or viewer.role in FULL_DIRECTORY_ROLES


def build_search_profile_fields(viewer, target):
    fields = []

    def add_field(label, value):
        if value is None or value == '':
            return
        fields.append({'label': label, 'value': str(value)})

    if target.position:
        add_field('Position', target.position)
    if target.purok is not None:
        add_field('Purok', target.purok)
    if target.barangay_name:
        add_field('Barangay', target.barangay_name)

    if can_view_full_profile(viewer, target):
        add_field('Username', target.username)
        if target.birthdate:
            add_field('Birthdate', target.birthdate.isoformat())
            add_field('Age', get_age(target.birthdate))
        add_field('Birthplace', target.birthplace)
        add_field('Employment Status', target.employment_status)
        add_field("Mother's Name", target.mother_name)
        add_field("Father's Name", target.father_name)
        if target.family and target.family.class_type:
            add_field('Family Class', target.family.class_type)
        add_field('Monthly Income', f"PHP {target.monthly_income:,.2f}")

    return fields


def serialize_search_profile(viewer, target):
    return {
        'id': target.id,
        'full_name': target.full_name,
        'role': target.role,
        'position': target.position,
        'pic_url': target.pic_url,
        'access_level': 'full' if can_view_full_profile(viewer, target) else 'limited',
        'fields': build_search_profile_fields(viewer, target)
    }


def serialize_search_post(post, match_reasons):
    return {
        'id': post.id,
        'content': post.content,
        'author_name': post.author.full_name if post.author else 'Unknown',
        'author_position': official_position_label(post.author),
        'author_role': post.author.role if post.author else None,
        'author_pic': post.author.pic_url if post.author else None,
        'timestamp': serialize_utc_datetime(post.timestamp),
        'image_url': post.image_url,
        'media_urls': parse_json_list(post.media_urls),
        'mentions': parse_post_mentions(post.mentions),
        'location': post.location,
        'match_reasons': match_reasons
    }


def initials_for_name(name):
    cleaned = re.sub(r'\b(hon|honorable)\.?\b', '', name or '', flags=re.IGNORECASE)
    parts = re.findall(r'[A-Za-z0-9]+', cleaned)
    if not parts:
        return 'NA'
    return ''.join(part[0].upper() for part in parts[:3])


def rating_score(rating):
    values = [
        rating.responsiveness,
        rating.fairness,
        rating.service_quality,
        rating.community_involvement,
    ]
    return sum(values) / len(values)


def resolve_rating_rater(rating):
    if rating.rater_id:
        return User.query.get(rating.rater_id)
    if rating.family and rating.family.users:
        return rating.family.users[0]
    return None


def build_rating_summary(barangay_name, year=None):
    normalized_barangay = normalize_barangay_name(barangay_name)
    year = year or ph_year()
    officials = [
        official for official in User.query.filter(
            (User.role == 'official') |
            ((User.role == 'bio') & (User.is_approved == True))
        ).all()
        if not normalized_barangay or normalize_barangay_name(official.barangay_name) == normalized_barangay
    ]

    summary = []
    for official in officials:
        ratings = Rating.query.filter_by(official_id=official.id, year=year).all()
        total_score = 0.0
        purok_totals = {}

        for rating in ratings:
            score = rating_score(rating)
            total_score += score
            rater = resolve_rating_rater(rating)
            purok = str(rater.purok) if rater and rater.purok not in [None, ''] else 'Unassigned'
            if purok not in purok_totals:
                purok_totals[purok] = {'purok': purok, 'total_votes': 0, 'score_total': 0.0}
            purok_totals[purok]['total_votes'] += 1
            purok_totals[purok]['score_total'] += score

        total_votes = len(ratings)
        average_rating = round(total_score / total_votes, 2) if total_votes else 0
        ratings_by_purok = []
        for item in purok_totals.values():
            ratings_by_purok.append({
                'purok': item['purok'],
                'total_votes': item['total_votes'],
                'average_rating': round(item['score_total'] / item['total_votes'], 2) if item['total_votes'] else 0
            })

        ratings_by_purok.sort(key=lambda item: (item['purok'] == 'Unassigned', str(item['purok'])))
        summary.append({
            'official_id': official.id,
            'full_name': official.full_name,
            'initials': initials_for_name(official.full_name),
            'position': official_position_label(official),
            'role': official.role,
            'total_votes': total_votes,
            'average_rating': average_rating,
            'ratings_by_purok': ratings_by_purok,
        })

    summary.sort(key=lambda item: (-item['average_rating'], -item['total_votes'], item['full_name'].lower()))
    return {
        'year': year,
        'barangay_name': barangay_name,
        'officials': summary
    }

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.form if request.form else request.json
        user = User.query.filter_by(username=data.get('username')).first()
        if user and check_password_hash(user.password_hash, data.get('password')):
            if not user.is_active:
                return jsonify({'success': False, 'error': 'Account Deactivated. Please contact Brgy Hall.'}), 403

            # Check for ban
            now = utc_now()
            if user.banned_until and user.banned_until > now:
                remaining = user.banned_until - now
                msg = "You are requested to go to the Brgy Hall for your explanation and give your consequences."
                return jsonify({
                    'success': False, 
                    'error': 'Banned', 
                    'message': msg,
                    'banned_until': serialize_utc_datetime(user.banned_until),
                    'remaining_seconds': int(remaining.total_seconds())
                }), 403

            if user.role == 'bio' and not user.is_approved:
                return jsonify({'success': False, 'error': 'Account pending Superadmin approval'}), 401
            session['user_id'] = user.id
            session['role'] = user.role
            session['brgy'] = user.barangay_name
            session['position'] = user.position
            session['username'] = user.username
            session.permanent = True # Persistent Session
            return jsonify({'success': True, 'role': user.role})
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    return render_template('login.html')

@main.route('/api/bio/member', methods=['POST'])
def add_member():
    if session.get('role') != 'bio': return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    requested_role = (data.get('role') or 'resident').strip().lower()
    actual_role = 'bio' if requested_role == 'bio' else ('official' if 'official' in requested_role else 'resident')
    
    fam_id = data.get('family_id')
    inc = float(data.get('monthly_income', 0.0)) if data.get('monthly_income') else 0.0
    c_type = calculate_class(inc)

    if actual_role == 'bio':
        fam_id = None
    elif not fam_id:
        f = Family(class_type=c_type, size=int(data.get('family_size', 1) if data.get('family_size') else 1))
        db.session.add(f)
        db.session.commit()
        fam_id = f.id
    else:
        f = Family.query.get(fam_id)
        if f:
            f.class_type = c_type
            db.session.commit()
        
    bd = datetime.strptime(data.get('birthdate'), '%Y-%m-%d').date() if data.get('birthdate') else None
    p_hash = generate_password_hash(data['password'])
    bio = User.query.get(session['user_id'])
    full_name = data['full_name']
    if actual_role == 'official' and not full_name.startswith('Hon. '):
        full_name = 'Hon. ' + full_name

    u = User(
        username=data['username'], password_hash=p_hash, full_name=full_name, 
        role=actual_role, position=data.get('position'), purok=data.get('purok'), 
        family_id=fam_id, birthdate=bd, birthplace=data.get('birthplace'), 
        monthly_income=float(data.get('monthly_income', 0.0)) if data.get('monthly_income') else 0.0, 
        mother_name=data.get('mother_name'), father_name=data.get('father_name'),
        employment_status=data.get('employment_status'), lat=data.get('lat'), lng=data.get('lng'),
        pic_url=data.get('pic_url'),
        is_rater=True, barangay_name=bio.barangay_name,
        is_approved=True
    )
    db.session.add(u)
    db.session.commit()
    log_action(session.get('user_id'), f"Registered a new member: {data['full_name']} ({actual_role})")
    return jsonify({'success': True, 'user_id': u.id, 'family_id': fam_id})

@main.route('/api/upload_image', methods=['POST'])
def upload_image():
    if 'file' not in request.files: return jsonify({'error':'No file part'}), 400
    f = request.files['file']
    if f.filename == '': return jsonify({'error':'No selected file'}), 400
    if f:
        ext = f.filename.rsplit('.', 1)[1].lower() if '.' in f.filename else 'jpg'
        fname = f"{uuid.uuid4().hex}.{ext}"
        up_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads')
        os.makedirs(up_dir, exist_ok=True)
        f.save(os.path.join(up_dir, fname))
        return jsonify({'success': True, 'url': url_for('static', filename=f"uploads/{fname}")})

@main.route('/api/bio/member/<int:uid>', methods=['PUT', 'DELETE'])
def edit_member(uid):
    if session.get('role') != 'bio': return jsonify({'error':'Unauthorized'}), 401
    u = User.query.get(uid)
    if not u: return jsonify({'error':'User not found'}), 404
    current_bio = User.query.get(session['user_id'])
    if not current_bio:
        session.clear()
        return jsonify({'error': 'Unauthorized'}), 401
    
    if request.method == 'DELETE':
        deleting_self = u.id == current_bio.id
        if not deleting_self and u.role not in ['resident', 'official']:
            return jsonify({'error': 'BIO can only delete resident and official accounts.'}), 400
        if (
            not deleting_self and
            u.barangay_name and current_bio.barangay_name and
            normalize_barangay_name(u.barangay_name) != normalize_barangay_name(current_bio.barangay_name)
        ):
            return jsonify({'error': 'You can only delete accounts from your barangay.'}), 403

        deleted_name = u.full_name
        deleted_role = u.role
        try:
            detach_or_delete_user_records(u.id)
            db.session.delete(u)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Failed to delete member account %s', uid)
            return jsonify({'error': 'Unable to delete this account right now.'}), 500

        if deleting_self:
            session.clear()
            return jsonify({
                'success': True,
                'deleted_self': True,
                'redirect_url': url_for('main.login')
            })

        log_action(current_bio.id, f"Deleted {deleted_role} account: {deleted_name}")
        return jsonify({'success': True})
        
    data = request.json
    if data.get('full_name'): 
        u.full_name = data['full_name']
        if u.role == 'official' and not u.full_name.startswith('Hon. '):
            u.full_name = 'Hon. ' + u.full_name
    if data.get('username'): u.username = data['username']
    if data.get('password'): u.password_hash = generate_password_hash(data['password'])
    if data.get('role'):
        requested_role = (data['role'] or '').strip().lower()
        if requested_role == 'bio':
            if u.role not in ['official', 'bio']:
                return jsonify({'error': 'Only an official can be assigned as an additional BIO.'}), 400
            if normalize_barangay_name(u.barangay_name) != normalize_barangay_name(current_bio.barangay_name):
                return jsonify({'error': 'Only officials from your barangay can be assigned as BIO.'}), 400
            u.role = 'bio'
            u.is_approved = True
            u.barangay_name = current_bio.barangay_name
        else:
            u.role = 'official' if 'official' in requested_role else 'resident'
        if u.role == 'official' and u.full_name and not u.full_name.startswith('Hon. '):
            u.full_name = 'Hon. ' + u.full_name
    if 'position' in data: u.position = data['position']
    if data.get('birthdate'): u.birthdate = datetime.strptime(data['birthdate'], '%Y-%m-%d').date()
    if 'birthplace' in data: u.birthplace = data['birthplace']
    if 'purok' in data: u.purok = data['purok']
    if 'employment_status' in data: u.employment_status = data['employment_status']
    if 'mother_name' in data: u.mother_name = data['mother_name']
    if 'father_name' in data: u.father_name = data['father_name']
    if 'lat' in data: u.lat = data['lat']
    if 'lng' in data: u.lng = data['lng']
    if 'pic_url' in data: u.pic_url = data['pic_url']
    if 'monthly_income' in data: 
        u.monthly_income = float(data['monthly_income']) if data['monthly_income'] not in [None, ''] else 0.0
        if u.family:
            u.family.class_type = calculate_class(u.monthly_income)
    
    db.session.commit()
    return jsonify({'success': True})


@main.route('/api/bio/barangay/wipe', methods=['POST'])
def wipe_current_bio_barangay():
    if session.get('role') != 'bio':
        return jsonify({'error': 'Unauthorized'}), 401

    current_bio = User.query.get(session.get('user_id'))
    if not current_bio:
        session.clear()
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    confirmation_text = (data.get('confirmation_text') or '').strip()
    wipe_summary, error_message, status_code = execute_bio_barangay_wipe(current_bio, confirmation_text)
    if error_message:
        return jsonify({'error': error_message}), status_code

    session.clear()
    return jsonify({
        'success': True,
        'deleted_self': True,
        'deleted_barangay': True,
        'wiped_barangay_name': wipe_summary['barangay_name'],
        'deleted_user_count': wipe_summary['user_count'],
        'redirect_url': url_for('main.login')
    })


@main.route('/bio/barangay/wipe', methods=['GET', 'POST'])
def wipe_current_bio_barangay_page():
    if session.get('role') != 'bio':
        return redirect(url_for('main.login'))

    current_bio = User.query.get(session.get('user_id'))
    if not current_bio:
        session.clear()
        return redirect(url_for('main.login'))

    barangay_name, normalized_barangay, expected_confirmation = get_bio_barangay_wipe_details(current_bio)
    error_message = ''

    if request.method == 'POST':
        confirmation_text = (request.form.get('confirmation_text') or '').strip()
        wipe_summary, error_message, status_code = execute_bio_barangay_wipe(current_bio, confirmation_text)
        if error_message:
            return render_template(
                'bio_wipe_confirmation.html',
                user=current_bio,
                barangay_name=barangay_name,
                expected_confirmation=expected_confirmation,
                error_message=error_message
            ), status_code

        session.clear()
        return redirect(url_for('main.login'))

    if not normalized_barangay:
        error_message = 'Your BIO account has no barangay assigned.'
        status_code = 400
    else:
        status_code = 200

    return render_template(
        'bio_wipe_confirmation.html',
        user=current_bio,
        barangay_name=barangay_name,
        expected_confirmation=expected_confirmation,
        error_message=error_message
    ), status_code

@main.route('/api/residents', methods=['GET'])
def get_residents():
    user = get_session_user()
    if not user: return jsonify([])
    residents = filter_users_to_viewer_barangay(user, User.query.filter(User.role == 'resident').all())
    out = []

    for r in residents:
        base = {'id': r.id, 'full_name': r.full_name, 'purok': r.purok, 'family_id': r.family_id, 'age': get_age(r.birthdate) or 'N/A', 'birthplace': r.birthplace}
        if user.role in ['bio', 'official', 'superadmin'] or user.family_id == r.family_id:
            base['monthly_income'] = r.monthly_income
        out.append(base)
    return jsonify(out)

@main.route('/api/members', methods=['GET'])
def get_members():
    user = get_session_user()
    if not user: return jsonify([])
    
    # Exclude officials from general member list
    users = filter_users_to_viewer_barangay(user, User.query.filter(User.role == 'resident').all())
    out = []
    
    now = utc_now()
    for u in users:
        base = {
            'id': u.id, 'full_name': u.full_name, 'role': u.role, 'username': u.username,
            'lat': u.lat, 'lng': u.lng, 'pic_url': u.pic_url, 'position': u.position
        }
        
        # Ban data
        if u.banned_until and u.banned_until > now:
            base['is_banned'] = True
            base['ban_remaining'] = int((u.banned_until - now).total_seconds())
        else:
            base['is_banned'] = False

        base['class_type'] = u.family.class_type if u.family else 'N/A'
        base['is_active'] = u.is_active

        if user.role in ['bio', 'official', 'superadmin']:
            base['purok'] = u.purok
            base['monthly_income'] = u.monthly_income
            base['birthdate'] = str(u.birthdate) if u.birthdate else None
            base['birthplace'] = u.birthplace
            base['position'] = u.position
            base['mother_name'] = u.mother_name
            base['father_name'] = u.father_name
            base['employment_status'] = u.employment_status
        elif user.id != u.id:
            # Mask data for standard resident
            base['username'] = 'Hidden'
            base['purok'] = u.purok
        out.append(base)
    return jsonify(out)

@main.route('/api/officials', methods=['GET'])
def get_officials():
    viewer = get_session_user()
    if not viewer: return jsonify([])
    officials = filter_users_to_viewer_barangay(viewer, User.query.filter(
        (User.role == 'official') |
        ((User.role == 'bio') & (User.is_approved == True))
    ).all())
    out = []
    for o in officials:
        base = {
            'id': o.id, 'full_name': o.full_name, 'role': o.role, 'position': o.position, 
            'pic_url': o.pic_url,
            'lat': o.lat,
            'lng': o.lng
        }
        if can_view_full_profile(viewer, o):
            base.update({
                'username': o.username,
                'purok': o.purok,
                'birthdate': str(o.birthdate) if o.birthdate else None,
                'birthplace': o.birthplace,
                'employment_status': o.employment_status,
                'mother_name': o.mother_name,
                'father_name': o.father_name,
                'monthly_income': o.monthly_income
            })
        out.append(base)
    return jsonify(out)

@main.route('/api/search', methods=['GET'])
def search_directory():
    viewer = get_session_user()
    if not viewer:
        return jsonify({'profiles': [], 'posts': []})

    query = (request.args.get('q') or '').strip()
    if not query:
        return jsonify({'profiles': [], 'posts': []})

    users = User.query.filter(
        User.role.in_(SEARCHABLE_DIRECTORY_ROLES),
        User.full_name.ilike(f'%{query}%')
    ).order_by(User.full_name.asc()).limit(12).all()

    query_lower = query.lower()
    posts = Post.query.options(joinedload(Post.author)).order_by(Post.timestamp.desc()).all()
    matched_posts = []

    for post in posts:
        match_reasons = []
        author_name = post.author.full_name if post.author else ''
        mention_names = parse_post_mentions(post.mentions)
        content = post.content or ''
        location = post.location or ''

        if query_lower in author_name.lower():
            match_reasons.append('Posted by this person')
        if query_lower in content.lower():
            match_reasons.append('Name appears in the post')
        if any(query_lower in mention.lower() for mention in mention_names):
            match_reasons.append('Tagged or mentioned')
        if query_lower in location.lower():
            match_reasons.append('Location match')

        if match_reasons:
            matched_posts.append(serialize_search_post(post, match_reasons))
        if len(matched_posts) >= 12:
            break

    return jsonify({
        'profiles': [serialize_search_profile(viewer, user) for user in users],
        'posts': matched_posts
    })

@main.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    viewer = get_session_user()
    if not viewer:
        return jsonify({'members': 0, 'officials': 0, 'incidents': 0, 'health': 0, 'posts': 0})

    scoped_users = filter_users_to_viewer_barangay(viewer, User.query.all())
    scoped_user_ids = {user.id for user in scoped_users}
    scoped_emergencies = [
        emergency for emergency in Emergency.query.all()
        if emergency.reported_by in scoped_user_ids
    ]

    member_count = sum(1 for user in scoped_users if user.role == 'resident')
    official_count = sum(
        1 for user in scoped_users
        if user.role == 'official' or (user.role == 'bio' and user.is_approved)
    )
    incident_count = sum(1 for emergency in scoped_emergencies if emergency.type == 'accident')
    health_count = sum(1 for emergency in scoped_emergencies if emergency.type == 'health')
    post_count = sum(1 for post in Post.query.all() if post.author_id in scoped_user_ids)
    
    return jsonify({
        'members': member_count,
        'officials': official_count,
        'incidents': incident_count,
        'health': health_count,
        'posts': post_count
    })

@main.route('/register_bio', methods=['POST'])
def register_bio():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    full_name = (data.get('full_name') or '').strip()
    password = data.get('password') or ''
    barangay_name = (data.get('barangay_name') or '').strip()
    position = (data.get('position') or '').strip()
    if not username or not password or not full_name or not barangay_name or not position:
        return jsonify({'success': False, 'error': 'Fill in all BIO registration fields first.', 'error_code': 'validation_error'}), 400
    if not barangay_name:
        return jsonify({'success': False, 'error': 'Barangay name is required', 'error_code': 'validation_error'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'error': 'Username taken', 'error_code': 'username_taken'}), 400
    conflict = find_barangay_bio_conflict(barangay_name)
    if conflict:
        return jsonify({'success': False, 'error': conflict, 'error_code': 'bio_conflict'}), 400
    identity_conflict = find_bio_identity_conflict(full_name, position)
    if identity_conflict:
        return jsonify({'success': False, 'error': identity_conflict, 'error_code': 'bio_conflict'}), 400
    p_hash = generate_password_hash(password)
    user = User(
        username=username, password_hash=p_hash, full_name=full_name, 
        role='bio', is_approved=False, barangay_name=barangay_name,
        position=position
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'success': True})

@main.route('/logout')
def logout():
    user_id = session.get('user_id')
    if user_id:
        PushSubscription.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        db.session.commit()
    session.clear()
    return redirect(url_for('main.login'))

@main.route('/api/session/refresh', methods=['POST'])
def refresh_session():
    session.modified = True 
    return jsonify({'success': True})


@main.route('/service-worker.js')
def notification_service_worker():
    response = make_response(send_from_directory('static', 'service-worker.js'))
    response.headers['Content-Type'] = 'application/javascript; charset=utf-8'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Service-Worker-Allowed'] = '/'
    return response


@main.route('/api/push/public-key')
def push_public_key():
    available = is_web_push_configured()
    return jsonify({
        'available': available,
        'publicKey': current_app.config.get('WEB_PUSH_PUBLIC_KEY') if available else '',
        'reason': '' if available else get_web_push_unavailable_reason(),
    })


@main.route('/api/push/subscribe', methods=['POST'])
def subscribe_push_notifications():
    user = get_session_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    if not is_web_push_configured():
        return jsonify({'error': get_web_push_unavailable_reason() or 'Web push is not configured.'}), 503

    data = request.json or {}
    endpoint = (data.get('endpoint') or '').strip()
    keys = data.get('keys') or {}
    p256dh = (keys.get('p256dh') or '').strip()
    auth = (keys.get('auth') or '').strip()

    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'Invalid push subscription payload.'}), 400

    record = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if not record:
        record = PushSubscription(
            user_id=user.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
        )
        db.session.add(record)
    else:
        record.user_id = user.id
        record.p256dh = p256dh
        record.auth = auth

    db.session.commit()
    return jsonify({'success': True})


@main.route('/api/push/unsubscribe', methods=['POST'])
def unsubscribe_push_notifications():
    user = get_session_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json or {}
    endpoint = (data.get('endpoint') or '').strip()

    query = PushSubscription.query.filter_by(user_id=user.id)
    if endpoint:
        query = query.filter_by(endpoint=endpoint)
    query.delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True})

@main.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('main.login'))
    if user.role == 'superadmin':
        return render_template('superadmin_dashboard.html', user=user)
    elif user.role == 'bio':
        return render_template('bio_dashboard.html', user=user)
    elif user.role == 'official':
        return render_template('official_dashboard.html', user=user)
    else:
        return render_template('resident_dashboard.html', user=user)

# === SUPERADMIN ===
@main.route('/api/superadmin/barangays', methods=['GET'])
def superadmin_barangays():
    return jsonify(build_superadmin_barangay_overview())


@main.route('/api/superadmin/bios', methods=['GET', 'POST'])
def handle_bios():
    if request.method == 'GET':
        bios = User.query.filter_by(role='bio', is_approved=False).all()
        return jsonify([{'id':b.id, 'username':b.username, 'full_name':b.full_name, 'barangay_name': b.barangay_name} for b in bios])
    
    data = request.json
    bio = User.query.get(data['id'])
    if data.get('action') == 'approve':
        bio.is_approved = True
    else:
        db.session.delete(bio)
    db.session.commit()
    return jsonify({'success': True})

# === EVENTS & ACHIEVEMENTS ===
@main.route('/api/events', methods=['GET', 'POST'])
def manage_events():
    if request.method == 'GET':
        events = Event.query.order_by(Event.date.desc()).all()
        return jsonify([{'id':e.id, 'title':e.title, 'desc':e.description, 'date':serialize_ph_datetime(e.date), 'type':e.type} for e in events])
    
    data = request.json
    ev = Event(title=data['title'], description=data.get('description'), type=data.get('type','event'), date=datetime.fromisoformat(data['date']), created_by=session['user_id'])
    db.session.add(ev)
    db.session.commit()
    return jsonify({'success': True})

# === BIO Controls ===
@main.route('/api/finance', methods=['POST', 'GET'])
def finance():
    if request.method == 'GET':
        reports = FinancialReport.query.order_by(FinancialReport.year.desc(), FinancialReport.month.desc()).all()
        return jsonify([{ 'id': r.id, 'month': r.month, 'year': r.year, 'total': r.total_funds, 'relief': r.relief_distribution, 'expenses': r.project_expenses, 'summary': r.ai_summary } for r in reports])
    
    data = request.json
    summary = generate_financial_summary(data['month'], data['year'], data['total_funds'], data['relief_distribution'], data['project_expenses'])
    report = FinancialReport(month=data['month'], year=data['year'], total_funds=data['total_funds'], relief_distribution=data['relief_distribution'], project_expenses=data['project_expenses'], ai_summary=summary, uploaded_by=session['user_id'])
    db.session.add(report)
    db.session.commit()
    return jsonify({'success': True, 'summary': summary})

@main.route('/api/relief/calculate', methods=['POST'])
def calculate_relief():
    user = get_session_user()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401
    if user.role not in ['bio', 'official', 'superadmin']:
        return jsonify({'error': 'Only barangay staff can run the AI relief calculator.'}), 403

    data = request.json or {}
    budget = parse_float(data.get('budget'), 0.0)
    if budget <= 0:
        return jsonify({'error': 'Enter a valid positive budget first.'}), 400

    residents = filter_users_to_viewer_barangay(
        user,
        User.query.options(joinedload(User.family)).filter(User.role == 'resident').all()
    )
    families = []
    seen_family_ids = set()
    for resident in residents:
        family = resident.family
        if not family or family.id in seen_family_ids:
            continue
        seen_family_ids.add(family.id)
        families.append(family)

    all_users = User.query.all()
    users_by_id = {item.id: item for item in all_users}
    emergencies = filter_emergencies_to_viewer_barangay(user, Emergency.query.all(), users_by_id=users_by_id)
    allocation_result = calculate_relief_allocation(
        budget,
        families,
        residents=residents,
        emergencies=emergencies,
        barangay_name=user.barangay_name,
        iteration=data.get('iteration', 0),
    )
    return jsonify({'success': True, **allocation_result})


@main.route('/api/welfare/distributions', methods=['GET', 'POST'])
def welfare_distributions():
    user = get_session_user()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    if request.method == 'GET':
        if user.role not in WELFARE_MANAGER_ROLES and user.role != 'resident':
            return jsonify({'error': 'Unauthorized'}), 403

        distributions = WelfareDistribution.query.options(
            joinedload(WelfareDistribution.resident).joinedload(User.family),
            joinedload(WelfareDistribution.creator)
        ).all()

        if user.role == 'resident':
            distributions = [row for row in distributions if row.resident_id == user.id]
        elif user.role != 'superadmin':
            distributions = [
                row for row in distributions
                if row.resident and belongs_to_same_barangay(user, row.resident)
            ]

        raw_status_filter = request.args.get('status')
        status_filter = normalize_welfare_status(raw_status_filter) if raw_status_filter not in [None, ''] else None
        if status_filter:
            distributions = [row for row in distributions if row.status == status_filter]

        query = (request.args.get('q') or '').strip().lower()
        if query:
            distributions = [
                row for row in distributions
                if query in (row.reference_code or '').lower()
                or query in (row.assistance_type or '').lower()
                or query in (row.program_name or '').lower()
                or (row.resident and query in (row.resident.full_name or '').lower())
            ]

        distributions = sorted(
            distributions,
            key=lambda row: (row.distributed_on or date.min, row.created_at or datetime.min),
            reverse=True
        )

        return jsonify({
            'success': True,
            'records': [serialize_welfare_distribution(row, user) for row in distributions],
            'summary': build_welfare_summary(distributions),
            'available_statuses': list(WELFARE_STATUSES),
        })

    if not can_manage_welfare(user):
        return jsonify({'error': 'Only BIO and barangay officials can manage welfare records.'}), 403

    data = request.json or {}
    resident_ids = parse_int_list(data.get('resident_ids'))
    single_resident_id = data.get('resident_id')
    if not resident_ids and single_resident_id not in [None, '']:
        try:
            resident_ids = [int(single_resident_id)]
        except (TypeError, ValueError):
            resident_ids = []

    if not resident_ids:
        return jsonify({'error': 'Select at least one valid resident beneficiary.'}), 400

    residents = User.query.options(joinedload(User.family)).filter(User.id.in_(resident_ids)).all()
    residents_by_id = {resident.id: resident for resident in residents}
    ordered_residents = [residents_by_id.get(resident_id) for resident_id in resident_ids]

    if any(not resident or resident.role != 'resident' for resident in ordered_residents):
        return jsonify({'error': 'Select valid resident beneficiaries only.'}), 400
    if any(not belongs_to_same_barangay(user, resident) for resident in ordered_residents):
        return jsonify({'error': 'You can only record welfare assistance for residents in your barangay.'}), 403

    assistance_type = (data.get('assistance_type') or '').strip()
    if not assistance_type:
        return jsonify({'error': 'Assistance type is required.'}), 400

    status = normalize_welfare_status(data.get('status'))
    if not status:
        return jsonify({'error': 'Select a valid welfare status.'}), 400

    distributed_on_raw = data.get('distributed_on')
    distributed_on = parse_schedule_date(distributed_on_raw)
    if distributed_on_raw not in [None, ''] and not distributed_on:
        return jsonify({'error': 'Enter a valid distribution date.'}), 400

    amount = parse_float(data.get('amount'), 0.0)
    quantity = parse_float(data.get('quantity'), 1.0)
    if amount < 0:
        return jsonify({'error': 'Amount cannot be negative.'}), 400
    if quantity < 0:
        return jsonify({'error': 'Quantity cannot be negative.'}), 400

    reference_codes, reference_error = build_welfare_reference_codes(data.get('reference_code'), len(ordered_residents))
    if reference_error:
        return jsonify({'error': reference_error}), 400

    program_name = (data.get('program_name') or '').strip() or None
    unit = (data.get('unit') or '').strip() or None
    source_funds = (data.get('source_funds') or '').strip() or None
    notes = (data.get('notes') or '').strip() or None

    created_records = []
    for resident, reference_code in zip(ordered_residents, reference_codes):
        record = WelfareDistribution(
            resident_id=resident.id,
            family_id=resident.family_id,
            assistance_type=assistance_type,
            program_name=program_name,
            reference_code=reference_code,
            amount=amount,
            quantity=quantity,
            unit=unit,
            status=status,
            source_funds=source_funds,
            distributed_on=distributed_on,
            notes=notes,
            created_by=user.id,
        )

        if record.status == 'released' and not record.distributed_on:
            record.distributed_on = ph_today()

        db.session.add(record)
        sync_family_aid_totals(None, None, 0.0, record.family_id, record.status, record.amount)
        created_records.append(record)

    db.session.commit()
    resident_names = ', '.join(resident.full_name for resident in ordered_residents[:3])
    if len(ordered_residents) > 3:
        resident_names += f" and {len(ordered_residents) - 3} more"
    log_action(
        user.id,
        f"Recorded welfare assistance for {len(ordered_residents)} resident(s): {assistance_type} ({status}) for {resident_names}."
    )
    return jsonify({
        'success': True,
        'created_count': len(created_records),
        'distributions': [serialize_welfare_distribution(record, user) for record in created_records],
        'distribution': serialize_welfare_distribution(created_records[0], user) if len(created_records) == 1 else None,
    })


@main.route('/api/welfare/distributions/<int:distribution_id>', methods=['PUT'])
def update_welfare_distribution(distribution_id):
    user = get_session_user()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401
    if not can_manage_welfare(user):
        return jsonify({'error': 'Only BIO and barangay officials can update welfare records.'}), 403

    record = WelfareDistribution.query.options(
        joinedload(WelfareDistribution.resident).joinedload(User.family),
        joinedload(WelfareDistribution.creator)
    ).get_or_404(distribution_id)

    if record.resident and not belongs_to_same_barangay(user, record.resident):
        return jsonify({'error': 'You can only update welfare records for residents in your barangay.'}), 403

    old_family_id = record.family_id
    old_status = record.status
    old_amount = record.amount

    data = request.json or {}

    if 'resident_id' in data:
        resident = User.query.options(joinedload(User.family)).get(data.get('resident_id'))
        if not resident or resident.role != 'resident':
            return jsonify({'error': 'Select a valid resident beneficiary.'}), 400
        if not belongs_to_same_barangay(user, resident):
            return jsonify({'error': 'You can only assign welfare records to residents in your barangay.'}), 403
        record.resident = resident
        record.resident_id = resident.id
        record.family_id = resident.family_id

    if 'assistance_type' in data:
        assistance_type = (data.get('assistance_type') or '').strip()
        if not assistance_type:
            return jsonify({'error': 'Assistance type is required.'}), 400
        record.assistance_type = assistance_type

    if 'program_name' in data:
        record.program_name = (data.get('program_name') or '').strip() or None

    if 'reference_code' in data:
        reference_code = (data.get('reference_code') or '').strip().upper()
        if not reference_code:
            return jsonify({'error': 'Reference code is required.'}), 400
        existing = WelfareDistribution.query.filter_by(reference_code=reference_code).first()
        if existing and existing.id != record.id:
            return jsonify({'error': 'Reference code already exists. Use a unique value.'}), 400
        record.reference_code = reference_code

    if 'amount' in data:
        amount = parse_float(data.get('amount'), 0.0)
        if amount < 0:
            return jsonify({'error': 'Amount cannot be negative.'}), 400
        record.amount = amount

    if 'quantity' in data:
        quantity = parse_float(data.get('quantity'), 1.0)
        if quantity < 0:
            return jsonify({'error': 'Quantity cannot be negative.'}), 400
        record.quantity = quantity

    if 'unit' in data:
        record.unit = (data.get('unit') or '').strip() or None

    if 'status' in data:
        status = normalize_welfare_status(data.get('status'))
        if not status:
            return jsonify({'error': 'Select a valid welfare status.'}), 400
        record.status = status

    if 'source_funds' in data:
        record.source_funds = (data.get('source_funds') or '').strip() or None

    if 'distributed_on' in data:
        distributed_on_raw = data.get('distributed_on')
        distributed_on = parse_schedule_date(distributed_on_raw)
        if distributed_on_raw not in [None, ''] and not distributed_on:
            return jsonify({'error': 'Enter a valid distribution date.'}), 400
        record.distributed_on = distributed_on

    if 'notes' in data:
        record.notes = (data.get('notes') or '').strip() or None

    if record.status == 'released' and not record.distributed_on:
        record.distributed_on = ph_today()

    sync_family_aid_totals(old_family_id, old_status, old_amount, record.family_id, record.status, record.amount)
    db.session.commit()
    log_action(user.id, f"Updated welfare record {record.reference_code} for {record.resident.full_name if record.resident else 'resident'}.")
    return jsonify({'success': True, 'distribution': serialize_welfare_distribution(record, user)})

@main.route('/api/announcements', methods=['POST', 'GET'])
def announcements():
    if request.method == 'GET':
        user_id = session.get('user_id')
        user = User.query.get(user_id) if user_id else None

        anns = Announcement.query.order_by(Announcement.date_posted.desc()).all()
        visible = [announcement for announcement in anns if can_view_announcement(user, announcement)]
        return jsonify([serialize_announcement(announcement) for announcement in visible[:20]])
    
    if session.get('role') != 'bio':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json or {}
    targets = normalize_target_users(data.get('target_users', []))
    puroks = [] if targets else normalize_target_puroks(data.get('target_puroks', data.get('target_purok')))
    legacy_target = targets[0]['id'] if len(targets) == 1 and targets[0].get('id') else None
    ann = Announcement(
        message=data['message'],
        target_purok=puroks[0] if len(puroks) == 1 else None,
        target_puroks=json.dumps(puroks),
        target_user=legacy_target,
        target_users=json.dumps(targets),
        created_by=session['user_id']
    )
    db.session.add(ann)
    db.session.commit()
    recipients = get_announcement_push_recipients(ann)
    snippet = (ann.message or '').strip().replace('\n', ' ')
    send_push_notifications(
        recipients,
        'iBarangay Announcement',
        snippet[:140] or 'New barangay announcement received.',
        event_key='announcement',
        url_path=url_for('main.dashboard', tab='notification'),
        tag=f'ibarangay-announcement-{ann.id}',
        require_interaction=True,
    )
    return jsonify({'success': True, 'announcement': serialize_announcement(ann)})


@main.route('/api/announcements/<int:announcement_id>', methods=['PUT', 'DELETE'])
def manage_announcement(announcement_id):
    if session.get('role') != 'bio':
        return jsonify({'error': 'Unauthorized'}), 401

    announcement = Announcement.query.get_or_404(announcement_id)
    if announcement.created_by and announcement.created_by != session.get('user_id'):
        return jsonify({'error': 'You can only edit announcements you created.'}), 403

    if request.method == 'DELETE':
        db.session.delete(announcement)
        db.session.commit()
        return jsonify({'success': True})

    data = request.json or {}
    targets = normalize_target_users(data.get('target_users', []))
    puroks = [] if targets else normalize_target_puroks(data.get('target_puroks', data.get('target_purok')))
    announcement.message = data.get('message', announcement.message)
    announcement.target_purok = puroks[0] if len(puroks) == 1 else None
    announcement.target_puroks = json.dumps(puroks)
    announcement.target_user = targets[0]['id'] if len(targets) == 1 and targets[0].get('id') else None
    announcement.target_users = json.dumps(targets)
    db.session.commit()
    return jsonify({'success': True, 'announcement': serialize_announcement(announcement)})

import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@main.route('/api/upload_media', methods=['POST'])
def upload_media():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'}), 400
    if file:
        filename = secure_filename(f"{utc_now().timestamp()}_{file.filename}")
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        return jsonify({'success': True, 'url': f'/static/uploads/{filename}'})
import json
@main.route('/api/posts', methods=['GET', 'POST'])
def handle_posts():
    if request.method == 'GET':
        posts = Post.query.options(joinedload(Post.author)).order_by(Post.timestamp.desc()).limit(20).all()
        user_id = session.get('user_id')
        
        return jsonify([{
            'id': p.id, 
            'author_id': p.author_id,
            'content': p.content, 
            'author_name': p.author.full_name if p.author else "Unknown", 
            'author_position': official_position_label(p.author),
            'author_role': p.author.role if p.author else None,
            'author_pic': p.author.pic_url if p.author else None,
            'timestamp': serialize_utc_datetime(p.timestamp),
            'image_url': p.image_url,
            'media_urls': parse_json_list(p.media_urls),
            'mentions': parse_json_list(p.mentions),
            'mention_names': parse_post_mentions(p.mentions),
            'location': p.location,
            'likes_count': PostLike.query.filter_by(post_id=p.id).count(),
            'is_liked': PostLike.query.filter_by(post_id=p.id, user_id=user_id).first() is not None
        } for p in posts])
    
    data = request.json
    # Only BIO can post as per user request
    if session.get('role') != 'bio':
        return jsonify({'error': 'Unauthorized'}), 401
    
    post = Post(
        author_id=session.get('user_id'), 
        content=data['content'], 
        image_url=data.get('image_url'), # Keeping for compatibility
        media_urls=json.dumps(data.get('media_urls', [])),
        mentions=json.dumps(normalize_post_mentions(data.get('mentions', []))),
        location=data.get('location')
    )
    db.session.add(post)
    db.session.commit()
    author = User.query.get(post.author_id)
    send_push_notifications(
        get_post_push_recipients(post),
        'iBarangay New BIO Post',
        f"New BIO post from {author.full_name if author else 'the barangay feed'}.",
        event_key='post',
        url_path=url_for('main.dashboard', tab='home'),
        tag=f'ibarangay-post-{post.id}',
    )
    return jsonify({'success': True})

@main.route('/api/posts/<int:post_id>', methods=['PUT', 'DELETE'])
def manage_post(post_id):
    if session.get('role') != 'bio':
        return jsonify({'error': 'Unauthorized'}), 401
    
    post = Post.query.get_or_404(post_id)
    if request.method == 'DELETE':
        try:
            PostLike.query.filter_by(post_id=post.id).delete(synchronize_session=False)
            db.session.delete(post)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Failed to delete post %s', post_id)
            return jsonify({'error': 'Unable to delete post right now.'}), 500
        return jsonify({'success': True})
    
    data = request.json
    post.content = data.get('content', post.content)
    if 'image_url' in data:
        post.image_url = data.get('image_url')
    if 'media_urls' in data:
        post.media_urls = json.dumps(data.get('media_urls', []))
    if 'mentions' in data:
        post.mentions = json.dumps(normalize_post_mentions(data.get('mentions', [])))
    if 'location' in data:
        post.location = data.get('location')
    db.session.commit()
    return jsonify({'success': True})

@main.route('/api/posts/<int:post_id>/like', methods=['POST'])
def toggle_like(post_id):
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    existing = PostLike.query.filter_by(post_id=post_id, user_id=session.get('user_id')).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'success': True, 'action': 'unliked'})
    else:
        db.session.add(PostLike(post_id=post_id, user_id=session.get('user_id')))
        db.session.commit()
        return jsonify({'success': True, 'action': 'liked'})

# === SUMMONS (PATAWAG) ===
@main.route('/api/summons', methods=['GET', 'POST'])
def handle_summons():
    if request.method == 'GET':
        user_id = session.get('user_id')
        role = session.get('role')
        if role == 'resident':
            s = Summons.query.filter_by(resident_id=user_id, acknowledged=False).all()
        else:
            s = Summons.query.order_by(Summons.timestamp.desc()).all()
        return jsonify([{'id':x.id, 'resident_id':x.resident_id, 'reason':x.reason, 'timestamp':serialize_utc_datetime(x.timestamp)} for x in s])
        
    data = request.json
    s = Summons(resident_id=data['resident_id'], official_id=session.get('user_id'), reason=data['reason'])
    db.session.add(s)
    db.session.commit()
    return jsonify({'success': True})

@main.route('/api/summons/ack', methods=['POST'])
def ack_summons():
    s = Summons.query.get(request.json['id'])
    s.acknowledged = True
    db.session.commit()
    return jsonify({'success': True})

# === Ratings ===
@main.route('/api/ratings/schedule', methods=['GET', 'POST'])
def rating_schedule():
    user = get_session_user()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    if request.method == 'GET':
        schedule = get_rating_schedule_windows_for_barangay(user.barangay_name)
        return jsonify(serialize_rating_schedule(schedule))

    if user.role != 'bio':
        return jsonify({'error': 'Only BIO can edit the rating schedule.'}), 403

    barangay_key = normalize_barangay_name(user.barangay_name)
    if not barangay_key:
        return jsonify({'error': 'Your BIO account has no barangay assigned.'}), 400

    data = request.json or {}
    raw_windows = data.get('windows')
    if not isinstance(raw_windows, list) or not raw_windows:
        raw_windows = [data]

    parsed_windows = []
    for index, raw_window in enumerate(raw_windows[:2], start=1):
        start_date = parse_schedule_date(raw_window.get('start_date'))
        end_date = parse_schedule_date(raw_window.get('end_date'))

        try:
            start_month = start_date.month if start_date else int(raw_window.get('start_month'))
            start_day = start_date.day if start_date else int(raw_window.get('start_day'))
            end_month = end_date.month if end_date else int(raw_window.get('end_month'))
            end_day = end_date.day if end_date else int(raw_window.get('end_day'))
        except (TypeError, ValueError):
            return jsonify({'error': 'Enter valid start and end dates for each rating window.'}), 400

        if not is_valid_month_day(start_month, start_day) or not is_valid_month_day(end_month, end_day):
            return jsonify({'error': 'The selected rating date range is invalid.'}), 400

        parsed_windows.append({
            'window_number': index,
            'start_month': start_month,
            'start_day': start_day,
            'end_month': end_month,
            'end_day': end_day,
        })

    if not parsed_windows:
        return jsonify({'error': 'Add at least one rating window.'}), 400

    for existing_window in RatingScheduleWindow.query.filter_by(barangay_key=barangay_key).all():
        db.session.delete(existing_window)

    saved_windows = []
    for window_data in parsed_windows:
        window = RatingScheduleWindow(
            barangay_key=barangay_key,
            barangay_name=user.barangay_name or barangay_key,
            updated_by=user.id,
            updated_at=utc_now(),
            **window_data
        )
        saved_windows.append(window)
        db.session.add(window)

    first_window = saved_windows[0]
    legacy_schedule = RatingSchedule.query.filter_by(barangay_key=barangay_key).first()
    if not legacy_schedule:
        legacy_schedule = RatingSchedule(barangay_key=barangay_key, barangay_name=user.barangay_name or barangay_key)
        db.session.add(legacy_schedule)

    legacy_schedule.barangay_name = user.barangay_name or legacy_schedule.barangay_name
    legacy_schedule.start_month = first_window.start_month
    legacy_schedule.start_day = first_window.start_day
    legacy_schedule.end_month = first_window.end_month
    legacy_schedule.end_day = first_window.end_day
    legacy_schedule.updated_by = user.id
    legacy_schedule.updated_at = utc_now()

    db.session.commit()
    log_action(user.id, f"Updated official rating schedule: {format_rating_schedule(saved_windows)}")
    return jsonify({'success': True, 'schedule': serialize_rating_schedule(saved_windows)})


@main.route('/api/ratings', methods=['POST'])
def submit_rating():
    if 'user_id' not in session: return jsonify({'error': 'unauthorized'}), 401
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return jsonify({'error': 'unauthorized'}), 401
    data = request.json
    now = ph_now()
    off_id = data.get('official_id')
    official = User.query.get(off_id) if off_id else None
    if not is_official_account(official):
        return jsonify({'error': 'Select a valid official to rate.'}), 400

    schedule = get_rating_schedule_windows_for_barangay(official.barangay_name or user.barangay_name)
    if not is_rating_schedule_open(schedule, now.date()):
        details = serialize_rating_schedule(schedule)
        return jsonify({'error': details['message'], 'schedule': details}), 400

    yearly_rating_query = Rating.query.filter(Rating.official_id == off_id, Rating.year == now.year)
    if user.family_id:
        yearly_rating_query = yearly_rating_query.filter(
            (Rating.rater_id == user.id) |
            ((Rating.rater_id == None) & (Rating.family_id == user.family_id))
        )
    else:
        yearly_rating_query = yearly_rating_query.filter(Rating.rater_id == user.id)

    if yearly_rating_query.count() >= 2:
        return jsonify({'error': 'You can only rate this official twice a year.'}), 400
    
    # User wants 1-5 rating.
    r_val = int(data.get('rating', 5))
    
    r = Rating(
        official_id=off_id, 
        family_id=user.family_id, 
        rater_id=user.id,
        month=now.month, 
        year=now.year, 
        responsiveness=r_val, 
        fairness=r_val, 
        service_quality=r_val, 
        community_involvement=r_val, 
        feedback_text=data.get('feedback')
    )
    db.session.add(r)
    db.session.commit()
    return jsonify({'success': True})


@main.route('/api/ratings/summary', methods=['GET'])
def get_rating_summary():
    user = get_session_user()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    year = request.args.get('year', type=int) or ph_year()
    return jsonify({'success': True, 'summary': build_rating_summary(user.barangay_name, year)})


@main.route('/api/ratings/analysis', methods=['GET'])
def get_rating_analysis():
    ratings = Rating.query.all()
    analysis = analyze_ratings(ratings)
    return jsonify({'success': True, 'analysis': analysis})

# === Emergency ===
@main.route('/api/emergency', methods=['POST', 'GET'])
def emergency():
    user = get_session_user()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    if request.method == 'GET':
        all_users = User.query.all()
        users_by_id = {item.id: item for item in all_users}
        emgs = filter_emergencies_to_viewer_barangay(
            user,
            Emergency.query.filter_by(acknowledged=False).order_by(Emergency.timestamp.desc()).all(),
            users_by_id=users_by_id,
        )
        return jsonify_no_store([{
            'id': e.id,
            'type': e.type,
            'lat': e.lat,
            'lng': e.lng,
            'purok': e.purok,
            'timestamp': serialize_utc_datetime(e.timestamp),
            'reported_by_name': users_by_id[e.reported_by].full_name if e.reported_by in users_by_id else 'Unknown'
        } for e in emgs])
    
    data = request.json or {}
    purok = data.get('purok')
    if purok in [None, '', 'N/A']:
        purok = user.purok
    e = Emergency(reported_by=user.id, type=data['type'], lat=data['lat'], lng=data['lng'], purok=purok)
    db.session.add(e)
    db.session.commit()
    log_action(user.id, f"Triggered {data['type'].upper()} Emergency at {(data['lat'], data['lng'])}")
    emergency_label = 'health report' if data['type'] == 'health' else 'incident'
    send_push_notifications(
        get_emergency_push_recipients(e),
        'iBarangay Emergency Alert',
        f"New {emergency_label} reported. Open the report tab now.",
        event_key='emergency',
        url_path=url_for('main.dashboard', tab='report'),
        tag=f'ibarangay-emergency-{e.id}',
        require_interaction=True,
    )
    return jsonify({'success': True})

@main.route('/api/emergency/ack', methods=['POST'])
def ack_emergency():
    user = get_session_user()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    data = request.json or {}
    e = Emergency.query.get(data['id'])
    if e:
        reporter = User.query.get(e.reported_by) if e.reported_by else None
        if reporter and not is_within_viewer_barangay_scope(user, reporter):
            return jsonify({'error': 'You cannot acknowledge emergencies outside your barangay scope.'}), 403
        e.acknowledged = True
        log_action(user.id, f"Acknowledged {e.type.upper()} emergency.")
        if e.reported_by:
            log_action(e.reported_by, f"🚨 NOTIFICATION: Your {e.type.upper()} report was acknowledged! Officials have secured the map coordinates and are mobilizing.")
        db.session.commit()
        if reporter and reporter.is_active:
            send_push_notifications(
                [reporter],
                'iBarangay Report Update',
                f"Your {e.type.upper()} report was acknowledged by barangay officials.",
                event_key='acknowledgment',
                url_path=url_for('main.dashboard', tab='notification'),
                tag=f'ibarangay-acknowledgment-{e.id}',
                require_interaction=True,
            )
    return jsonify({'success': True})

@main.route('/api/emergency/history', methods=['GET'])
def emg_history():
    user = get_session_user()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    all_users = User.query.all()
    users_by_id = {item.id: item for item in all_users}
    emgs = filter_emergencies_to_viewer_barangay(
        user,
        Emergency.query.filter_by(acknowledged=True).order_by(Emergency.timestamp.desc()).all(),
        users_by_id=users_by_id,
    )[:20]
    return jsonify_no_store([{
        'id': e.id,
        'type': e.type,
        'lat': e.lat,
        'lng': e.lng,
        'purok': e.purok,
        'timestamp': serialize_utc_datetime(e.timestamp),
        'reported_by_name': users_by_id[e.reported_by].full_name if e.reported_by in users_by_id else 'Unknown'
    } for e in emgs])

@main.route('/api/emergency/analysis', methods=['GET'])
def get_emergency_analysis():
    user = get_session_user()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    filter_type = request.args.get('type')
    iteration = request.args.get('iteration', default=0, type=int) or 0
    all_users = User.query.options(joinedload(User.family)).all()
    users_by_id = {item.id: item for item in all_users}
    users = filter_users_to_viewer_barangay(user, all_users)
    emgs = filter_emergencies_to_viewer_barangay(user, Emergency.query.all(), users_by_id=users_by_id)
    analysis = analyze_incident_and_health_risks(
        emgs,
        users,
        filter_type=filter_type,
        include_profile_details=session.get('role') in FULL_DIRECTORY_ROLES,
        barangay_name=user.barangay_name,
        iteration=iteration,
    )
    return jsonify({
        'success': True,
        **analysis
    })

@main.route('/api/history', methods=['GET'])
def get_history():
    user_id = session.get('user_id')
    if not user_id: return jsonify([])
    logs = HistoryLog.query.filter_by(user_id=user_id).order_by(HistoryLog.timestamp.desc()).limit(50).all()
    return jsonify([{'id': h.id, 'action': h.action, 'timestamp': serialize_utc_datetime(h.timestamp)} for h in logs])

@main.route('/api/bio/member/warn', methods=['POST'])
def warn_member():
    if session.get('role') != 'bio': return jsonify({'error':'Unauthorized'}), 401
    data = request.json
    u = User.query.get(data['id'])
    if not u: return jsonify({'error':'User not found'}), 404
    
    if u.role != 'resident':
        return jsonify({'error': 'Only Residents can be issued warnings/bans.'}), 400

    u.warning_count += 1
    now = utc_now()
    
    if u.warning_count == 1:
        u.banned_until = now + timedelta(hours=1)
        duration = "1 Hour"
    elif u.warning_count == 2:
        u.banned_until = now + timedelta(weeks=1)
        duration = "1 Week"
    else:
        u.banned_until = now + timedelta(days=30)
        duration = "30 Days"
        
    db.session.commit()
    log_action(session.get('user_id'), f"Issued Warning #{u.warning_count} to {u.full_name}. Banned for {duration}.")
    return jsonify({'success': True, 'warning_count': u.warning_count, 'banned_until': serialize_utc_datetime(u.banned_until)})

@main.route('/api/bio/member/toggle_active', methods=['POST'])
def toggle_member_active():
    if session.get('role') != 'bio': return jsonify({'error':'Unauthorized'}), 401
    u = User.query.get(request.json['id'])
    u.is_active = not u.is_active
    db.session.commit()
    log_action(session.get('user_id'), f"{'Activated' if u.is_active else 'Deactivated'} account for {u.full_name}")
    return jsonify({'success': True, 'is_active': u.is_active})
