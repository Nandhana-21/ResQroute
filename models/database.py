"""SQLAlchemy models (SQLite)."""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # hashed, never plain text
    role = db.Column(db.String(20), nullable=False)       # patient|driver|hospital|admin

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    age = db.Column(db.Integer)
    emergency_contact = db.Column(db.String(120), default="")

class Hospital(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    name = db.Column(db.String(120), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    emergency_available = db.Column(db.Boolean, default=True)
    emergency_beds = db.Column(db.Integer, default=0)
    readiness = db.Column(db.String(20), default="Ready")  # Ready|Preparing|Full

class Ambulance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    vehicle_number = db.Column(db.String(30), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    availability = db.Column(db.String(30), default="Available")
    capability = db.Column(db.String(20), default="Basic")  # Basic|Advanced

class Emergency(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    name = db.Column(db.String(80)); age = db.Column(db.Integer)
    symptoms = db.Column(db.Text, nullable=False)
    emergency_type = db.Column(db.String(40))
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    severity = db.Column(db.String(12)); confidence = db.Column(db.Float); reason = db.Column(db.Text)
    status = db.Column(db.String(20), default="pending")
    notes = db.Column(db.Text, default=""); contact = db.Column(db.String(120), default="")
    preferred_hospital_id = db.Column(db.Integer)
    demo = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    emergency_id = db.Column(db.Integer, db.ForeignKey("emergency.id"), nullable=False)
    ambulance_id = db.Column(db.Integer, db.ForeignKey("ambulance.id"))
    hospital_id = db.Column(db.Integer, db.ForeignKey("hospital.id"))
    assigned_at = db.Column(db.DateTime, default=datetime.now)
    accepted_at = db.Column(db.DateTime)
    pickup_time = db.Column(db.DateTime); arrival_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default="pending")
    rejected = db.Column(db.String(100), default="")
    amb_eta = db.Column(db.Float, default=0); amb_dist = db.Column(db.Float, default=0)
    amb_why = db.Column(db.Text, default=""); hosp_why = db.Column(db.Text, default="")
    candidates = db.Column(db.Text, default="[]")

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    read_status = db.Column(db.Boolean, default=False)
