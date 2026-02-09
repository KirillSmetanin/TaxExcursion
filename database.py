from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Booking(db.Model):
    __tablename__ = 'bookings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(100))
    school_name = db.Column(db.String(200), nullable=False)
    class_number = db.Column(db.String(20), nullable=False)
    class_profile = db.Column(db.String(100))
    excursion_date = db.Column(db.Date, nullable=False)
    contact_person = db.Column(db.String(200), nullable=False)
    contact_phone = db.Column(db.String(20), nullable=False)
    participants_count = db.Column(db.Integer, nullable=False)
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)