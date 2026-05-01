from app import app
from models import db, User, Family

def calculate_class(income):
    if income > 30000: return 'A'
    if income > 20000: return 'B'
    if income > 10000: return 'C'
    return 'D'

with app.app_context():
    users = User.query.all()
    for u in users:
        if u.family:
            u.family.class_type = calculate_class(u.monthly_income)
    db.session.commit()
    print("Updated all existing family classes based on member income.")
