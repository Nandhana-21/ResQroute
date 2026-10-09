"""ResQRoute - AI-assisted emergency coordination PROTOTYPE. Run: python app.py"""
import os, math, random, re, json, secrets
from collections import Counter
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, session, redirect, jsonify, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from models.database import db, User, Patient, Hospital, Ambulance, Emergency, Assignment, Notification
from models.ml_model import predict

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE, "database", "resqroute.db"))
TYPES = ["Accident","Chest pain","Breathing difficulty","Stroke symptoms","Unconsciousness","Severe bleeding","Pregnancy emergency","Other"]
ACTIVE = ["pending","accepted","on_the_way","arrived","picked_up"]
NEXT = {"accepted":"on_the_way","on_the_way":"arrived","arrived":"picked_up","picked_up":"completed"}
AVAIL = {"accepted":"Assigned","on_the_way":"On the way","arrived":"Arrived","picked_up":"Patient picked up","completed":"Available"}
CENTER = (float(os.environ.get("CENTER_LAT", 11.0168)), float(os.environ.get("CENTER_LNG", 76.9558)))  # fictional data placed around this point

app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"), SQLALCHEMY_DATABASE_URI="sqlite:///" + DB_PATH,
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
db.init_app(app)

# ---------- helpers ----------
def hav(a, b, c, d):
    p = math.radians; x = math.sin(p(c-a)/2)**2 + math.cos(p(a))*math.cos(p(c))*math.sin(p(d-b)/2)**2
    return 2*6371*math.asin(math.sqrt(x))
def eta(km): return round(max(1.0, km*1.3/40*60), 1)   # 1.3 road factor, 40 km/h urban average
def clean(s, n=300): return re.sub(r"[<>]", "", str(s or "")).strip()[:n]
def me(): return db.session.get(User, session["uid"]) if "uid" in session else None
def notify(uid, msg):
    if uid: db.session.add(Notification(user_id=uid, message=msg))
