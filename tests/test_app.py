import os, sys, tempfile, unittest
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A

def login(c, e): return c.post("/login", data={"email": e, "password": "demo123"}, follow_redirects=False)
class Flow(unittest.TestCase):
    def test_full_workflow(self):
        p, d, h, ad = (A.app.test_client() for _ in range(4))
        self.assertEqual(p.get("/admin").status_code, 302)               # staff pages protected
        self.assertEqual(p.get("/patient").status_code, 200)             # patient = guest, no login
        self.assertEqual(p.get("/api/admin/stats").status_code, 403)     # RBAC
        r = p.post("/api/emergency", json=dict(symptoms="Severe chest pain and difficulty breathing", emergency_type="Chest pain", latitude=11.012, longitude=76.95, demo=False))
        e = r.get_json(); self.assertEqual(e["severity"], "CRITICAL"); self.assertEqual(e["ambulance"]["capability"], "Advanced")
        self.assertEqual(p.post("/api/emergency", json=dict(symptoms="x y z", emergency_type="Other", latitude=1, longitude=1)).status_code, 400)
        veh = e["ambulance"]["vehicle"]; n = int(veh[-1]); login(d, f"driver{n}@demo.com")
        self.assertEqual(d.post("/api/driver/respond", json={"accept": True}).status_code, 200)
        for s in ["on_the_way", "arrived", "picked_up", "completed"]: self.assertEqual(d.post("/api/driver/status", json={"status": s}).status_code, 200)
        self.assertEqual(d.post("/api/driver/status", json={"status": "arrived"}).status_code, 400)
        e = p.get(f"/api/emergency/{e['id']}").get_json(); self.assertEqual(e["status"], "completed"); self.assertTrue(0 <= e["score"]["total"] <= 100)
        login(ad, "admin@demo.com"); st = ad.get("/api/admin/stats").get_json(); self.assertGreater(st["kpi"]["total"], 40)
        self.assertEqual(p.get("/api/admin/stats").status_code, 403)
    def test_demo_simulation(self):
        p = A.app.test_client(); p.post("/demo-login")
        e = p.post("/api/emergency", json=dict(symptoms="Severe chest pain and difficulty breathing", emergency_type="Chest pain", latitude=11.0122, longitude=76.9500, demo=True)).get_json()
        for _ in range(80):
            p.post(f"/api/sim/{e['id']}/tick")
            if p.get(f"/api/emergency/{e['id']}").get_json()["status"] == "completed": break
        self.assertEqual(p.get(f"/api/emergency/{e['id']}").get_json()["status"], "completed")
if __name__ == "__main__": unittest.main()
