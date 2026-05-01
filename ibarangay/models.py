from flask_sqlalchemy import SQLAlchemy
from time_utils import utc_now

db = SQLAlchemy()

class Family(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_type = db.Column(db.String(10), nullable=False) # A, B, C, D
    size = db.Column(db.Integer, default=1)
    health_risk_score = db.Column(db.Float, default=0.0) # 0.0 to 10.0
    past_aid_received = db.Column(db.Float, default=0.0)
    users = db.relationship('User', backref='family', lazy=True)
    ratings = db.relationship('Rating', backref='family', lazy=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True) # 'superadmin', 'bio', 'official', 'resident'
    is_approved = db.Column(db.Boolean, default=True) # Used to check if BIO is approved
    purok = db.Column(db.Integer, nullable=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=True)
    is_rater = db.Column(db.Boolean, default=False)
    birthdate = db.Column(db.Date, nullable=True)
    birthplace = db.Column(db.String(100), nullable=True)
    monthly_income = db.Column(db.Float, default=0.0)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    pic_url = db.Column(db.String(500), nullable=True)
    barangay_name = db.Column(db.String(100), nullable=True)
    position = db.Column(db.String(100), nullable=True)
    mother_name = db.Column(db.String(100), nullable=True)
    father_name = db.Column(db.String(100), nullable=True)
    employment_status = db.Column(db.String(50), nullable=True)
    warning_count = db.Column(db.Integer, default=0)
    banned_until = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    date = db.Column(db.DateTime, nullable=False) # applies to past, present or future
    type = db.Column(db.String(20), default="event") # 'achievement' or 'event' 
    target_purok = db.Column(db.Integer, nullable=True) # None means all
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))

class FinancialReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    total_funds = db.Column(db.Float, nullable=False)
    relief_distribution = db.Column(db.Float, nullable=False)
    project_expenses = db.Column(db.Float, nullable=False)
    ai_summary = db.Column(db.Text, nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))

class ReliefDistribution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'))
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=utc_now)

class WelfareDistribution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=True, index=True)
    assistance_type = db.Column(db.String(80), nullable=False)
    program_name = db.Column(db.String(120), nullable=True)
    reference_code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    amount = db.Column(db.Float, default=0.0)
    quantity = db.Column(db.Float, default=1.0)
    unit = db.Column(db.String(40), nullable=True)
    status = db.Column(db.String(20), default='planned', index=True)
    source_funds = db.Column(db.String(120), nullable=True)
    distributed_on = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    resident = db.relationship('User', foreign_keys=[resident_id], backref=db.backref('welfare_records', lazy=True))
    family = db.relationship('Family', foreign_keys=[family_id], backref=db.backref('welfare_distributions', lazy=True))
    creator = db.relationship('User', foreign_keys=[created_by], backref=db.backref('created_welfare_records', lazy=True))

class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    target_purok = db.Column(db.Integer, nullable=True)
    target_puroks = db.Column(db.Text, nullable=True) # JSON list of selected puroks; empty means all
    target_user = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Specific resident target
    target_users = db.Column(db.Text, nullable=True) # JSON list of selected target users by name/id
    target_lat = db.Column(db.Float, nullable=True)
    target_lng = db.Column(db.Float, nullable=True)
    date_posted = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500), nullable=True) # Legacy single image
    media_urls = db.Column(db.Text, nullable=True) # JSON string of multiple images/videos
    mentions = db.Column(db.Text, nullable=True) # JSON string of tagged user IDs
    location = db.Column(db.String(255), nullable=True) # Check-in location string
    timestamp = db.Column(db.DateTime, default=utc_now, index=True)
    author = db.relationship('User', backref=db.backref('posts', lazy=True))

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=True)
    official_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    rater_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    responsiveness = db.Column(db.Integer, nullable=False)
    fairness = db.Column(db.Integer, nullable=False)
    service_quality = db.Column(db.Integer, nullable=False)
    community_involvement = db.Column(db.Integer, nullable=False)
    feedback_text = db.Column(db.Text, nullable=True)

class RatingSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    barangay_key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    barangay_name = db.Column(db.String(100), nullable=False)
    start_month = db.Column(db.Integer, nullable=False)
    start_day = db.Column(db.Integer, nullable=False)
    end_month = db.Column(db.Integer, nullable=False)
    end_day = db.Column(db.Integer, nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

class RatingScheduleWindow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    barangay_key = db.Column(db.String(120), nullable=False, index=True)
    barangay_name = db.Column(db.String(100), nullable=False)
    window_number = db.Column(db.Integer, nullable=False)
    start_month = db.Column(db.Integer, nullable=False)
    start_day = db.Column(db.Integer, nullable=False)
    end_month = db.Column(db.Integer, nullable=False)
    end_day = db.Column(db.Integer, nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

class Emergency(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reported_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    type = db.Column(db.String(50), nullable=False) # 'accident', 'health'
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    purok = db.Column(db.Integer, nullable=True)
    timestamp = db.Column(db.DateTime, default=utc_now)
    acknowledged = db.Column(db.Boolean, default=False)

class Summons(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    official_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    reason = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=utc_now)
    acknowledged = db.Column(db.Boolean, default=False)

class PostLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=utc_now)
    
    post = db.relationship('Post', backref=db.backref('likes', lazy=True))
    user = db.relationship('User', backref=db.backref('liked_posts', lazy=True))

class HistoryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=utc_now)


class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    endpoint = db.Column(db.Text, unique=True, nullable=False)
    p256dh = db.Column(db.String(255), nullable=False)
    auth = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    user = db.relationship('User', backref=db.backref('push_subscriptions', lazy=True))