def guard(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = me(); api = request.path.startswith("/api")
            if not u: return (jsonify(error="Login required"), 401) if api else redirect("/login")
            if roles and u.role not in roles: return (jsonify(error="Forbidden"), 403) if api else redirect("/")
            return f(u, *a, **k)
        return w
    return deco
def ts(d): return d.strftime("%d %b %H:%M") if d else ""

# ---------- smart allocation ----------
def rank_amb(lat, lng, sev, exclude=()):
    out = []
    for a in Ambulance.query.filter_by(availability="Available"):
        if a.id in exclude: continue
        d = hav(lat, lng, a.latitude, a.longitude); t = eta(d); adv = a.capability == "Advanced"
        pen = 6 if (sev == "CRITICAL" and not adv) else 2 if (sev == "HIGH" and not adv) else 0
        out.append(dict(id=a.id, vehicle=a.vehicle_number, capability=a.capability, dist=round(d, 1), eta=t, score=round(t + pen, 1)))
    return sorted(out, key=lambda x: x["score"])
def rank_hosp(lat, lng, pref=None):
    out = []
    for h in Hospital.query:
        d = hav(lat, lng, h.latitude, h.longitude); t = eta(d); ok = bool(h.emergency_available and h.emergency_beds > 0 and h.readiness != "Full")
        s = t - min(h.emergency_beds, 5)*0.8 - (2 if h.readiness == "Ready" else 0) - (3 if pref == h.id else 0) + (0 if ok else 999)
        out.append(dict(id=h.id, name=h.name, dist=round(d, 1), eta=t, beds=h.emergency_beds, available=ok, readiness=h.readiness, score=round(s, 1)))
    return sorted(out, key=lambda x: x["score"])

def assign(e, a=None):
    """Pick the best ambulance (and hospital on first call). Returns assignment or None."""
    excl = [int(x) for x in (a.rejected if a else "").split(",") if x]
    ranked = rank_amb(e.latitude, e.longitude, e.severity, excl)
    if not ranked:
        e.status = "waiting"; return None
    best = ranked[0]; amb = db.session.get(Ambulance, best["id"]); closest = min(ranked, key=lambda x: x["dist"])
    why = f"{best['vehicle']} selected: {best['dist']} km away, ETA {best['eta']} min, {best['capability']} equipment."
    if best["id"] != closest["id"]:
        why += f" Preferred over closer {closest['vehicle']} ({closest['dist']} km, {closest['capability']}) because the case is {e.severity} and needs better-equipped crew."
    elif e.severity == "CRITICAL" and best["capability"] == "Advanced":
        why += " Closest unit AND advanced life-support capable, ideal for a CRITICAL case."
    if not a:
        a = Assignment(emergency_id=e.id, rejected="")
        hs = rank_hosp(e.latitude, e.longitude, e.preferred_hospital_id)
        if hs and hs[0]["available"]:
            h = hs[0]; a.hospital_id = h["id"]
            a.hosp_why = f"{h['name']}: ETA {h['eta']} min, {h['dist']} km, {h['beds']} emergency beds, readiness {h['readiness']}."
            if e.preferred_hospital_id == h["id"]: a.hosp_why += " Matches the patient's preferred hospital."
            if len(hs) > 1: a.hosp_why += f" Ranked above {hs[1]['name']} on travel time, bed availability and readiness."
        db.session.add(a)
    a.ambulance_id = amb.id; a.amb_eta = best["eta"]; a.amb_dist = best["dist"]; a.amb_why = why
    a.candidates = json.dumps(ranked[:4]); a.status = "pending"; a.assigned_at = datetime.now()
    amb.availability = "Requested"; e.status = "pending"
    notify(amb.driver_id, f"NEW EMERGENCY [{e.severity}] {e.emergency_type} - you are the best-matched available driver, patient {best['dist']} km away. Open your dashboard to accept and see the route.")
    return a

def patient_user(e): return db.session.get(Patient, e.patient_id).user_id
def accept(a, e):
    amb = db.session.get(Ambulance, a.ambulance_id); h = db.session.get(Hospital, a.hospital_id) if a.hospital_id else None
    a.status = e.status = "accepted"; a.accepted_at = datetime.now(); amb.availability = "Assigned"
    notify(patient_user(e), f"Driver accepted. Ambulance {amb.vehicle_number} is assigned (ETA {a.amb_eta} min).")
    if h:
        notify(patient_user(e), f"Hospital selected: {h.name}.")
        notify(h.user_id, f"INCOMING EMERGENCY [{e.severity}] {e.emergency_type} - ambulance {amb.vehicle_number}, ETA to hospital ~{round(a.amb_eta + eta(hav(e.latitude, e.longitude, h.latitude, h.longitude)), 1)} min.")
    if e.contact: notify(patient_user(e), f"EMERGENCY ALERT (simulated message to {e.contact}): {e.name}'s ambulance request [{e.severity}] is assigned to {amb.vehicle_number}.")
def set_status(a, e, new):
    amb = db.session.get(Ambulance, a.ambulance_id); h = db.session.get(Hospital, a.hospital_id) if a.hospital_id else None
    a.status = e.status = new; amb.availability = AVAIL[new]; pu = patient_user(e)
    if new == "on_the_way": notify(pu, "Ambulance is on the way to you.")
    if new == "arrived": notify(pu, "Ambulance is arriving / has arrived at your location.")
    if new == "picked_up":
        a.pickup_time = datetime.now(); notify(pu, "Patient picked up. Heading to hospital.")
        if h: notify(h.user_id, f"Patient picked up ({e.severity}). Updated ETA ~{eta(hav(amb.latitude, amb.longitude, h.latitude, h.longitude))} min.")
    if new == "completed":
        a.arrival_time = datetime.now(); amb.availability = "Available"
        notify(pu, f"Arrived at hospital{' ' + h.name if h else ''}. Emergency completed and saved to history.")
        if h: h.emergency_beds = max(0, h.emergency_beds - 1); notify(h.user_id, "Patient has arrived at the emergency department.")

def tick(a, e, auto, pos=None, final=False):
    """Simulated GPS. `pos` = point along the real road route (computed in the browser via OSRM); falls back to straight-line."""
    amb = db.session.get(Ambulance, a.ambulance_id); h = db.session.get(Hospital, a.hospital_id) if a.hospital_id else None; st = a.status
    if st == "pending" and auto: return accept(a, e)
    if st == "accepted" and auto: return set_status(a, e, "on_the_way")
    if st == "arrived" and auto: return set_status(a, e, "picked_up")
    if st in ("on_the_way", "picked_up"):
        tl, tg = (e.latitude, e.longitude) if st == "on_the_way" else ((h.latitude, h.longitude) if h else (amb.latitude, amb.longitude))
        ok = bool(pos) and hav(amb.latitude, amb.longitude, pos[0], pos[1]) <= 25
        d = hav(amb.latitude, amb.longitude, tl, tg)
        if ok: amb.latitude, amb.longitude = pos
        elif d > 0.2:
            f = min(1, max(0.35, d*0.3)/d); amb.latitude += (tl-amb.latitude)*f; amb.longitude += (tg-amb.longitude)*f
        d = hav(amb.latitude, amb.longitude, tl, tg)
        if (final and ok) or d <= 0.2:
            amb.latitude, amb.longitude = tl, tg
            if auto: set_status(a, e, "arrived" if st == "on_the_way" else "completed")

def score(e, a, h):
    secs = ((a.accepted_at or datetime.now()) - e.created_at).total_seconds(); amb = db.session.get(Ambulance, a.ambulance_id)
    adv = amb.capability == "Advanced"
    items = [("Assignment time", min(20, secs/6), f"{secs:.0f}s from request to driver acceptance (max -20)"),
             ("ETA", min(25, a.amb_eta*1.5), f"{a.amb_eta} min ambulance ETA (max -25)"),
             ("Distance", min(15, a.amb_dist*1.5), f"{a.amb_dist} km to patient (max -15)"),
             ("Hospital readiness", 0 if (h and h.emergency_beds >= 3 and h.readiness == "Ready") else 4 if (h and h.emergency_beds > 0) else 10, "Beds/readiness at recommended hospital"),
             ("Severity match", 10 if (e.severity == "CRITICAL" and not adv) else 3 if (e.severity == "HIGH" and not adv) else 0, "Ambulance capability vs severity")]
    total = max(0, round(100 - sum(i[1] for i in items)))
    return dict(total=total, breakdown=[dict(name=n, penalty=round(p, 1), note=t) for n, p, t in items],
                formula="Score = 100 minus penalties for slow assignment, long ETA, long distance, low hospital readiness and capability mismatch.")

def ser(e):
    a = Assignment.query.filter_by(emergency_id=e.id).first(); amb = db.session.get(Ambulance, a.ambulance_id) if a and a.ambulance_id else None
    h = db.session.get(Hospital, a.hospital_id) if a and a.hospital_id else None
    d = dict(id=e.id, name=e.name, age=e.age, symptoms=e.symptoms, type=e.emergency_type, severity=e.severity, confidence=e.confidence, reason=e.reason,
             status=e.status, lat=e.latitude, lng=e.longitude, created=ts(e.created_at), contact=e.contact, notes=e.notes, demo=e.demo, assignment=a.id if a else None)
    ea = 0
    if amb:
        ea = 0 if e.status in ("picked_up", "completed", "arrived") else eta(hav(amb.latitude, amb.longitude, e.latitude, e.longitude))
        d["ambulance"] = dict(vehicle=amb.vehicle_number, lat=amb.latitude, lng=amb.longitude, capability=amb.capability, availability=amb.availability, why=a.amb_why, eta=ea, dist=a.amb_dist)
        d["candidates"] = json.loads(a.candidates or "[]")
    if h:
        he = 0 if e.status == "completed" else eta(hav(amb.latitude, amb.longitude, h.latitude, h.longitude)) if (amb and e.status == "picked_up") else round(ea + eta(hav(e.latitude, e.longitude, h.latitude, h.longitude)), 1)
        d["hospital"] = dict(id=h.id, name=h.name, lat=h.latitude, lng=h.longitude, beds=h.emergency_beds, readiness=h.readiness, why=a.hosp_why, eta=he)
        others = [x for x in rank_hosp(e.latitude, e.longitude, e.preferred_hospital_id) if x["id"] != h.id][:2]
        d["hospitals"] = [dict(id=h.id, name=h.name, eta=he, beds=h.emergency_beds, available=True, dist=round(hav(e.latitude, e.longitude, h.latitude, h.longitude), 1), recommended=True)] + others
        if a.accepted_at: d["score"] = score(e, a, h)
    d["alert"] = f"An ambulance has been assigned to {e.name}'s emergency request. Level: {e.severity}. Ambulance: {amb.vehicle_number if amb else 'pending'}. Hospital: {h.name if h else 'pending'}. Status: {e.status.replace('_', ' ')}."
    return d

# ---------- auth ----------
def new_guest():
    """Patients need no account: an anonymous guest session is created automatically."""
    u = User(name="Guest Patient", email=f"guest-{secrets.token_hex(6)}@guest.local", password=generate_password_hash(secrets.token_hex(8)), role="patient")
    db.session.add(u); db.session.flush(); db.session.add(Patient(user_id=u.id)); db.session.commit()
    session.clear(); session["uid"] = u.id; session.permanent = True; return u
@app.route("/")
def index():
    u = me()
    if u and u.role != "patient": return redirect("/" + u.role)
    return render_template("home.html", user=None)
@app.route("/patient")
def patient_page():
    u = me()
    if not u or u.role != "patient": u = new_guest()
    return render_template("patient_dashboard.html", user=u)
@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        u = User.query.filter_by(email=clean(request.form.get("email"), 120).lower()).first()
        if u and check_password_hash(u.password, request.form.get("password", "")):
            session.clear(); session["uid"] = u.id; return redirect("/" + u.role)
        err = "Invalid email or password."
    return render_template("login.html", error=err, user=None)
@app.post("/register")
def register():
    n, em, pw = clean(request.form.get("name"), 80), clean(request.form.get("email"), 120).lower(), request.form.get("password", "")
    if len(n) < 2 or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", em) or len(pw) < 6:
        return render_template("login.html", error="Enter a name, valid email and a password of 6+ characters.", user=None)
    if User.query.filter_by(email=em).first(): return render_template("login.html", error="Email already registered.", user=None)
    u = User(name=n, email=em, password=generate_password_hash(pw), role="patient"); db.session.add(u); db.session.flush()
    db.session.add(Patient(user_id=u.id, age=None)); db.session.commit(); session.clear(); session["uid"] = u.id
    return redirect("/patient")
@app.post("/demo-login")
def demo_login():
    new_guest(); return redirect("/patient?demo=1")
@app.route("/logout")
def logout(): session.clear(); return redirect("/login")

# ---------- pages ----------
for _r, _t in [("driver", "ambulance_dashboard.html"), ("hospital", "hospital_dashboard.html"), ("admin", "admin_dashboard.html")]:
    app.add_url_rule("/" + _r, _r + "_page", guard(_r)(lambda u, t=_t: render_template(t, user=u)))
app.add_url_rule("/emergency", "emergency_page", guard("patient")(lambda u: redirect("/patient")))

# ---------- shared APIs ----------
@app.get("/api/notifications")
@guard()
def api_notes(u):
    ns = Notification.query.filter_by(user_id=u.id).order_by(Notification.id.desc()).limit(15).all()
    return jsonify(items=[dict(id=n.id, message=n.message, time=n.timestamp.strftime("%H:%M:%S"), read=n.read_status) for n in ns], unread=sum(not n.read_status for n in ns))
@app.post("/api/notifications/read")
@guard()
def api_read(u):
    Notification.query.filter_by(user_id=u.id, read_status=False).update({"read_status": True}); db.session.commit(); return jsonify(ok=True)
@app.get("/api/hospitals")
@guard()
def api_hosp(u): return jsonify([dict(id=h.id, name=h.name) for h in Hospital.query])

# ---------- patient ----------
@app.post("/api/emergency")
@guard("patient")
def api_create(u):
    d = request.get_json(silent=True) or {}; sym = clean(d.get("symptoms"), 500); et = d.get("emergency_type")
    if len(sym) < 3 or et not in TYPES: return jsonify(error="Symptoms and a valid emergency type are required."), 400
    try:
        lat, lng = float(d["latitude"]), float(d["longitude"]); assert -90 <= lat <= 90 and -180 <= lng <= 180
    except Exception: return jsonify(error="Location required - please allow location access."), 400
    p = Patient.query.filter_by(user_id=u.id).first()
    for old in Emergency.query.filter(Emergency.patient_id == p.id, Emergency.status.in_(ACTIVE + ["waiting"])):
        if not d.get("demo"): return jsonify(error="You already have an active emergency."), 400
        old.status = "cancelled"; oa = Assignment.query.filter_by(emergency_id=old.id).first()
        if oa:
            oa.status = "cancelled"; oamb = db.session.get(Ambulance, oa.ambulance_id)
            if oamb: oamb.availability = "Available"
    try: age = int(d.get("age")) if d.get("age") not in (None, "") else p.age
    except ValueError: return jsonify(error="Age must be a number."), 400
    contact = clean(d.get("contact"), 120) or p.emergency_contact or ""
    sev, conf, why = predict(sym, et)
    try: pref = int(d.get("preferred_hospital")) if d.get("preferred_hospital") else None
    except ValueError: pref = None
    e = Emergency(patient_id=p.id, name=clean(d.get("name"), 80) or u.name, age=age, symptoms=sym, emergency_type=et, latitude=lat, longitude=lng,
                  severity=sev, confidence=conf, reason=why, notes=clean(d.get("notes"), 300), contact=contact, preferred_hospital_id=pref, demo=bool(d.get("demo")))
    db.session.add(e); db.session.flush(); p.age = age or p.age
    a = assign(e)
    if a: notify(u.id, f"Ambulance assigned: {a.amb_why}")
    else: notify(u.id, "No ambulance is free right now. Please call 112 / 108 immediately.")
    db.session.commit(); return jsonify(ser(e)), 201
@app.get("/api/emergency/<int:i>")
@guard("patient", "admin", "hospital", "driver")
def api_get(u, i):
    e = db.get_or_404(Emergency, i)
    if u.role == "patient" and db.session.get(Patient, e.patient_id).user_id != u.id: return jsonify(error="Forbidden"), 403
    return jsonify(ser(e))
@app.get("/api/my/active")
@guard("patient")
def api_active(u):
    p = Patient.query.filter_by(user_id=u.id).first()
    e = Emergency.query.filter(Emergency.patient_id == p.id, Emergency.status.in_(ACTIVE + ["waiting"])).order_by(Emergency.id.desc()).first()
    hist = Emergency.query.filter_by(patient_id=p.id, status="completed").order_by(Emergency.id.desc()).limit(8).all()
    return jsonify(emergency=ser(e) if e else None, contact=p.emergency_contact or "", age=p.age, history=[dict(id=x.id, type=x.emergency_type, severity=x.severity, created=ts(x.created_at)) for x in hist])
@app.post("/api/patient/profile")
@guard("patient")
def api_profile(u):
    d = request.get_json(silent=True) or {}; p = Patient.query.filter_by(user_id=u.id).first(); p.emergency_contact = clean(d.get("contact"), 120); db.session.commit(); return jsonify(ok=True)
@app.post("/api/sim/<int:i>/tick")
@guard("patient", "driver")
def api_tick(u, i):
    e = db.get_or_404(Emergency, i); a = Assignment.query.filter_by(emergency_id=i).first()
    if not a or e.status not in ACTIVE: return jsonify(ok=True)
    b = request.get_json(silent=True) or {}
    try: pos = (float(b["lat"]), float(b["lng"]))
    except (KeyError, TypeError, ValueError): pos = None
    fin = bool(b.get("final"))
    if u.role == "patient":
        if not e.demo or db.session.get(Patient, e.patient_id).user_id != u.id: return jsonify(error="Forbidden"), 403
        tick(a, e, True, pos, fin)
    else:
        amb = db.session.get(Ambulance, a.ambulance_id)
        if amb.driver_id != u.id: return jsonify(error="Forbidden"), 403
        tick(a, e, False, pos, fin)
    db.session.commit(); return jsonify(ok=True)

# ---------- driver ----------
def my_amb(u): return Ambulance.query.filter_by(driver_id=u.id).first()
def current(amb):
    a = Assignment.query.filter(Assignment.ambulance_id == amb.id, Assignment.status.in_(ACTIVE)).first()
    return (a, db.session.get(Emergency, a.emergency_id)) if a else (None, None)
@app.get("/api/driver/state")
@guard("driver")
def drv_state(u):
    amb = my_amb(u); a, e = current(amb)
    hist = db.session.query(Assignment, Emergency).join(Emergency, Emergency.id == Assignment.emergency_id).filter(Assignment.ambulance_id == amb.id, Assignment.status == "completed").order_by(Assignment.id.desc()).limit(10).all()
    return jsonify(ambulance=dict(vehicle=amb.vehicle_number, availability=amb.availability, capability=amb.capability, lat=amb.latitude, lng=amb.longitude), current=ser(e) if e else None,
                   next=NEXT.get(a.status) if a else None, history=[dict(type=x.emergency_type, severity=x.severity, when=ts(x.created_at), pickup=ts(y.pickup_time), arrived=ts(y.arrival_time)) for y, x in hist])
@app.post("/api/driver/availability")
@guard("driver")
def drv_avail(u):
    amb = my_amb(u); v = (request.get_json(silent=True) or {}).get("availability")
    if v not in ("Available", "Offline") or amb.availability not in ("Available", "Offline"): return jsonify(error="Cannot change availability during a trip."), 400
    amb.availability = v; db.session.commit(); return jsonify(ok=True)
@app.post("/api/driver/respond")
@guard("driver")
def drv_respond(u):
    amb = my_amb(u); a, e = current(amb)
    if not a or a.status != "pending": return jsonify(error="No pending request."), 400
    if (request.get_json(silent=True) or {}).get("accept"): accept(a, e)
    else:
        a.rejected = (a.rejected + "," if a.rejected else "") + str(amb.id); amb.availability = "Available"
        if not assign(e, a): notify(patient_user(e), "No other ambulance available. Please call 112 / 108.")
    db.session.commit(); return jsonify(ok=True)
@app.post("/api/driver/status")
@guard("driver")
def drv_status(u):
    amb = my_amb(u); a, e = current(amb); new = (request.get_json(silent=True) or {}).get("status")
    if not a or NEXT.get(a.status) != new: return jsonify(error="Invalid status transition."), 400
    set_status(a, e, new); db.session.commit(); return jsonify(ok=True)

# ---------- hospital ----------
def my_hosp(u): return Hospital.query.filter_by(user_id=u.id).first()
@app.get("/api/hospital/state")
@guard("hospital")
def hos_state(u):
    h = my_hosp(u)
    rows = db.session.query(Assignment, Emergency).join(Emergency, Emergency.id == Assignment.emergency_id).filter(Assignment.hospital_id == h.id).order_by(Assignment.id.desc()).all()
    inc, done = [], []
    for a, e in rows:
        s = ser(e)
        if a.status in ("accepted", "on_the_way", "arrived", "picked_up"): inc.append(s)
        elif a.status == "completed": done.append(dict(name=e.name, severity=e.severity, type=e.emergency_type, arrived=ts(a.arrival_time)))
    return jsonify(hospital=dict(name=h.name, beds=h.emergency_beds, readiness=h.readiness, available=h.emergency_available), incoming=inc, history=done[:10])
@app.post("/api/hospital/update")
@guard("hospital")
def hos_update(u):
    h = my_hosp(u); d = request.get_json(silent=True) or {}
    try: beds = int(d.get("beds"))
    except (TypeError, ValueError): return jsonify(error="Beds must be a number."), 400
    if not 0 <= beds <= 200 or d.get("readiness") not in ("Ready", "Preparing", "Full"): return jsonify(error="Invalid values."), 400
    h.emergency_beds, h.readiness, h.emergency_available = beds, d["readiness"], bool(d.get("available", True)); db.session.commit(); return jsonify(ok=True)

# ---------- admin ----------
@app.post("/api/admin/toggle")
@guard("admin")
def adm_toggle(u):
    d = request.get_json(silent=True) or {}
    if d.get("kind") == "ambulance":
        a = db.get_or_404(Ambulance, d.get("id"))
        if a.availability in ("Available", "Offline"): a.availability = "Offline" if a.availability == "Available" else "Available"
    elif d.get("kind") == "hospital":
        h = db.get_or_404(Hospital, d.get("id")); h.emergency_available = not h.emergency_available
    db.session.commit(); return jsonify(ok=True)
@app.get("/api/admin/stats")
@guard("admin")
def adm_stats(u):
    es = Emergency.query.all(); emap = {e.id: e for e in es}; asg = Assignment.query.all(); now = datetime.now()
    days = [(now - timedelta(days=i)).date() for i in range(6, -1, -1)]
    done = [a for a in asg if a.pickup_time and a.emergency_id in emap]
    resp = lambda a: (a.pickup_time - emap[a.emergency_id].created_at).total_seconds()/60
    avg = lambda xs: round(sum(xs)/len(xs), 1) if xs else 0
    byday = Counter(e.created_at.date() for e in es); hourly = Counter(e.created_at.hour for e in es); ndays = len({e.created_at.date() for e in es}) or 1
    trend = [avg([resp(a) for a in done if emap[a.emergency_id].created_at.date() == d]) for d in days]
    hot = Counter((round(e.latitude, 2), round(e.longitude, 2)) for e in es).most_common(5)
    types = Counter(e.emergency_type for e in es); ambs = Ambulance.query.all(); util = Counter("Available" if a.availability == "Available" else "Offline" if a.availability == "Offline" else "Busy" for a in ambs)
    peak = max(hourly, key=hourly.get) if hourly else 0; nh = [(now.hour + i) % 24 for i in (1, 2, 3)]
    fc = [dict(hour=f"{h:02d}:00", expected=round(hourly.get(h, 0)/ndays, 1)) for h in nh]
    return jsonify(
        kpi=dict(total=len(es), active=sum(e.status in ACTIVE + ["waiting"] for e in es), critical=sum(e.severity == "CRITICAL" for e in es), available=util["Available"], busy=util["Busy"],
                 hospitals=Hospital.query.count(), completed=sum(e.status == "completed" for e in es), avg_response=avg([resp(a) for a in done]),
                 avg_assign=round(avg([(a.assigned_at - emap[a.emergency_id].created_at).total_seconds() for a in asg if a.emergency_id in emap and a.assigned_at]), 0)),
        by_day=dict(labels=[d.strftime("%d %b") for d in days], data=[byday.get(d, 0) for d in days]), types=dict(types), severity=dict(Counter(e.severity for e in es)), utilization=dict(util),
        trend=dict(labels=[d.strftime("%d %b") for d in days], data=trend), hourly=[hourly.get(h, 0) for h in range(24)], forecast=fc,
        insights=[f"Peak emergency hour: {peak:02d}:00 - {peak+1:02d}:00.", f"Most common type: {types.most_common(1)[0][0] if types else 'n/a'}.", f"Average response time (request to pickup): {avg([resp(a) for a in done])} min.",
                  f"Highest-demand zone (approx. lat, lng): {hot[0][0][0]}, {hot[0][0][1]} ({hot[0][1]} requests)." if hot else "No zone data yet.",
                  "Demand forecast = average requests per hour across historical days (simple baseline, not a validated model)."],
        hotspots=[dict(zone=f"{k[0]}, {k[1]}", count=c) for k, c in hot],
        lists=dict(patients=[dict(name=x.name, email=x.email, age=p.age, contact=p.emergency_contact) for p, x in db.session.query(Patient, User).join(User, User.id == Patient.user_id)],
                   ambulances=[dict(id=a.id, vehicle=a.vehicle_number, availability=a.availability, capability=a.capability) for a in ambs],
                   hospitals=[dict(id=h.id, name=h.name, beds=h.emergency_beds, available=h.emergency_available, readiness=h.readiness) for h in Hospital.query],
                   emergencies=[dict(id=e.id, name=e.name, type=e.emergency_type, severity=e.severity, status=e.status, created=ts(e.created_at)) for e in sorted(es, key=lambda x: -x.id)[:15]]))

# ---------- seed (fictional data only) ----------
def seed():
    if User.query.first(): return
    mk = lambda n, e, r: (lambda u: (db.session.add(u), db.session.flush(), u)[2])(User(name=n, email=e, password=generate_password_hash("demo123"), role=r))
    mk("Admin User", "admin@demo.com", "admin"); pu = mk("Demo Patient", "patient@demo.com", "patient")
    p = Patient(user_id=pu.id, age=45, emergency_contact="Sample Contact (+91 90000 00000)"); db.session.add(p)
    cl, cg = CENTER
    for i, (n, dl, dg, cap) in enumerate([("TN-38-AM-1001", .004, .008, "Basic"), ("TN-38-AM-1002", .012, .012, "Advanced"), ("TN-38-AM-1003", -.006, -.012, "Basic"), ("TN-38-AM-1004", .03, .03, "Advanced")], 1):
        d = mk(f"Driver {i}", f"driver{i}@demo.com", "driver"); db.session.add(Ambulance(driver_id=d.id, vehicle_number=n, latitude=cl+dl, longitude=cg+dg, capability=cap))
    for i, (n, dl, dg, av, beds) in enumerate([("Riverside General Hospital", .004, .015, True, 4), ("Lakeview Medical Centre", -.02, .004, True, 2), ("St. Hope Emergency Institute", .014, -.016, True, 5), ("Northgate Care Hospital", .04, .02, False, 0)], 1):
        u = mk(n + " Staff", f"hospital{i}@demo.com", "hospital"); db.session.add(Hospital(user_id=u.id, name=n, latitude=cl+dl, longitude=cg+dg, emergency_available=av, emergency_beds=beds, readiness="Ready" if av else "Full"))
    db.session.flush(); random.seed(7); ambs = Ambulance.query.all(); hs = Hospital.query.all()
    for _ in range(45):   # synthetic history for analytics
        hr = random.choices(range(24), weights=[1,1,1,1,1,2,3,5,6,5,4,4,4,4,4,5,6,7,7,6,4,3,2,1])[0]
        t = (datetime.now() - timedelta(days=random.randint(1, 13))).replace(hour=hr, minute=random.randint(0, 59), second=0, microsecond=0)
        et = random.choice(TYPES); sev = random.choices(["CRITICAL", "HIGH", "MODERATE"], [3, 4, 3])[0]
        e = Emergency(patient_id=p.id, name="Sample Patient", age=random.randint(20, 80), symptoms="Sample historical record", emergency_type=et, latitude=cl+random.gauss(0, .015), longitude=cg+random.gauss(0, .015), severity=sev, confidence=.8, reason="", status="completed", created_at=t)
        db.session.add(e); db.session.flush(); pk = t + timedelta(minutes=random.randint(6, 17))
        db.session.add(Assignment(emergency_id=e.id, ambulance_id=random.choice(ambs).id, hospital_id=random.choice(hs).id, assigned_at=t + timedelta(seconds=random.randint(5, 45)), accepted_at=t + timedelta(seconds=60), pickup_time=pk, arrival_time=pk + timedelta(minutes=random.randint(6, 15)), status="completed"))
    db.session.commit()

with app.app_context():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True); db.create_all(); seed()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
