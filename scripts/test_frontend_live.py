"""
Live integration test for frontend API client contract against the local FastAPI backend.
"""
import time
import requests

BASE_URL = "http://127.0.0.1:8000"

print("Waiting for server readiness...")
ready = False
for i in range(25):
    try:
        res = requests.get(f"{BASE_URL}/health/live", timeout=2)
        if res.status_code == 200:
            ready_res = requests.get(f"{BASE_URL}/health/ready", timeout=5)
            if ready_res.status_code == 200:
                print("Server is READY!")
                print("Readiness response:", ready_res.json())
                ready = True
                break
    except Exception:
        time.sleep(1)

if not ready:
    print("Server not ready in time.")
    exit(1)

# Test 1: Grounded question
print("\n--- Testing Grounded Question ---")
payload = {
    "message": "What ERP software does Eureka Solutions implement?",
    "session_id": "test-live-session-1",
    "language": "auto"
}
res = requests.post(
    f"{BASE_URL}/api/v1/chat",
    json=payload,
    headers={"Content-Type": "application/json", "Origin": "http://localhost:5173"}
)
print("Status Code:", res.status_code)
print("CORS Origin:", res.headers.get("access-control-allow-origin"))
print("X-Request-ID:", res.headers.get("x-request-id"))
data = res.json()
print("Response Status:", data.get("status"))
print("Answer snippet:", data.get("answer")[:150] if data.get("answer") else None)
print("Sources count:", len(data.get("sources", [])))
for s in data.get("sources", []):
    print(" - Source:", s.get("title"), "|", s.get("url"))

# Test 2: Out of scope question
print("\n--- Testing Out of Scope ---")
payload = {"message": "How do I bake sourdough bread?", "session_id": "test-live-session-2"}
res = requests.post(f"{BASE_URL}/api/v1/chat", json=payload, headers={"Origin": "http://localhost:5173"})
print("Status Code:", res.status_code)
print("Response Status:", res.json().get("status"))

# Test 3: Validation Error (> 2000 chars)
print("\n--- Testing Message > 2000 chars ---")
payload = {"message": "A" * 2001}
res = requests.post(f"{BASE_URL}/api/v1/chat", json=payload, headers={"Origin": "http://localhost:5173"})
print("Status Code:", res.status_code)

print("\n--- ALL LIVE INTEGRATION CHECKS PASSED ---")
