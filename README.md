# 🚑 ResQRoute – AI-Powered Smart Ambulance & Emergency Response (Hackathon Prototype)

> This system is a technology prototype intended to assist emergency coordination. AI predictions are not medical diagnoses and must not replace qualified medical professionals or emergency services. All data is fictional. The ML dataset is small and **synthetic** – no clinical accuracy is claimed.

## Run (3 commands)
```bash
pip install -r requirements.txt
python ml/train.py        # optional; model.pkl is auto-trained on first run
python app.py             # open http://127.0.0.1:5000
```
The home page has two sections: **Patient** (no login – an anonymous guest session is created) and **Driver** (login). Click **"Run demo scenario"** for the automatic demo. To watch both sides live, open the driver in a second browser/incognito window (one browser = one session). Maps use Leaflet + OpenStreetMap (no API key; internet needed for tiles/CDN). Geolocation works on `localhost`/HTTPS. Fictional units are seeded around Coimbatore; set `CENTER_LAT` / `CENTER_LNG` env vars (before first run, delete `database/resqroute.db`) to relocate.

Driver/staff demo accounts (password `demo123`): `driver1..4@demo.com`, `hospital1..4@demo.com`, `admin@demo.com`.
Tests: `python -m unittest tests.test_app`

## Workflow implemented
Request → geolocation → AI severity (TF-IDF + Logistic Regression + transparent safety rules) → rank available ambulances (ETA + capability penalty for CRITICAL/HIGH) → best-matched (nearest suitable) available driver notified, who sees the real road route (OSRM) to patient and hospital plus a Google Maps navigation link → accept/reject (reject triggers re-allocation) → hospital ranked (ETA, beds, readiness, preference) → hospital + emergency-contact alerts → simulated GPS → pickup → hospital → history + Response Efficiency Score. Admin analytics include peak hours, hot zones and a baseline demand forecast.

**Response score** = 100 − penalties (assignment time ≤20, ETA ≤25, distance ≤15, hospital readiness ≤10, capability-vs-severity ≤10). Breakdown is shown in the UI.

## Structure
`app.py` (routes + allocation + simulation), `models/database.py`, `models/ml_model.py`, `ml/train.py|dataset.csv|model.pkl`, `templates/`, `static/`, `tests/`, `database/resqroute.db` (created on first run).

## Schema (SQLite / SQLAlchemy)
users(id,name,email,password[hash],role) · patients(id,user_id→users,age,emergency_contact) · hospitals(id,user_id,name,lat,lng,emergency_available,emergency_beds,readiness) · ambulances(id,driver_id→users,vehicle_number,lat,lng,availability,capability) · emergencies(id,patient_id→patients,symptoms,emergency_type,lat,lng,severity,confidence,reason,status,created_at,…) · assignments(id,emergency_id,ambulance_id,hospital_id,assigned_at,accepted_at,pickup_time,arrival_time,status,…) · notifications(id,user_id,message,timestamp,read_status)

## API (JSON, session-cookie auth, role-protected)
| Method & path | Role | Purpose |
|---|---|---|
| POST /api/emergency | patient | Create request (AI + allocation) |
| GET /api/emergency/<id> | any | Full emergency state, map data, score |
| GET /api/my/active · POST /api/patient/profile | patient | Active/history, save contact |
| POST /api/sim/<id>/tick | patient(demo)/driver | Simulated movement (+auto progression in demo) |
| GET /api/driver/state · POST /api/driver/{availability,respond,status} | driver | Driver workflow |
| GET /api/hospital/state · POST /api/hospital/update | hospital | Incoming patients, beds, readiness |
| GET /api/admin/stats · POST /api/admin/toggle | admin | KPIs, charts, analytics, manage |
| GET /api/notifications · POST /api/notifications/read | any | In-app notifications |

## Architecture
```
Browser (Bootstrap + Leaflet + Chart.js, polling 1.5–3 s)
   │ JSON/HTTP
Flask app.py ── auth/RBAC ── allocation (ambulance + hospital ranking) ── simulation ── scoring
   │                 │
SQLAlchemy/SQLite    models/ml_model.py ← ml/model.pkl (scikit-learn)
```
Twilio SMS plug-in point: call `notify()` → also send via Twilio REST in a helper (not required).

## Presentation outline
1 Problem & delay chain · 2 Solution workflow · 3 Live demo · 4 AI + allocation logic · 5 Response score · 6 Analytics · 7 Safety/ethics · 8 Roadmap.

## 2-minute demo script
0:00 Problem. 0:15 Click Demo → AI says CRITICAL with explanation. 0:35 Point to ranked ambulances: advanced unit chosen over closer basic one. 0:50 Map movement; open hospital tab (second browser) to show incoming alert. 1:15 Pickup → hospital ETA update. 1:30 Score breakdown. 1:45 Admin analytics. 1:55 Disclaimer + roadmap.

## Future enhancements
Validated clinical triage data and clinician review · real GPS from driver phones · Google/OSRM road routing with live traffic · WebSockets · Twilio SMS/WhatsApp · CSRF tokens, rate limiting, audit logs · PostgreSQL · multilingual/voice input · hospital EHR integration.
