"""Performance test for the CodeLiteracy backend using Locust.

Run (backend must be running on port 8000):
    locust -f locustfile.py --host http://127.0.0.1:8000 --headless -u 20 -r 5 -t 30s --html locust_report.html
Or run without --headless and open http://localhost:8089 for the web UI.
"""
from locust import HttpUser, between, task


class CodeLiteracyUser(HttpUser):
    wait_time = between(0.5, 1.5)  # think time between requests, in seconds

    def on_start(self):
        # Every simulated user signs in as a guest once, like a real visitor would.
        with self.client.post("/api/auth/guest", name="POST /api/auth/guest", catch_response=True) as r:
            if r.status_code == 200 and r.json().get("token"):
                self.token = r.json()["token"]
                r.success()
            else:
                self.token = None
                r.failure(f"guest login failed: {r.status_code}")

    @task(3)
    def health(self):
        with self.client.get("/api/health", name="GET /api/health", catch_response=True) as r:
            if r.status_code == 200 and r.json().get("status") == "ok":
                r.success()
            else:
                r.failure("health check did not return status ok")

    @task(2)
    def samples(self):
        with self.client.get("/api/repo/samples", name="GET /api/repo/samples", catch_response=True) as r:
            if r.status_code == 200 and len(r.json()) >= 2:
                r.success()
            else:
                r.failure("sample repository list is missing")

    @task(1)
    def me(self):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        with self.client.get("/api/auth/me", name="GET /api/auth/me", headers=headers, catch_response=True) as r:
            if r.status_code == 200 and r.json()["user"]["is_guest"]:
                r.success()
            else:
                r.failure(f"current user lookup failed: {r.status_code}")
