"""
scripts/verify_live_router.py
=============================
Direct live integration verification against http://127.0.0.1:8000/api/v1/chat.
Validates the smart conversation router, off-topic handling, vulgar language handling,
and follow-up return to website topics on the live server.
"""
import json
import urllib.request
import urllib.error

API_URL = "http://127.0.0.1:8000/api/v1/chat"

TEST_PROMPTS = [
    {
        "name": "Scenario A: Unrelated Food",
        "message": "Do they provide rajma chawal?",
        "history": [],
        "expected_status": "out_of_scope",
    },
    {
        "name": "Scenario B: General Trivia",
        "message": "What is the capital of Japan?",
        "history": [],
        "expected_status": "out_of_scope",
    },
    {
        "name": "Scenario C: Bot Insult",
        "message": "You are useless.",
        "history": [],
        "expected_status": "out_of_scope",
    },
    {
        "name": "Scenario D: Profanity in Legitimate Website Query",
        "message": "Tell me what the hell Eureka Solutions actually does.",
        "history": [],
        "expected_status": "answered",
    },
    {
        "name": "Scenario E: Insult in Legitimate Company Query",
        "message": "You idiot, explain their cloud integration service",
        "history": [],
        "expected_status": "answered",
    },
    {
        "name": "Scenario F: Frustration / Feedback Not Abusive",
        "message": "I am angry because your previous answer was wrong. Can you explain the service again?",
        "history": [],
        "expected_status": "answered",
    },
    {
        "name": "Scenario G: Repeated Provocations (Boundary)",
        "message": "You idiot bot",
        "history": [
            {"role": "user", "content": "You are stupid"},
            {"role": "assistant", "content": "I'm sorry this hasn't been helpful yet..."},
            {"role": "user", "content": "You are completely useless"},
            {"role": "assistant", "content": "I'm here to help with questions about Eureka Solutions..."},
        ],
        "expected_status": "out_of_scope",
    },
    {
        "name": "Scenario H: Follow-up Restores RAG",
        "message": "Okay fine, what ERP solutions does Eureka Solutions implement?",
        "history": [
            {"role": "user", "content": "Do they provide rajma chawal?"},
            {"role": "assistant", "content": "Haha, rajma chawal isn't quite our line of business! I'm here to help you explore Eureka Solutions' software and cloud integration."},
        ],
        "expected_status": "answered",
    },
]


import time

def run_checks():
    print(f"Connecting to live API at {API_URL}...\n")
    all_passed = True

    for test in TEST_PROMPTS:
        time.sleep(6.0)  # Respect free tier Groq 30-RPM / TPM limits
        payload = {
            "message": test["message"],
            "conversation_history": test["history"],
        }
        req = urllib.request.Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Origin": "http://localhost:5173"},
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                status = data.get("status")
                answer = data.get("answer", "").encode("ascii", errors="replace").decode("ascii")
                sources_count = len(data.get("sources", []))

                passed = status == test["expected_status"]
                if not passed:
                    all_passed = False

                flag = "PASS" if passed else "FAIL"
                print(f"[{flag}] {test['name']}")
                print(f"       Query:   '{test['message']}'")
                print(f"       Status:  {status} (expected: {test['expected_status']})")
                print(f"       Sources: {sources_count}")
                print(f"       Answer:  {answer[:120]}...\n")
        except urllib.error.HTTPError as exc:
            print(f"[FAIL] {test['name']} - HTTP {exc.code}: {exc.read().decode('utf-8')}\n")
            all_passed = False
        except Exception as exc:
            print(f"[FAIL] {test['name']} - Error: {exc}\n")
            all_passed = False

    if all_passed:
        print("ALL LIVE INTEGRATION CHECKS PASSED SUCCESSFULLY!")
    else:
        print("SOME CHECKS FAILED.")


if __name__ == "__main__":
    run_checks()
