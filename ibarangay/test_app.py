import unittest
import os
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

TEST_DB_PATH = os.path.join(tempfile.gettempdir(), f'ibarangay_test_{os.getpid()}.sqlite')
os.environ['DATABASE_URL'] = 'sqlite:///' + TEST_DB_PATH

from app import app, db
from datetime import date, datetime, timedelta
import json
from flask import render_template, render_template_string, session
from werkzeug.security import generate_password_hash
from models import User, Post, PostLike, Family, Emergency, Announcement, Event, FinancialReport, Summons, Rating, RatingSchedule, RatingScheduleWindow, WelfareDistribution, ReliefDistribution, HistoryLog, PushSubscription
from ai_model.train_health_risk_model import train as train_health_model_artifact
from time_utils import ph_now, ph_today, ph_year

class AppTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + TEST_DB_PATH
        self.app = app.test_client()
        self._user_seq = 0
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_startup(self):
        res = self.app.get('/')
        self.assertEqual(res.status_code, 302)
        
    def test_dashboard_no_login(self):
        res = self.app.get('/dashboard')
        self.assertEqual(res.status_code, 302)

    def test_login_page_contains_password_visibility_toggle(self):
        res = self.app.get('/login')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('id="login-password-toggle"', html)
        self.assertIn('id="reg-password-toggle"', html)
        self.assertIn("togglePasswordVisibility('password', this)", html)
        self.assertIn("togglePasswordVisibility('reg-pass', this)", html)
        self.assertIn('fa-eye-slash', html)

    def test_dashboard_shows_logged_in_profile_picture_and_modal(self):
        with app.app_context():
            user = self.create_user(
                role='resident',
                full_name='Profile Resident',
                username='profile-resident@test.ph',
                barangay_name='San Roque',
                purok=4,
                pic_url='/uploads/profile-resident.jpg',
                mother_name='Maria Resident',
                father_name='Jose Resident',
                employment_status='Self-Employed'
            )

            self.login_as(user)
            res = self.app.get('/dashboard')

        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('id="profile-info-modal"', html)
        self.assertIn('Open your profile details', html)
        self.assertIn('/uploads/profile-resident.jpg', html)
        self.assertIn('Profile Resident', html)
        self.assertIn('profile-resident@test.ph', html)
        self.assertIn('Maria Resident', html)
        self.assertIn('Jose Resident', html)

    def test_dashboard_serializes_blank_resident_location_values_safely(self):
        user = SimpleNamespace(
            role='resident',
            full_name='Blank Location Resident',
            username='blank-location@test.ph',
            purok='',
            lat='',
            lng='',
            pic_url=None,
            barangay_name=None,
            position=None,
            birthdate=None,
            birthplace=None,
            monthly_income=0,
            employment_status=None,
            mother_name=None,
            father_name=None
        )

        with app.test_request_context('/dashboard'):
            session['user_id'] = 1
            session['role'] = 'resident'
            session['brgy'] = ''
            html = render_template('resident_dashboard.html', user=user)

        self.assertIn('window.USER_PUROK = null;', html)
        self.assertIn('window.USER_HOME_LAT = null;', html)
        self.assertIn('window.USER_HOME_LNG = null;', html)

    def test_base_template_prefers_current_user_barangay_for_shared_js_state(self):
        user = SimpleNamespace(
            role='bio',
            full_name='Assigned BIO',
            username='assigned-bio@test.ph',
            barangay_name='Mabuhay',
            purok=1,
            lat=None,
            lng=None,
            pic_url=None,
            position='BIO',
            birthdate=None,
            birthplace=None,
            monthly_income=0,
            employment_status=None,
            mother_name=None,
            father_name=None
        )

        with app.test_request_context('/dashboard'):
            session['user_id'] = 1
            session['role'] = 'bio'
            session['brgy'] = ''
            html = render_template('bio_dashboard.html', user=user)

        self.assertIn('window.USER_ROLE = "bio";', html)
        self.assertIn('window.USER_BRGY = "Mabuhay";', html)

    def test_base_template_exposes_wipe_barangay_handler_for_bio_sidebar(self):
        with app.test_request_context('/dashboard'):
            session['user_id'] = 1
            session['role'] = 'bio'
            session['brgy'] = 'Mabuhay'
            html = render_template_string("{% extends 'base.html' %}{% block content %}Test{% endblock %}")

        self.assertIn('Delete Entire Barangay Page & All Records', html)
        self.assertIn('href="/bio/barangay/wipe"', html)
        self.assertIn('async function wipeBarangayPage()', html)

    def test_rendered_pages_expose_static_button_handlers(self):
        main_js = Path('static/js/main.js').read_text(encoding='utf-8')
        builtin_names = {'alert', 'if'}
        handler_pattern = re.compile(r'(?<![\w.])(?:window\.)?([A-Za-z_][A-Za-z0-9_]*)\s*\(')
        script_function_pattern = re.compile(r'(?:async\s+function|function)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(')
        window_assignment_pattern = re.compile(r'window\.([A-Za-z_][A-Za-z0-9_]*)\s*=')

        cases = [
            ('login.html', None),
            (
                'superadmin_dashboard.html',
                SimpleNamespace(
                    role='superadmin',
                    full_name='Super Admin',
                    username='superadmin@test.ph',
                    barangay_name='Mabuhay',
                    purok=1,
                    lat=None,
                    lng=None,
                    pic_url=None,
                    position='Admin',
                    birthdate=None,
                    birthplace=None,
                    monthly_income=0,
                    employment_status=None,
                    mother_name=None,
                    father_name=None,
                    is_approved=True,
                ),
            ),
            (
                'bio_dashboard.html',
                SimpleNamespace(
                    role='bio',
                    full_name='Barangay BIO',
                    username='bio@test.ph',
                    barangay_name='Mabuhay',
                    purok=1,
                    lat=None,
                    lng=None,
                    pic_url=None,
                    position='BIO',
                    birthdate=None,
                    birthplace=None,
                    monthly_income=0,
                    employment_status=None,
                    mother_name=None,
                    father_name=None,
                    is_approved=True,
                ),
            ),
            (
                'official_dashboard.html',
                SimpleNamespace(
                    role='official',
                    full_name='Barangay Official',
                    username='official@test.ph',
                    barangay_name='Mabuhay',
                    purok=1,
                    lat=None,
                    lng=None,
                    pic_url=None,
                    position='Captain',
                    birthdate=None,
                    birthplace=None,
                    monthly_income=0,
                    employment_status=None,
                    mother_name=None,
                    father_name=None,
                    is_approved=True,
                ),
            ),
            (
                'resident_dashboard.html',
                SimpleNamespace(
                    role='resident',
                    full_name='Resident User',
                    username='resident@test.ph',
                    barangay_name='Mabuhay',
                    purok=1,
                    lat=None,
                    lng=None,
                    pic_url=None,
                    position=None,
                    birthdate=None,
                    birthplace=None,
                    monthly_income=0,
                    employment_status=None,
                    mother_name=None,
                    father_name=None,
                    is_approved=True,
                ),
            ),
        ]

        for template_name, user in cases:
            with self.subTest(template=template_name):
                with app.test_request_context('/dashboard'):
                    if user:
                        session['user_id'] = 1
                        session['role'] = user.role
                        session['brgy'] = user.barangay_name
                        session['position'] = user.position
                        html = render_template(template_name, user=user)
                    else:
                        html = render_template(template_name)

                html_without_scripts = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.S | re.I)
                onclick_values = re.findall(r'onclick="([^"]+)"', html_without_scripts)
                handlers = set()
                for onclick in onclick_values:
                    for name in handler_pattern.findall(onclick):
                        if name not in builtin_names:
                            handlers.add(name)

                inline_scripts = '\n'.join(re.findall(r'<script[^>]*>(.*?)</script>', html, re.S | re.I))
                available = set(script_function_pattern.findall(inline_scripts))
                available.update(window_assignment_pattern.findall(inline_scripts))
                available.update(script_function_pattern.findall(main_js))
                available.update(window_assignment_pattern.findall(main_js))

                missing = sorted(name for name in handlers if name not in available)
                self.assertEqual(missing, [])
        
    def test_dashboard_with_login_missing_user(self):
        with self.app.session_transaction() as sess:
            sess['user_id'] = 999 # Non-existent user
        res = self.app.get('/dashboard')
        self.assertEqual(res.status_code, 302) # Redirect rather than AttributeError crash

    def test_get_residents_missing_user(self):
        with self.app.session_transaction() as sess:
            sess['user_id'] = 999 # Non-existent user
        res = self.app.get('/api/residents')
        self.assertEqual(res.status_code, 200) # Expect clean JSON with no crash

    def test_submit_rating_missing_user(self):
        with self.app.session_transaction() as sess:
            sess['user_id'] = 999 # Non-existent user
        res = self.app.post('/api/ratings', json={"foo": "bar"})
        self.assertEqual(res.status_code, 401)

    def test_register_bio_appears_in_superadmin_pending_list(self):
        res = self.app.post('/register_bio', json={
            'username': 'pendingbio@test.ph',
            'full_name': 'Pending BIO',
            'password': 'secret123',
            'position': 'Secretary',
            'barangay_name': 'Mabuhay'
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        pending = self.app.get('/api/superadmin/bios')
        self.assertEqual(pending.status_code, 200)
        pending_rows = pending.get_json()
        self.assertEqual(len(pending_rows), 1)
        self.assertEqual(pending_rows[0]['username'], 'pendingbio@test.ph')

    def test_superadmin_barangay_overview_lists_registered_barangay_counts(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Approved BIO',
                username='approvedbio@test.ph',
                barangay_name='San Roque',
                is_approved=True
            )
            self.create_user(
                role='bio',
                full_name='Pending BIO',
                username='pendingbio2@test.ph',
                barangay_name='San Roque',
                is_approved=False
            )
            official = self.create_user(
                role='official',
                full_name='Hon. Pedro Santos',
                username='officialsanroque@test.ph',
                barangay_name='San Roque'
            )
            resident = self.create_user(
                role='resident',
                full_name='Maria Cruz',
                username='residentsanroque@test.ph',
                barangay_name='San Roque'
            )
            self.create_user(
                role='resident',
                full_name='Other Resident',
                username='otherresident@test.ph',
                barangay_name='Mabuhay'
            )

            db.session.add_all([
                Post(author_id=bio.id, content='Barangay update'),
                Emergency(reported_by=resident.id, type='accident', lat=9.1, lng=125.1),
                Emergency(reported_by=resident.id, type='health', lat=9.2, lng=125.2),
                Announcement(message='Community announcement', created_by=bio.id),
                Event(title='Clean up drive', description='Barangay activity', date=ph_now().replace(tzinfo=None), created_by=bio.id),
                FinancialReport(month=4, year=2026, total_funds=10000, relief_distribution=2500, project_expenses=3500, uploaded_by=bio.id),
                Summons(resident_id=resident.id, official_id=official.id, reason='Meeting'),
                Rating(official_id=official.id, month=4, year=2026, responsiveness=5, fairness=5, service_quality=5, community_involvement=5)
            ])
            db.session.commit()

            res = self.app.get('/api/superadmin/barangays')

        self.assertEqual(res.status_code, 200)
        rows = res.get_json()
        san_roque = next(row for row in rows if row['name'] == 'San Roque')

        self.assertEqual(san_roque['status'], 'Controlled')
        self.assertEqual(san_roque['residents'], 1)
        self.assertEqual(san_roque['officials'], 2)
        self.assertEqual(san_roque['bios'], 1)
        self.assertEqual(san_roque['pending_bios'], 1)
        self.assertEqual(san_roque['posts'], 1)
        self.assertEqual(san_roque['reports'], 2)
        self.assertEqual(san_roque['incident_reports'], 1)
        self.assertEqual(san_roque['health_reports'], 1)
        self.assertEqual(san_roque['announcements'], 1)
        self.assertEqual(san_roque['events'], 1)
        self.assertEqual(san_roque['financial_reports'], 1)
        self.assertEqual(san_roque['summons'], 1)
        self.assertEqual(san_roque['ratings'], 1)
        self.assertEqual(san_roque['other_records'], 5)
        self.assertEqual(san_roque['total_members'], 3)

    def test_approved_bio_is_listed_as_official_with_position(self):
        with app.app_context():
            viewer = self.create_user(role='resident', full_name='Resident Viewer')
            approved_bio = self.create_user(
                role='bio',
                full_name='Hon. Maria Santos',
                username='captainbio@test.ph',
                barangay_name='Mabuhay',
                position='Barangay Captain',
                is_approved=True
            )
            pending_bio = self.create_user(
                role='bio',
                full_name='Pending BIO',
                username='pendingofficialbio@test.ph',
                barangay_name='Mabuhay',
                position='PIO',
                is_approved=False
            )
            approved_bio_id = approved_bio.id
            pending_bio_id = pending_bio.id

            self.login_as(viewer)
            res = self.app.get('/api/officials')

        self.assertEqual(res.status_code, 200)
        officials = res.get_json()
        official_ids = {item['id'] for item in officials}
        approved_row = next(item for item in officials if item['id'] == approved_bio_id)

        self.assertIn(approved_bio_id, official_ids)
        self.assertNotIn(pending_bio_id, official_ids)
        self.assertEqual(approved_row['role'], 'bio')
        self.assertEqual(approved_row['position'], 'Barangay Captain')

    def test_official_can_create_welfare_distribution_and_update_family_running_total(self):
        with app.app_context():
            official = self.create_user(
                role='official',
                full_name='Hon. Welfare Officer',
                username='welfareofficial@test.ph',
                barangay_name='San Roque'
            )
            family = Family(class_type='D', size=5, past_aid_received=250)
            db.session.add(family)
            db.session.commit()

            resident = self.create_user(
                role='resident',
                full_name='Ana Welfare',
                username='anawelfare@test.ph',
                barangay_name='San Roque',
                family_id=family.id
            )
            resident_id = resident.id
            family_id = family.id

            self.login_as(official)
            res = self.app.post('/api/welfare/distributions', json={
                'resident_id': resident_id,
                'assistance_type': 'Food Pack',
                'program_name': 'Relief Batch A',
                'amount': 1000,
                'quantity': 2,
                'unit': 'packs',
                'status': 'released',
                'distributed_on': '2026-04-25',
                'reference_code': 'WEL-CREATE-001',
                'notes': 'Delivered at the barangay hall.'
            })

            created = WelfareDistribution.query.filter_by(reference_code='WEL-CREATE-001').first()
            updated_family = Family.query.get(family_id)

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])
        self.assertIsNotNone(created)
        self.assertEqual(created.resident_id, resident_id)
        self.assertEqual(created.status, 'released')
        self.assertEqual(created.distributed_on, date(2026, 4, 25))
        self.assertEqual(updated_family.past_aid_received, 1250)

    def test_official_can_create_welfare_distribution_for_multiple_beneficiaries(self):
        with app.app_context():
            official = self.create_user(
                role='official',
                full_name='Hon. Batch Welfare Officer',
                username='batchwelfareofficial@test.ph',
                barangay_name='San Roque'
            )
            family_one = Family(class_type='C', size=4, past_aid_received=100)
            family_two = Family(class_type='D', size=6, past_aid_received=300)
            db.session.add_all([family_one, family_two])
            db.session.commit()

            resident_one = self.create_user(
                role='resident',
                full_name='Batch Resident One',
                username='batchresidentone@test.ph',
                barangay_name='San Roque',
                family_id=family_one.id
            )
            resident_two = self.create_user(
                role='resident',
                full_name='Batch Resident Two',
                username='batchresidenttwo@test.ph',
                barangay_name='San Roque',
                family_id=family_two.id
            )

            self.login_as(official)
            res = self.app.post('/api/welfare/distributions', json={
                'resident_ids': [resident_one.id, resident_two.id],
                'assistance_type': 'Food Pack',
                'program_name': 'Batch Relief',
                'amount': 500,
                'quantity': 1,
                'unit': 'pack',
                'status': 'released',
                'distributed_on': '2026-04-25',
                'reference_code': 'WEL-BATCH-001'
            })

            records = WelfareDistribution.query.filter(WelfareDistribution.reference_code.like('WEL-BATCH-001-%')).order_by(WelfareDistribution.reference_code.asc()).all()
            updated_family_one = Family.query.get(family_one.id)
            updated_family_two = Family.query.get(family_two.id)

        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['created_count'], 2)
        self.assertEqual(len(payload['distributions']), 2)
        self.assertEqual([record.reference_code for record in records], ['WEL-BATCH-001-001', 'WEL-BATCH-001-002'])
        self.assertEqual(updated_family_one.past_aid_received, 600)
        self.assertEqual(updated_family_two.past_aid_received, 800)

    def test_resident_welfare_listing_shows_only_their_records(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Hon. BIO Welfare',
                username='biowelfare@test.ph',
                barangay_name='San Roque',
                is_approved=True
            )
            resident_one = self.create_user(
                role='resident',
                full_name='Maria One',
                username='mariaone@test.ph',
                barangay_name='San Roque'
            )
            resident_two = self.create_user(
                role='resident',
                full_name='Pedro Two',
                username='pedrotwo@test.ph',
                barangay_name='San Roque'
            )

            db.session.add_all([
                WelfareDistribution(
                    resident_id=resident_one.id,
                    family_id=resident_one.family_id,
                    assistance_type='Medical Aid',
                    program_name='Health Support',
                    reference_code='WEL-LIST-001',
                    amount=700,
                    quantity=1,
                    unit='voucher',
                    status='released',
                    distributed_on=date(2026, 4, 25),
                    created_by=bio.id
                ),
                WelfareDistribution(
                    resident_id=resident_two.id,
                    family_id=resident_two.family_id,
                    assistance_type='Cash Aid',
                    program_name='Livelihood Support',
                    reference_code='WEL-LIST-002',
                    amount=1500,
                    quantity=1,
                    unit='grant',
                    status='approved',
                    created_by=bio.id
                )
            ])
            db.session.commit()

            self.login_as(resident_one)
            res = self.app.get('/api/welfare/distributions')

        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['summary']['total_records'], 1)
        self.assertEqual(len(payload['records']), 1)
        self.assertEqual(payload['records'][0]['resident_id'], resident_one.id)
        self.assertEqual(payload['records'][0]['reference_code'], 'WEL-LIST-001')

    def test_bio_can_update_welfare_distribution_status_and_family_totals(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Hon. Welfare BIO',
                username='welfarebio@test.ph',
                barangay_name='San Roque',
                is_approved=True
            )
            family = Family(class_type='C', size=4, past_aid_received=0)
            db.session.add(family)
            db.session.commit()

            resident = self.create_user(
                role='resident',
                full_name='Liza Support',
                username='lizasupport@test.ph',
                barangay_name='San Roque',
                family_id=family.id
            )

            record = WelfareDistribution(
                resident_id=resident.id,
                family_id=family.id,
                assistance_type='Rice Subsidy',
                program_name='Emergency Reserve',
                reference_code='WEL-UPDATE-001',
                amount=750,
                quantity=1,
                unit='allocation',
                status='approved',
                created_by=bio.id
            )
            db.session.add(record)
            db.session.commit()
            record_id = record.id
            family_id = family.id

            self.login_as(bio)
            res = self.app.put(f'/api/welfare/distributions/{record_id}', json={
                'status': 'released',
                'distributed_on': '2026-04-25',
                'notes': 'Released after verification.'
            })

            updated = WelfareDistribution.query.get(record_id)
            updated_family = Family.query.get(family_id)

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])
        self.assertEqual(updated.status, 'released')
        self.assertEqual(updated.distributed_on, date(2026, 4, 25))
        self.assertEqual(updated_family.past_aid_received, 750)

    def test_resident_cannot_create_welfare_distribution(self):
        with app.app_context():
            resident = self.create_user(
                role='resident',
                full_name='Resident Sender',
                username='residentsender@test.ph',
                barangay_name='San Roque'
            )
            target = self.create_user(
                role='resident',
                full_name='Resident Target',
                username='residenttarget@test.ph',
                barangay_name='San Roque'
            )

            self.login_as(resident)
            res = self.app.post('/api/welfare/distributions', json={
                'resident_id': target.id,
                'assistance_type': 'Cash Aid',
                'status': 'planned'
            })

        self.assertEqual(res.status_code, 403)
        self.assertIn('Only BIO and barangay officials', res.get_json()['error'])

    def test_bio_post_includes_author_position_for_feed_display(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Hon. Pedro Reyes',
                username='piobio@test.ph',
                barangay_name='Mabuhay',
                position='PIO',
                is_approved=True
            )
            db.session.add(Post(author_id=bio.id, content='Barangay announcement'))
            db.session.commit()

            self.login_as(bio)
            res = self.app.get('/api/posts')

        self.assertEqual(res.status_code, 200)
        post = next(item for item in res.get_json() if item['content'] == 'Barangay announcement')
        self.assertEqual(post['author_role'], 'bio')
        self.assertEqual(post['author_position'], 'PIO')

    def test_bio_can_target_announcement_by_selected_names_and_edit_delete(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='announcementbio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            target = self.create_user(
                role='resident',
                full_name='Target Resident',
                username='targetresident@test.ph',
                barangay_name='Mabuhay'
            )
            other = self.create_user(
                role='resident',
                full_name='Other Resident',
                username='otherannouncement@test.ph',
                barangay_name='Mabuhay'
            )
            target_id = target.id
            other_id = other.id

            self.login_as(bio)
            create_res = self.app.post('/api/announcements', json={
                'message': 'Targeted notice',
                'target_users': [{'id': target.id, 'name': target.full_name}]
            })
            announcement_id = create_res.get_json()['announcement']['id']

            update_res = self.app.put(f'/api/announcements/{announcement_id}', json={
                'message': 'Updated targeted notice',
                'target_users': [{'id': target.id, 'name': target.full_name}]
            })

            self.login_as(target)
            target_res = self.app.get('/api/announcements')

            self.login_as(other)
            other_res = self.app.get('/api/announcements')

            self.login_as(bio)
            delete_res = self.app.delete(f'/api/announcements/{announcement_id}')
            deleted = Announcement.query.get(announcement_id)

        self.assertEqual(create_res.status_code, 200)
        self.assertTrue(create_res.get_json()['success'])
        self.assertEqual(create_res.get_json()['announcement']['target_names'], ['Target Resident'])
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.get_json()['announcement']['message'], 'Updated targeted notice')
        self.assertTrue(any(item['id'] == announcement_id for item in target_res.get_json()))
        self.assertFalse(any(item['id'] == announcement_id for item in other_res.get_json()))
        self.assertEqual(delete_res.status_code, 200)
        self.assertIsNone(deleted)

    def test_bio_can_target_announcement_to_multiple_puroks(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='purokbio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            purok_one = self.create_user(
                role='resident',
                full_name='Purok One Resident',
                username='purokone@test.ph',
                barangay_name='Mabuhay',
                purok=1
            )
            purok_two = self.create_user(
                role='resident',
                full_name='Purok Two Resident',
                username='puroktwo@test.ph',
                barangay_name='Mabuhay',
                purok=2
            )
            purok_three = self.create_user(
                role='resident',
                full_name='Purok Three Resident',
                username='purokthree@test.ph',
                barangay_name='Mabuhay',
                purok=3
            )

            self.login_as(bio)
            create_res = self.app.post('/api/announcements', json={
                'message': 'Purok 1 and 3 notice',
                'target_puroks': [1, 3]
            })
            announcement_id = create_res.get_json()['announcement']['id']

            self.login_as(purok_one)
            one_res = self.app.get('/api/announcements')

            self.login_as(purok_two)
            two_res = self.app.get('/api/announcements')

            self.login_as(purok_three)
            three_res = self.app.get('/api/announcements')

        self.assertEqual(create_res.status_code, 200)
        self.assertEqual(create_res.get_json()['announcement']['target_puroks'], [1, 3])
        self.assertTrue(any(item['id'] == announcement_id for item in one_res.get_json()))
        self.assertFalse(any(item['id'] == announcement_id for item in two_res.get_json()))
        self.assertTrue(any(item['id'] == announcement_id for item in three_res.get_json()))

    def test_announcement_name_targets_ignore_purok_targets(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='nameoverpurokbio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            target = self.create_user(
                role='resident',
                full_name='Named Target',
                username='namedtarget@test.ph',
                barangay_name='Mabuhay',
                purok=1
            )
            purok_two = self.create_user(
                role='resident',
                full_name='Purok Two Only',
                username='puroktwoonly@test.ph',
                barangay_name='Mabuhay',
                purok=2
            )

            self.login_as(bio)
            create_res = self.app.post('/api/announcements', json={
                'message': 'Name target beats purok',
                'target_puroks': [2],
                'target_users': [{'id': target.id, 'name': target.full_name}]
            })
            announcement_id = create_res.get_json()['announcement']['id']

            self.login_as(target)
            target_res = self.app.get('/api/announcements')

            self.login_as(purok_two)
            purok_res = self.app.get('/api/announcements')

        self.assertEqual(create_res.status_code, 200)
        self.assertEqual(create_res.get_json()['announcement']['target_puroks'], [])
        self.assertTrue(any(item['id'] == announcement_id for item in target_res.get_json()))
        self.assertFalse(any(item['id'] == announcement_id for item in purok_res.get_json()))

    def test_bio_can_create_and_edit_official_rating_schedule(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='schedulebio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            self.login_as(bio)

            res = self.app.post('/api/ratings/schedule', json={
                'start_month': 4,
                'start_day': 1,
                'end_month': 4,
                'end_day': 30
            })
            edit_res = self.app.post('/api/ratings/schedule', json={
                'start_month': 5,
                'start_day': 2,
                'end_month': 5,
                'end_day': 20
            })

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])
        self.assertEqual(edit_res.status_code, 200)
        schedule = edit_res.get_json()['schedule']
        self.assertEqual(schedule['start_month'], 5)
        self.assertEqual(schedule['start_day'], 2)
        self.assertEqual(schedule['end_month'], 5)
        self.assertEqual(schedule['end_day'], 20)

    def test_bio_can_set_two_calendar_rating_windows(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Calendar BIO',
                username='calendarbio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            self.login_as(bio)

            res = self.app.post('/api/ratings/schedule', json={
                'windows': [
                    {'start_date': '2026-04-01', 'end_date': '2026-04-15'},
                    {'start_date': '2026-10-01', 'end_date': '2026-10-15'}
                ]
            })

        self.assertEqual(res.status_code, 200)
        schedule = res.get_json()['schedule']
        self.assertEqual(len(schedule['windows']), 2)
        self.assertEqual(schedule['windows'][0]['start_month'], 4)
        self.assertEqual(schedule['windows'][1]['start_month'], 10)

    def test_rating_requires_active_bio_schedule(self):
        today = ph_today()
        closed_day = today + timedelta(days=90)

        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='closedratingbio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            official = self.create_user(
                role='official',
                full_name='Hon. Closed Rating',
                username='closedofficial@test.ph',
                barangay_name='Mabuhay',
                position='Councilor'
            )
            resident = self.create_user(
                role='resident',
                full_name='Rating Resident',
                username='closedresident@test.ph',
                barangay_name='Mabuhay'
            )
            db.session.add(RatingSchedule(
                barangay_key='mabuhay',
                barangay_name='Mabuhay',
                start_month=closed_day.month,
                start_day=closed_day.day,
                end_month=closed_day.month,
                end_day=closed_day.day,
                updated_by=bio.id
            ))
            db.session.commit()

            self.login_as(resident)
            res = self.app.post('/api/ratings', json={
                'official_id': official.id,
                'rating': 5,
                'feedback': 'Helpful'
            })

        self.assertEqual(res.status_code, 400)
        self.assertIn('closed', res.get_json()['error'].lower())

    def test_rating_is_allowed_during_bio_schedule(self):
        today = ph_today()

        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='openratingbio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            official = self.create_user(
                role='official',
                full_name='Hon. Open Rating',
                username='openofficial@test.ph',
                barangay_name='Mabuhay',
                position='Councilor'
            )
            resident = self.create_user(
                role='resident',
                full_name='Rating Resident',
                username='openresident@test.ph',
                barangay_name='Mabuhay'
            )
            db.session.add(RatingSchedule(
                barangay_key='mabuhay',
                barangay_name='Mabuhay',
                start_month=today.month,
                start_day=today.day,
                end_month=today.month,
                end_day=today.day,
                updated_by=bio.id
            ))
            db.session.commit()

            self.login_as(resident)
            res = self.app.post('/api/ratings', json={
                'official_id': official.id,
                'rating': 5,
                'feedback': 'Helpful'
            })

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

    def test_member_can_rate_same_official_only_twice_per_year(self):
        today = ph_today()

        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='twiceratingbio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            official = self.create_user(
                role='official',
                full_name='Hon. Twice Rating',
                username='twiceofficial@test.ph',
                barangay_name='Mabuhay',
                position='Councilor'
            )
            resident = self.create_user(
                role='resident',
                full_name='Twice Rating Resident',
                username='twiceresident@test.ph',
                barangay_name='Mabuhay',
                purok=1
            )
            db.session.add(RatingScheduleWindow(
                barangay_key='mabuhay',
                barangay_name='Mabuhay',
                window_number=1,
                start_month=today.month,
                start_day=today.day,
                end_month=today.month,
                end_day=today.day,
                updated_by=bio.id
            ))
            db.session.commit()

            self.login_as(resident)
            payload = {'official_id': official.id, 'rating': 5, 'feedback': 'Good'}
            first = self.app.post('/api/ratings', json=payload)
            second = self.app.post('/api/ratings', json=payload)
            third = self.app.post('/api/ratings', json=payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 400)
        self.assertIn('twice a year', third.get_json()['error'])

    def test_rating_summary_ranks_officials_and_groups_by_purok(self):
        current_year = ph_year()

        with app.app_context():
            viewer = self.create_user(
                role='resident',
                full_name='Summary Viewer',
                username='summaryviewer@test.ph',
                barangay_name='Mabuhay',
                purok=1
            )
            high_official = self.create_user(
                role='official',
                full_name='Hon. Ana High',
                username='highofficial@test.ph',
                barangay_name='Mabuhay',
                position='Captain'
            )
            low_official = self.create_user(
                role='official',
                full_name='Hon. Ben Low',
                username='lowofficial@test.ph',
                barangay_name='Mabuhay',
                position='Councilor'
            )
            rater_one = self.create_user(
                role='resident',
                full_name='Rater One',
                username='raterone@test.ph',
                barangay_name='Mabuhay',
                purok=1
            )
            rater_two = self.create_user(
                role='resident',
                full_name='Rater Two',
                username='ratertwo@test.ph',
                barangay_name='Mabuhay',
                purok=2
            )
            db.session.add_all([
                Rating(official_id=high_official.id, rater_id=rater_one.id, month=4, year=current_year, responsiveness=5, fairness=5, service_quality=5, community_involvement=5),
                Rating(official_id=high_official.id, rater_id=rater_two.id, month=4, year=current_year, responsiveness=4, fairness=4, service_quality=4, community_involvement=4),
                Rating(official_id=low_official.id, rater_id=rater_one.id, month=4, year=current_year, responsiveness=2, fairness=2, service_quality=2, community_involvement=2),
            ])
            db.session.commit()
            high_id = high_official.id
            low_id = low_official.id

            self.login_as(viewer)
            res = self.app.get('/api/ratings/summary')

        self.assertEqual(res.status_code, 200)
        officials = res.get_json()['summary']['officials']
        self.assertEqual(officials[0]['official_id'], high_id)
        self.assertEqual(officials[-1]['official_id'], low_id)
        self.assertEqual(officials[0]['initials'], 'AH')
        self.assertEqual(officials[0]['total_votes'], 2)
        self.assertEqual(officials[0]['average_rating'], 4.5)
        purok_rows = {row['purok']: row for row in officials[0]['ratings_by_purok']}
        self.assertEqual(purok_rows['1']['total_votes'], 1)
        self.assertEqual(purok_rows['2']['total_votes'], 1)

    def test_bio_can_delete_resident_official_and_own_bio_account(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='deletebio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            resident = self.create_user(
                role='resident',
                full_name='Delete Resident',
                username='deleteresident@test.ph',
                barangay_name='Mabuhay'
            )
            official = self.create_user(
                role='official',
                full_name='Hon. Delete Official',
                username='deleteofficial@test.ph',
                barangay_name='Mabuhay'
            )
            db.session.add(Summons(resident_id=resident.id, official_id=official.id, reason='Test summons'))
            db.session.add(Rating(official_id=official.id, month=4, year=2026, responsiveness=5, fairness=5, service_quality=5, community_involvement=5))
            db.session.commit()
            resident_id = resident.id
            official_id = official.id
            bio_id = bio.id

            self.login_as(bio)
            resident_res = self.app.delete(f'/api/bio/member/{resident_id}')
            official_res = self.app.delete(f'/api/bio/member/{official_id}')
            bio_res = self.app.delete(f'/api/bio/member/{bio_id}')

            remaining_resident = User.query.get(resident_id)
            remaining_official = User.query.get(official_id)
            remaining_bio = User.query.get(bio_id)

        self.assertEqual(resident_res.status_code, 200)
        self.assertEqual(official_res.status_code, 200)
        self.assertEqual(bio_res.status_code, 200)
        self.assertIsNone(remaining_resident)
        self.assertIsNone(remaining_official)
        self.assertIsNone(remaining_bio)

    def test_member_delete_cleans_linked_records_that_block_mysql_deletes(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='cleanupbio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            resident = self.create_user(
                role='resident',
                full_name='Cleanup Resident',
                username='cleanupresident@test.ph',
                barangay_name='Mabuhay'
            )
            official = self.create_user(
                role='official',
                full_name='Hon. Cleanup Official',
                username='cleanupofficial@test.ph',
                barangay_name='Mabuhay'
            )
            other_resident = self.create_user(
                role='resident',
                full_name='Second Resident',
                username='cleanupresident2@test.ph',
                barangay_name='Mabuhay'
            )
            post = Post(author_id=bio.id, content='Cleanup test post')
            db.session.add(post)
            db.session.commit()

            db.session.add(PostLike(post_id=post.id, user_id=resident.id))
            db.session.add(WelfareDistribution(
                resident_id=resident.id,
                created_by=official.id,
                assistance_type='Food Pack',
                program_name='Resident Aid',
                reference_code='WD-DEL-001'
            ))
            db.session.add(WelfareDistribution(
                resident_id=other_resident.id,
                created_by=official.id,
                assistance_type='Rice',
                program_name='Official Aid',
                reference_code='WD-DEL-002'
            ))
            rating = Rating(
                official_id=official.id,
                rater_id=resident.id,
                month=4,
                year=2026,
                responsiveness=5,
                fairness=5,
                service_quality=5,
                community_involvement=5
            )
            schedule = RatingSchedule(
                barangay_key='mabuhay',
                barangay_name='Mabuhay',
                start_month=1,
                start_day=1,
                end_month=1,
                end_day=31,
                updated_by=official.id
            )
            window = RatingScheduleWindow(
                barangay_key='mabuhay',
                barangay_name='Mabuhay',
                window_number=1,
                start_month=1,
                start_day=1,
                end_month=1,
                end_day=31,
                updated_by=official.id
            )
            db.session.add(rating)
            db.session.add(schedule)
            db.session.add(window)
            db.session.commit()

            resident_id = resident.id
            official_id = official.id
            rating_id = rating.id
            schedule_id = schedule.id
            window_id = window.id

            self.login_as(bio)
            resident_res = self.app.delete(f'/api/bio/member/{resident_id}')
            official_res = self.app.delete(f'/api/bio/member/{official_id}')

            remaining_resident = User.query.get(resident_id)
            remaining_official = User.query.get(official_id)
            saved_rating = Rating.query.get(rating_id)
            saved_schedule = RatingSchedule.query.get(schedule_id)
            saved_window = RatingScheduleWindow.query.get(window_id)
            remaining_resident_likes = PostLike.query.filter_by(user_id=resident_id).count()
            resident_welfare_count = WelfareDistribution.query.filter_by(reference_code='WD-DEL-001').count()
            official_welfare_count = WelfareDistribution.query.filter_by(reference_code='WD-DEL-002').count()

        self.assertEqual(resident_res.status_code, 200)
        self.assertEqual(official_res.status_code, 200)
        self.assertIsNone(remaining_resident)
        self.assertIsNone(remaining_official)
        self.assertEqual(remaining_resident_likes, 0)
        self.assertEqual(resident_welfare_count, 0)
        self.assertEqual(official_welfare_count, 0)
        self.assertIsNotNone(saved_rating)
        self.assertIsNone(saved_rating.official_id)
        self.assertIsNone(saved_rating.rater_id)
        self.assertIsNotNone(saved_schedule)
        self.assertIsNone(saved_schedule.updated_by)
        self.assertIsNotNone(saved_window)
        self.assertIsNone(saved_window.updated_by)

    def test_bio_can_delete_own_page_and_is_logged_out(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Own Page BIO',
                username='ownpagebio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            resident = self.create_user(
                role='resident',
                full_name='Supporting Resident',
                username='supportresident@test.ph',
                barangay_name='Mabuhay'
            )
            post = Post(author_id=bio.id, content='BIO page post')
            db.session.add(post)
            db.session.commit()
            post_id = post.id

            db.session.add(PostLike(post_id=post_id, user_id=resident.id))
            db.session.add(PushSubscription(
                user_id=bio.id,
                endpoint='https://example.test/push/1',
                p256dh='key',
                auth='auth'
            ))
            db.session.add(WelfareDistribution(
                resident_id=resident.id,
                created_by=bio.id,
                assistance_type='Cash',
                program_name='BIO Aid',
                reference_code='WD-BIO-001'
            ))
            db.session.commit()
            bio_id = bio.id

            self.login_as(bio)
            bio_res = self.app.delete(f'/api/bio/member/{bio_id}')
            dashboard_res = self.app.get('/dashboard')
            bio_data = bio_res.get_json()

            deleted_bio = User.query.get(bio_id)
            deleted_post = Post.query.get(post_id)
            remaining_post_likes = PostLike.query.filter_by(post_id=post_id).count()
            remaining_subscriptions = PushSubscription.query.filter_by(user_id=bio_id).count()
            remaining_welfare = WelfareDistribution.query.filter_by(reference_code='WD-BIO-001').count()

        self.assertEqual(bio_res.status_code, 200)
        self.assertTrue(bio_data['success'])
        self.assertTrue(bio_data['deleted_self'])
        self.assertEqual(dashboard_res.status_code, 302)
        self.assertIsNone(deleted_bio)
        self.assertIsNone(deleted_post)
        self.assertEqual(remaining_post_likes, 0)
        self.assertEqual(remaining_subscriptions, 0)
        self.assertEqual(remaining_welfare, 0)

    def test_bio_can_wipe_entire_barangay_page_and_preserve_other_barangays(self):
        with app.app_context():
            mabuhay_family = Family(class_type='C', size=4)
            san_roque_family = Family(class_type='B', size=3)
            db.session.add_all([mabuhay_family, san_roque_family])
            db.session.commit()

            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='wipebio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            second_bio = self.create_user(
                role='bio',
                full_name='Second BIO',
                username='wipebio2@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            official = self.create_user(
                role='official',
                full_name='Hon. Wipe Official',
                username='wipeofficial@test.ph',
                barangay_name='Mabuhay'
            )
            resident = self.create_user(
                role='resident',
                full_name='Wipe Resident',
                username='wiperesident@test.ph',
                barangay_name='Mabuhay',
                family_id=mabuhay_family.id
            )
            other_bio = self.create_user(
                role='bio',
                full_name='Safe BIO',
                username='safebio@test.ph',
                barangay_name='San Roque',
                is_approved=True
            )
            other_resident = self.create_user(
                role='resident',
                full_name='Safe Resident',
                username='saferesident@test.ph',
                barangay_name='San Roque',
                family_id=san_roque_family.id
            )

            wipe_post = Post(author_id=bio.id, content='Barangay post to wipe')
            safe_post = Post(author_id=other_bio.id, content='Barangay post to keep')
            db.session.add_all([wipe_post, safe_post])
            db.session.commit()

            wipe_post_id = wipe_post.id
            safe_post_id = safe_post.id

            db.session.add_all([
                PostLike(post_id=wipe_post_id, user_id=resident.id),
                PostLike(post_id=safe_post_id, user_id=other_resident.id),
                WelfareDistribution(
                    resident_id=resident.id,
                    family_id=mabuhay_family.id,
                    created_by=official.id,
                    assistance_type='Cash',
                    program_name='Wipe Aid',
                    reference_code='WD-WIPE-001'
                ),
                WelfareDistribution(
                    resident_id=other_resident.id,
                    family_id=san_roque_family.id,
                    created_by=other_bio.id,
                    assistance_type='Rice',
                    program_name='Keep Aid',
                    reference_code='WD-KEEP-001'
                ),
                ReliefDistribution(family_id=mabuhay_family.id, amount=1000),
                ReliefDistribution(family_id=san_roque_family.id, amount=1500),
                Announcement(
                    message='Wipe this announcement',
                    created_by=bio.id,
                    target_user=resident.id,
                    target_users=json.dumps([{'id': resident.id, 'name': resident.full_name}])
                ),
                Announcement(
                    message='Keep this announcement',
                    created_by=other_bio.id,
                    target_user=other_resident.id,
                    target_users=json.dumps([{'id': other_resident.id, 'name': other_resident.full_name}])
                ),
                Event(
                    title='Wipe Event',
                    description='Barangay event',
                    date=datetime(2026, 5, 1, 10, 0, 0),
                    created_by=bio.id
                ),
                Event(
                    title='Keep Event',
                    description='Other barangay event',
                    date=datetime(2026, 5, 2, 10, 0, 0),
                    created_by=other_bio.id
                ),
                FinancialReport(
                    month=5,
                    year=2026,
                    total_funds=100000,
                    relief_distribution=5000,
                    project_expenses=9000,
                    ai_summary='Wipe report',
                    uploaded_by=bio.id
                ),
                FinancialReport(
                    month=5,
                    year=2026,
                    total_funds=120000,
                    relief_distribution=4000,
                    project_expenses=8000,
                    ai_summary='Keep report',
                    uploaded_by=other_bio.id
                ),
                Rating(
                    official_id=official.id,
                    rater_id=resident.id,
                    family_id=mabuhay_family.id,
                    month=5,
                    year=2026,
                    responsiveness=5,
                    fairness=5,
                    service_quality=5,
                    community_involvement=5
                ),
                Rating(
                    official_id=other_bio.id,
                    rater_id=other_resident.id,
                    family_id=san_roque_family.id,
                    month=5,
                    year=2026,
                    responsiveness=4,
                    fairness=4,
                    service_quality=4,
                    community_involvement=4
                ),
                RatingSchedule(
                    barangay_key='mabuhay',
                    barangay_name='Mabuhay',
                    start_month=1,
                    start_day=1,
                    end_month=1,
                    end_day=31,
                    updated_by=official.id
                ),
                RatingSchedule(
                    barangay_key='san-roque',
                    barangay_name='San Roque',
                    start_month=2,
                    start_day=1,
                    end_month=2,
                    end_day=28,
                    updated_by=other_bio.id
                ),
                RatingScheduleWindow(
                    barangay_key='mabuhay',
                    barangay_name='Mabuhay',
                    window_number=1,
                    start_month=1,
                    start_day=1,
                    end_month=1,
                    end_day=31,
                    updated_by=official.id
                ),
                RatingScheduleWindow(
                    barangay_key='san-roque',
                    barangay_name='San Roque',
                    window_number=1,
                    start_month=2,
                    start_day=1,
                    end_month=2,
                    end_day=28,
                    updated_by=other_bio.id
                ),
                Emergency(
                    reported_by=resident.id,
                    type='health',
                    lat=9.0,
                    lng=124.0,
                    purok=1
                ),
                Emergency(
                    reported_by=other_resident.id,
                    type='accident',
                    lat=10.0,
                    lng=125.0,
                    purok=2
                ),
                Summons(
                    resident_id=resident.id,
                    official_id=official.id,
                    reason='Wipe summons'
                ),
                Summons(
                    resident_id=other_resident.id,
                    official_id=other_bio.id,
                    reason='Keep summons'
                ),
                PushSubscription(
                    user_id=bio.id,
                    endpoint='https://example.test/push/wipe',
                    p256dh='wipe-key',
                    auth='wipe-auth'
                ),
                PushSubscription(
                    user_id=other_bio.id,
                    endpoint='https://example.test/push/keep',
                    p256dh='keep-key',
                    auth='keep-auth'
                ),
                HistoryLog(user_id=bio.id, action='Wipe log'),
                HistoryLog(user_id=other_bio.id, action='Keep log'),
            ])
            db.session.commit()

            bio_id = bio.id
            second_bio_id = second_bio.id
            official_id = official.id
            resident_id = resident.id
            other_bio_id = other_bio.id
            other_resident_id = other_resident.id
            mabuhay_family_id = mabuhay_family.id
            san_roque_family_id = san_roque_family.id

            self.login_as(bio)
            wipe_res = self.app.post('/api/bio/barangay/wipe', json={'confirmation_text': 'DELETE Mabuhay'})
            dashboard_res = self.app.get('/dashboard')
            wipe_data = wipe_res.get_json()

            deleted_bio = User.query.get(bio_id)
            deleted_second_bio = User.query.get(second_bio_id)
            deleted_official = User.query.get(official_id)
            deleted_resident = User.query.get(resident_id)
            kept_other_bio = User.query.get(other_bio_id)
            kept_other_resident = User.query.get(other_resident_id)
            deleted_wipe_post = Post.query.get(wipe_post_id)
            kept_safe_post = Post.query.get(safe_post_id)
            remaining_mabuhay_welfare = WelfareDistribution.query.filter_by(reference_code='WD-WIPE-001').count()
            remaining_safe_welfare = WelfareDistribution.query.filter_by(reference_code='WD-KEEP-001').count()
            remaining_mabuhay_relief = ReliefDistribution.query.filter_by(family_id=mabuhay_family_id).count()
            remaining_safe_relief = ReliefDistribution.query.filter_by(family_id=san_roque_family_id).count()
            remaining_mabuhay_announcements = Announcement.query.filter_by(message='Wipe this announcement').count()
            remaining_safe_announcements = Announcement.query.filter_by(message='Keep this announcement').count()
            remaining_mabuhay_events = Event.query.filter_by(title='Wipe Event').count()
            remaining_safe_events = Event.query.filter_by(title='Keep Event').count()
            remaining_mabuhay_reports = FinancialReport.query.filter_by(ai_summary='Wipe report').count()
            remaining_safe_reports = FinancialReport.query.filter_by(ai_summary='Keep report').count()
            remaining_mabuhay_ratings = Rating.query.filter_by(family_id=mabuhay_family_id).count()
            remaining_safe_ratings = Rating.query.filter_by(family_id=san_roque_family_id).count()
            remaining_mabuhay_schedule = RatingSchedule.query.filter_by(barangay_key='mabuhay').count()
            remaining_safe_schedule = RatingSchedule.query.filter_by(barangay_key='san-roque').count()
            remaining_mabuhay_window = RatingScheduleWindow.query.filter_by(barangay_key='mabuhay').count()
            remaining_safe_window = RatingScheduleWindow.query.filter_by(barangay_key='san-roque').count()
            remaining_mabuhay_emergencies = Emergency.query.filter_by(reported_by=resident_id).count()
            remaining_safe_emergencies = Emergency.query.filter_by(reported_by=other_resident_id).count()
            remaining_mabuhay_summons = Summons.query.filter_by(reason='Wipe summons').count()
            remaining_safe_summons = Summons.query.filter_by(reason='Keep summons').count()
            remaining_mabuhay_push = PushSubscription.query.filter_by(user_id=bio_id).count()
            remaining_safe_push = PushSubscription.query.filter_by(user_id=other_bio_id).count()
            remaining_mabuhay_logs = HistoryLog.query.filter_by(action='Wipe log').count()
            remaining_safe_logs = HistoryLog.query.filter_by(action='Keep log').count()
            deleted_mabuhay_family = Family.query.get(mabuhay_family_id)
            kept_san_roque_family = Family.query.get(san_roque_family_id)

        self.assertEqual(wipe_res.status_code, 200)
        self.assertTrue(wipe_data['success'])
        self.assertTrue(wipe_data['deleted_barangay'])
        self.assertEqual(wipe_data['deleted_user_count'], 4)
        self.assertEqual(dashboard_res.status_code, 302)
        self.assertIsNone(deleted_bio)
        self.assertIsNone(deleted_second_bio)
        self.assertIsNone(deleted_official)
        self.assertIsNone(deleted_resident)
        self.assertIsNotNone(kept_other_bio)
        self.assertIsNotNone(kept_other_resident)
        self.assertIsNone(deleted_wipe_post)
        self.assertIsNotNone(kept_safe_post)
        self.assertEqual(remaining_mabuhay_welfare, 0)
        self.assertEqual(remaining_safe_welfare, 1)
        self.assertEqual(remaining_mabuhay_relief, 0)
        self.assertEqual(remaining_safe_relief, 1)
        self.assertEqual(remaining_mabuhay_announcements, 0)
        self.assertEqual(remaining_safe_announcements, 1)
        self.assertEqual(remaining_mabuhay_events, 0)
        self.assertEqual(remaining_safe_events, 1)
        self.assertEqual(remaining_mabuhay_reports, 0)
        self.assertEqual(remaining_safe_reports, 1)
        self.assertEqual(remaining_mabuhay_ratings, 0)
        self.assertEqual(remaining_safe_ratings, 1)
        self.assertEqual(remaining_mabuhay_schedule, 0)
        self.assertEqual(remaining_safe_schedule, 1)
        self.assertEqual(remaining_mabuhay_window, 0)
        self.assertEqual(remaining_safe_window, 1)
        self.assertEqual(remaining_mabuhay_emergencies, 0)
        self.assertEqual(remaining_safe_emergencies, 1)
        self.assertEqual(remaining_mabuhay_summons, 0)
        self.assertEqual(remaining_safe_summons, 1)
        self.assertEqual(remaining_mabuhay_push, 0)
        self.assertEqual(remaining_safe_push, 1)
        self.assertEqual(remaining_mabuhay_logs, 0)
        self.assertEqual(remaining_safe_logs, 1)
        self.assertIsNone(deleted_mabuhay_family)
        self.assertIsNotNone(kept_san_roque_family)

    def test_register_bio_rejects_duplicate_barangay_request(self):
        with app.app_context():
            self.create_user(
                role='bio',
                full_name='Existing BIO',
                username='existingbio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )

        res = self.app.post('/register_bio', json={
            'username': 'newbio@test.ph',
            'full_name': 'New BIO',
            'password': 'secret123',
            'position': 'Secretary',
            'barangay_name': ' mabuhay '
        })

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()['error_code'], 'bio_conflict')
        self.assertIn('already exists', res.get_json()['error'])

    def test_register_bio_allows_different_barangay(self):
        with app.app_context():
            self.create_user(
                role='bio',
                full_name='Existing BIO',
                username='existingbio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )

        res = self.app.post('/register_bio', json={
            'username': 'otherbio@test.ph',
            'full_name': 'Other BIO',
            'password': 'secret123',
            'position': 'Secretary',
            'barangay_name': 'San Roque'
        })

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

    def test_register_bio_rejects_duplicate_name_and_position(self):
        with app.app_context():
            self.create_user(
                role='bio',
                full_name='Maria Dela Cruz',
                username='existingbio@test.ph',
                barangay_name='Mabuhay',
                position='Secretary',
                is_approved=True
            )

        res = self.app.post('/register_bio', json={
            'username': 'mariaduplicate@test.ph',
            'full_name': ' maria dela cruz ',
            'password': 'secret123',
            'position': ' secretary ',
            'barangay_name': 'San Roque'
        })

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()['error_code'], 'bio_conflict')
        self.assertIn('same full name and position', res.get_json()['error'])

    def create_user(self, role='resident', full_name='Test User', username=None, **kwargs):
        self._user_seq += 1
        username = username or f'user{self._user_seq}@test.com'
        user = User(
            username=username,
            password_hash=generate_password_hash('secret123'),
            full_name=full_name,
            role=role,
            **kwargs
        )
        db.session.add(user)
        db.session.commit()
        return user

    def login_as(self, user):
        with self.app.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['role'] = user.role

    def test_search_returns_limited_profile_for_resident_and_tagged_posts(self):
        with app.app_context():
            viewer = self.create_user(role='resident', full_name='Resident Viewer')
            target = self.create_user(role='resident', full_name='Maria Cruz', purok=2, monthly_income=4500)
            author = self.create_user(role='bio', full_name='Barangay BIO')
            db.session.add(Post(
                author_id=author.id,
                content='Please attend the barangay meeting tomorrow.',
                mentions=json.dumps([target.full_name])
            ))
            db.session.commit()

            self.login_as(viewer)
            res = self.app.get('/api/search', query_string={'q': 'Maria'})

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        profile = next(item for item in data['profiles'] if item['id'] == target.id)
        field_labels = {field['label'] for field in profile['fields']}

        self.assertEqual(profile['access_level'], 'limited')
        self.assertNotIn('Username', field_labels)
        self.assertTrue(any('Tagged or mentioned' in post['match_reasons'] for post in data['posts']))

    def test_search_returns_full_profile_for_official_viewer(self):
        with app.app_context():
            viewer = self.create_user(role='official', full_name='Hon. Pedro Santos', position='Councilor')
            target = self.create_user(
                role='resident',
                full_name='Ana Reyes',
                birthdate=date(2000, 5, 17),
                birthplace='Surigao City',
                monthly_income=12500,
                employment_status='employed',
                mother_name='Maria Reyes',
                father_name='Jose Reyes'
            )

            self.login_as(viewer)
            res = self.app.get('/api/search', query_string={'q': 'Ana'})

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        profile = next(item for item in data['profiles'] if item['id'] == target.id)
        field_labels = {field['label'] for field in profile['fields']}

        self.assertEqual(profile['access_level'], 'full')
        self.assertIn('Username', field_labels)
        self.assertIn('Monthly Income', field_labels)
        self.assertIn('Birthdate', field_labels)

    def test_search_matches_post_location(self):
        with app.app_context():
            viewer = self.create_user(role='resident', full_name='Resident Viewer')
            author = self.create_user(role='bio', full_name='Barangay BIO')
            db.session.add(Post(
                author_id=author.id,
                content='Medical mission this Saturday.',
                location='Barangay Hall'
            ))
            db.session.commit()

            self.login_as(viewer)
            res = self.app.get('/api/search', query_string={'q': 'Hall'})

        self.assertEqual(res.status_code, 200)
        posts = res.get_json()['posts']
        self.assertTrue(any('Location match' in post['match_reasons'] for post in posts))

    def test_resident_official_directory_hides_private_fields(self):
        with app.app_context():
            viewer = self.create_user(role='resident', full_name='Resident Viewer')
            official = self.create_user(
                role='official',
                full_name='Hon. Elena Cruz',
                position='Captain',
                birthdate=date(1990, 1, 5),
                monthly_income=30000,
                employment_status='employed',
                lat=9.12345,
                lng=125.54321
            )

            self.login_as(viewer)
            res = self.app.get('/api/officials')

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        item = next(entry for entry in data if entry['id'] == official.id)

        self.assertEqual(item['position'], 'Captain')
        self.assertEqual(item['lat'], 9.12345)
        self.assertEqual(item['lng'], 125.54321)
        self.assertNotIn('birthdate', item)
        self.assertNotIn('monthly_income', item)
        self.assertNotIn('username', item)

    def test_official_can_report_emergency_visible_to_fellow_staff_in_same_barangay(self):
        with app.app_context():
            reporter = self.create_user(
                role='official',
                full_name='Reporting Official',
                username='reportingofficial@test.ph',
                barangay_name='Mabuhay',
                purok=2
            )
            fellow_official = self.create_user(
                role='official',
                full_name='Fellow Official',
                username='fellowofficial@test.ph',
                barangay_name='Mabuhay',
                purok=4
            )
            bio = self.create_user(
                role='bio',
                full_name='Mabuhay BIO',
                username='mabuhaybio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            outsider = self.create_user(
                role='official',
                full_name='Other Barangay Official',
                username='otherbarangayofficial@test.ph',
                barangay_name='San Roque',
                purok=1
            )

            self.login_as(reporter)
            create_res = self.app.post('/api/emergency', json={
                'type': 'accident',
                'lat': 9.1234,
                'lng': 125.5678,
                'purok': 2
            })

            self.login_as(fellow_official)
            official_res = self.app.get('/api/emergency')

            self.login_as(bio)
            bio_res = self.app.get('/api/emergency')

            self.login_as(outsider)
            outsider_res = self.app.get('/api/emergency')

        self.assertEqual(create_res.status_code, 200)
        self.assertTrue(create_res.get_json()['success'])
        self.assertTrue(any(item['reported_by_name'] == 'Reporting Official' for item in official_res.get_json()))
        self.assertTrue(any(item['reported_by_name'] == 'Reporting Official' for item in bio_res.get_json()))
        self.assertFalse(any(item['reported_by_name'] == 'Reporting Official' for item in outsider_res.get_json()))

    def test_emergency_endpoints_disable_caching(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Emergency BIO',
                username='emergencybio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )

            self.login_as(bio)
            active_res = self.app.get('/api/emergency')
            history_res = self.app.get('/api/emergency/history')

        self.assertEqual(active_res.status_code, 200)
        self.assertEqual(history_res.status_code, 200)
        self.assertIn('no-store', active_res.headers.get('Cache-Control', ''))
        self.assertIn('no-cache', active_res.headers.get('Cache-Control', ''))
        self.assertIn('no-store', history_res.headers.get('Cache-Control', ''))
        self.assertIn('no-cache', history_res.headers.get('Cache-Control', ''))

    def test_bio_can_open_wipe_confirmation_page(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Wipe BIO',
                username='wipe-page-bio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            self.login_as(bio)
            res = self.app.get('/bio/barangay/wipe')

        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('Delete Entire Barangay Page', html)
        self.assertIn('DELETE Mabuhay', html)

    def test_bio_can_submit_wipe_confirmation_form(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Form BIO',
                username='form-bio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            self.create_user(
                role='resident',
                full_name='Form Resident',
                username='form-resident@test.ph',
                barangay_name='Mabuhay',
                purok=1
            )
            outsider = self.create_user(
                role='resident',
                full_name='Safe Resident',
                username='safe-resident@test.ph',
                barangay_name='San Roque',
                purok=2
            )

            self.login_as(bio)
            res = self.app.post('/bio/barangay/wipe', data={'confirmation_text': 'DELETE Mabuhay'})

            remaining_barangay_users = User.query.filter_by(barangay_name='Mabuhay').count()
            outsider_still_exists = User.query.get(outsider.id)

        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))
        self.assertEqual(remaining_barangay_users, 0)
        self.assertIsNotNone(outsider_still_exists)

    def test_emergency_analysis_includes_ai_health_risk_profiles_for_bio(self):
        with app.app_context():
            bio = self.create_user(role='bio', full_name='Barangay BIO', is_approved=True)
            family = Family(class_type='D', size=6, health_risk_score=8.0)
            db.session.add(family)
            db.session.commit()
            resident = self.create_user(
                role='resident',
                full_name='Elder Resident',
                birthdate=date(1950, 1, 1),
                monthly_income=1500,
                family_id=family.id,
                purok=3
            )
            db.session.add(Emergency(reported_by=resident.id, type='health', lat=9.1, lng=125.1, purok=3))
            db.session.add(Emergency(reported_by=resident.id, type='health', lat=9.1004, lng=125.1004, purok=3))
            db.session.commit()

            self.login_as(bio)
            res = self.app.get('/api/emergency/analysis', query_string={'type': 'health'})

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('incident_patterns', data)
        self.assertIn('health_risks', data)
        self.assertIn('incident_summary', data)
        self.assertIn('health_summary', data)
        self.assertIn('risk_overview', data)
        self.assertIn('recommendations', data)
        self.assertIn('analysis_metadata', data)
        self.assertEqual(data['incident_patterns']['total_records'], 2)
        self.assertGreaterEqual(data['risk_overview']['flagged_residents'], 1)
        self.assertGreaterEqual(data['risk_overview']['high_or_critical'], 1)
        self.assertTrue(data['recommendations'])
        self.assertEqual(data['analysis_metadata']['runtime_model'], 'community_risk_model')
        self.assertEqual(data['health_risks'][0]['full_name'], 'Elder Resident')
        self.assertIn(data['health_risks'][0]['risk_level'], ['high', 'critical'])
        self.assertIn('Potential health risks', data['insight'])

    def test_emergency_analysis_hides_health_risk_names_for_resident(self):
        with app.app_context():
            viewer = self.create_user(role='resident', full_name='Resident Viewer')
            family = Family(class_type='D', size=6, health_risk_score=8.0)
            db.session.add(family)
            db.session.commit()
            resident = self.create_user(
                role='resident',
                full_name='Private Risk Resident',
                birthdate=date(1950, 1, 1),
                monthly_income=1500,
                family_id=family.id,
                purok=4
            )
            db.session.add(Emergency(reported_by=resident.id, type='health', lat=9.2, lng=125.2, purok=4))
            db.session.add(Emergency(reported_by=resident.id, type='health', lat=9.2004, lng=125.2004, purok=4))
            db.session.commit()

            self.login_as(viewer)
            res = self.app.get('/api/emergency/analysis', query_string={'type': 'health'})

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['health_risks'])
        self.assertIn('risk_overview', data)
        self.assertIn('recommendations', data)
        self.assertGreaterEqual(data['risk_overview']['flagged_residents'], 1)
        self.assertTrue(data['recommendations'])
        self.assertNotIn('full_name', data['health_risks'][0])
        self.assertNotIn('Private Risk Resident', data['insight'])

    def test_emergency_analysis_scopes_results_to_registered_barangay_and_returns_predictive_fields(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='San Roque BIO',
                username='sanroquebio@test.ph',
                barangay_name='San Roque',
                is_approved=True
            )
            local_family = Family(class_type='D', size=5, health_risk_score=6.5)
            other_family = Family(class_type='C', size=4, health_risk_score=2.0)
            db.session.add_all([local_family, other_family])
            db.session.commit()

            local_resident = self.create_user(
                role='resident',
                full_name='Local Resident',
                username='localresident@test.ph',
                barangay_name='San Roque',
                family_id=local_family.id,
                monthly_income=2500,
                purok=2,
                lat=9.1010,
                lng=125.1010
            )
            other_resident = self.create_user(
                role='resident',
                full_name='Other Barangay Resident',
                username='otherbarangayresident@test.ph',
                barangay_name='Mabuhay',
                family_id=other_family.id,
                monthly_income=9000,
                purok=8,
                lat=9.3010,
                lng=125.3010
            )

            db.session.add_all([
                Emergency(reported_by=local_resident.id, type='accident', lat=9.1012, lng=125.1012, purok=2),
                Emergency(reported_by=local_resident.id, type='accident', lat=9.1015, lng=125.1015, purok=2),
                Emergency(reported_by=other_resident.id, type='health', lat=9.3012, lng=125.3012, purok=8),
                Emergency(reported_by=other_resident.id, type='health', lat=9.3015, lng=125.3015, purok=8),
                Emergency(reported_by=other_resident.id, type='health', lat=9.3018, lng=125.3018, purok=8),
            ])
            db.session.commit()

            self.login_as(bio)
            res = self.app.get('/api/emergency/analysis')

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['analysis_metadata']['barangay_name'], 'San Roque')
        self.assertEqual(data['incident_patterns']['total_records'], 2)
        self.assertEqual(data['incident_patterns']['type_counts'], {'accident': 2})
        self.assertEqual(data['barangay_profile']['resident_count'], 1)
        self.assertTrue(data['map_risk_signals'])
        self.assertTrue(data['predictive_alerts'])
        self.assertIn('watch zone', data['map_risk_summary'].lower())

    def test_emergency_analysis_iteration_changes_wording_but_keeps_same_barangay_data_scope(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Variant BIO',
                username='variantbio@test.ph',
                barangay_name='San Roque',
                is_approved=True
            )
            family = Family(class_type='D', size=5, health_risk_score=7.5)
            db.session.add(family)
            db.session.commit()

            resident = self.create_user(
                role='resident',
                full_name='Variant Resident',
                username='variantresident@test.ph',
                barangay_name='San Roque',
                family_id=family.id,
                monthly_income=2200,
                purok=3,
                lat=9.1450,
                lng=125.1450
            )

            db.session.add_all([
                Emergency(reported_by=resident.id, type='health', lat=9.1451, lng=125.1451, purok=3),
                Emergency(reported_by=resident.id, type='health', lat=9.1454, lng=125.1454, purok=3),
                Emergency(reported_by=resident.id, type='health', lat=9.1457, lng=125.1457, purok=3),
            ])
            db.session.commit()

            self.login_as(bio)
            first_res = self.app.get('/api/emergency/analysis', query_string={'type': 'health', 'iteration': 0})
            second_res = self.app.get('/api/emergency/analysis', query_string={'type': 'health', 'iteration': 1})

        self.assertEqual(first_res.status_code, 200)
        self.assertEqual(second_res.status_code, 200)
        first_payload = first_res.get_json()
        second_payload = second_res.get_json()

        self.assertEqual(first_payload['incident_patterns']['total_records'], second_payload['incident_patterns']['total_records'])
        self.assertEqual(first_payload['risk_overview'], second_payload['risk_overview'])
        self.assertEqual(first_payload['analysis_metadata']['barangay_name'], 'San Roque')
        self.assertEqual(second_payload['analysis_metadata']['barangay_name'], 'San Roque')
        self.assertEqual(first_payload['analysis_metadata']['analysis_variant'], 1)
        self.assertEqual(second_payload['analysis_metadata']['analysis_variant'], 2)
        self.assertNotEqual(first_payload['incident_summary'], second_payload['incident_summary'])
        self.assertNotEqual(first_payload['health_summary'], second_payload['health_summary'])
        self.assertNotEqual(first_payload['recommendations'], second_payload['recommendations'])

    def test_relief_calculator_rotates_ai_strategy_and_scopes_families_to_barangay(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Calculator BIO',
                username='calculatorbio@test.ph',
                barangay_name='San Roque',
                is_approved=True
            )
            family_one = Family(class_type='D', size=6, health_risk_score=8.0, past_aid_received=0)
            family_two = Family(class_type='C', size=3, health_risk_score=2.5, past_aid_received=400)
            other_family = Family(class_type='D', size=5, health_risk_score=7.0, past_aid_received=0)
            db.session.add_all([family_one, family_two, other_family])
            db.session.commit()

            resident_one = self.create_user(
                role='resident',
                full_name='Priority Household',
                username='priorityhousehold@test.ph',
                barangay_name='San Roque',
                family_id=family_one.id,
                monthly_income=1800,
                purok=1,
                lat=9.1100,
                lng=125.1100
            )
            self.create_user(
                role='resident',
                full_name='Secondary Household',
                username='secondaryhousehold@test.ph',
                barangay_name='San Roque',
                family_id=family_two.id,
                monthly_income=9500,
                purok=2,
                lat=9.1200,
                lng=125.1200
            )
            other_resident = self.create_user(
                role='resident',
                full_name='Outside Household',
                username='outsidehousehold@test.ph',
                barangay_name='Mabuhay',
                family_id=other_family.id,
                monthly_income=1200,
                purok=7,
                lat=9.3100,
                lng=125.3100
            )

            db.session.add_all([
                Emergency(reported_by=resident_one.id, type='accident', lat=9.1101, lng=125.1101, purok=1),
                Emergency(reported_by=resident_one.id, type='accident', lat=9.1104, lng=125.1104, purok=1),
                Emergency(reported_by=other_resident.id, type='health', lat=9.3101, lng=125.3101, purok=7),
                Emergency(reported_by=other_resident.id, type='health', lat=9.3104, lng=125.3104, purok=7),
            ])
            db.session.commit()

            self.login_as(bio)
            first_res = self.app.post('/api/relief/calculate', json={'budget': 12000, 'iteration': 0})
            second_res = self.app.post('/api/relief/calculate', json={'budget': 12000, 'iteration': 1})

        self.assertEqual(first_res.status_code, 200)
        self.assertEqual(second_res.status_code, 200)
        first_payload = first_res.get_json()
        second_payload = second_res.get_json()

        self.assertTrue(first_payload['success'])
        self.assertTrue(second_payload['success'])
        self.assertNotEqual(first_payload['strategy']['code'], second_payload['strategy']['code'])
        self.assertNotEqual(first_payload['allocations'], second_payload['allocations'])
        self.assertEqual(first_payload['analysis_metadata']['barangay_name'], 'San Roque')
        self.assertEqual(first_payload['analysis_metadata']['calculation_mode'], 'class_randomized_only')
        first_family_ids = {row['family_id'] for row in first_payload['allocations']}
        self.assertIn(family_one.id, first_family_ids)
        self.assertIn(family_two.id, first_family_ids)
        self.assertNotIn(other_family.id, first_family_ids)
        self.assertTrue(first_payload['ai_summary'])
        self.assertTrue(first_payload['ai_recommendation'])
        self.assertNotIn('predictive', first_payload['ai_summary'].lower())
        self.assertNotIn('incident', first_payload['ai_summary'].lower())
        self.assertNotIn('predictive', first_payload['ai_recommendation'].lower())

    def test_health_model_trainer_writes_real_model_artifacts(self):
        with app.app_context():
            family = Family(class_type='D', size=5, health_risk_score=7.0)
            db.session.add(family)
            db.session.commit()

            resident = self.create_user(
                role='resident',
                full_name='Model Resident',
                username='modelresident@test.ph',
                barangay_name='San Roque',
                family_id=family.id,
                birthdate=date(1960, 1, 1),
                monthly_income=2200
            )
            db.session.add_all([
                Emergency(reported_by=resident.id, type='health', lat=9.1, lng=125.1, purok=1),
                Emergency(reported_by=resident.id, type='health', lat=9.1003, lng=125.1003, purok=1),
            ])
            db.session.commit()

        temp_dir = Path(tempfile.mkdtemp())
        model_path = temp_dir / 'health_risk_model.joblib'
        metadata_path = temp_dir / 'health_risk_model.json'

        metadata = train_health_model_artifact(
            db_path=TEST_DB_PATH,
            output_model_path=model_path,
            output_metadata_path=metadata_path,
        )

        self.assertTrue(model_path.exists())
        self.assertTrue(metadata_path.exists())
        self.assertEqual(metadata['model_type'], 'RandomForestClassifier')
        self.assertEqual(metadata['target'], 'health_risk')
        self.assertIn('incident_count', metadata['features'])
        self.assertGreater(metadata['training_rows'], 0)

    def test_bio_post_can_update_and_clear_mentions_and_location(self):
        with app.app_context():
            bio = self.create_user(role='bio', full_name='Barangay BIO', is_approved=True)
            resident = self.create_user(role='resident', full_name='Maria Cruz')
            official = self.create_user(role='official', full_name='Hon. Pedro Santos')

            self.login_as(bio)
            create_res = self.app.post('/api/posts', json={
                'content': 'Community update',
                'media_urls': [],
                'mentions': [
                    {'id': resident.id, 'name': resident.full_name},
                    {'id': official.id, 'name': official.full_name}
                ],
                'location': 'Barangay Hall'
            })

            self.assertEqual(create_res.status_code, 200)
            self.assertTrue(create_res.get_json()['success'])

            posts_before = self.app.get('/api/posts').get_json()
            created_post = next(post for post in posts_before if post['content'] == 'Community update')
            post_id = created_post['id']
            self.assertEqual(created_post['author_id'], bio.id)
            self.assertEqual(created_post['mention_names'], [resident.full_name, official.full_name])
            self.assertEqual(created_post['mentions'][0]['id'], resident.id)
            self.assertEqual(created_post['location'], 'Barangay Hall')

            update_res = self.app.put(f'/api/posts/{post_id}', json={
                'content': 'Community update edited',
                'media_urls': [],
                'mentions': [],
                'location': None,
                'image_url': None
            })

            self.assertEqual(update_res.status_code, 200)
            self.assertTrue(update_res.get_json()['success'])

            posts_after = self.app.get('/api/posts').get_json()
            updated_post = next(post for post in posts_after if post['id'] == post_id)
            self.assertEqual(updated_post['mentions'], [])
            self.assertEqual(updated_post['mention_names'], [])
            self.assertIsNone(updated_post['location'])

    def test_bio_can_delete_post_with_likes(self):
        with app.app_context():
            bio = self.create_user(role='bio', full_name='Barangay BIO', is_approved=True)
            resident = self.create_user(role='resident', full_name='Resident Liker')
            post = Post(author_id=bio.id, content='Delete this post')
            db.session.add(post)
            db.session.commit()
            post_id = post.id

            self.login_as(resident)
            like_res = self.app.post(f'/api/posts/{post_id}/like')

            self.assertEqual(like_res.status_code, 200)
            self.assertTrue(like_res.get_json()['success'])
            self.assertEqual(PostLike.query.filter_by(post_id=post_id).count(), 1)

            self.login_as(bio)
            delete_res = self.app.delete(f'/api/posts/{post_id}')

            self.assertEqual(delete_res.status_code, 200)
            self.assertTrue(delete_res.get_json()['success'])
            self.assertIsNone(Post.query.get(post_id))
            self.assertEqual(PostLike.query.filter_by(post_id=post_id).count(), 0)

    def test_bio_can_promote_same_barangay_official_to_bio(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='bio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            official = self.create_user(
                role='official',
                full_name='Hon. Pedro Santos',
                username='official@test.ph',
                barangay_name='Mabuhay',
                position='Councilor'
            )

            self.login_as(bio)
            res = self.app.put(f'/api/bio/member/{official.id}', json={'role': 'bio'})

            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.get_json()['success'])

            updated = User.query.get(official.id)
            self.assertEqual(updated.role, 'bio')
            self.assertTrue(updated.is_approved)
            self.assertEqual(updated.barangay_name, 'Mabuhay')

    def test_bio_can_register_additional_bio_from_add_member_flow(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='bio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )

            self.login_as(bio)
            res = self.app.post('/api/bio/member', json={
                'full_name': 'Hon. Liza Ramos',
                'username': 'lizabio@test.ph',
                'password': 'secret123',
                'role': 'bio',
                'position': 'Councilor',
                'purok': 2,
                'monthly_income': 15000
            })

            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.get_json()['success'])

            created = User.query.filter_by(username='lizabio@test.ph').first()
            self.assertIsNotNone(created)
            self.assertEqual(created.role, 'bio')
            self.assertTrue(created.is_approved)
            self.assertEqual(created.barangay_name, 'Mabuhay')
            self.assertEqual(created.position, 'Councilor')
            self.assertIsNone(created.family_id)

    def test_bio_cannot_promote_resident_to_bio(self):
        with app.app_context():
            bio = self.create_user(
                role='bio',
                full_name='Barangay BIO',
                username='bio@test.ph',
                barangay_name='Mabuhay',
                is_approved=True
            )
            resident = self.create_user(
                role='resident',
                full_name='Maria Cruz',
                username='resident@test.ph',
                barangay_name='Mabuhay'
            )

            self.login_as(bio)
            res = self.app.put(f'/api/bio/member/{resident.id}', json={'role': 'bio'})

        self.assertEqual(res.status_code, 400)
        self.assertIn('Only an official', res.get_json()['error'])

if __name__ == '__main__':
    unittest.main()
