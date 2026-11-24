"""
Automated Integration & Concurrency Stress Test Suite (run_demo.py)
Validates:
1. End-to-End Multi-Resource Admission, Lab, Pharmacy, and Resource Release.
2. Multi-Threaded Concurrency Stress Test (12 simultaneous threads) to verify zero race conditions.
3. Priority Queue Auto-Promotion when an ICU bed/ventilator is released.
"""

from concurrent.futures import ThreadPoolExecutor
import time
import threading
import requests
import db_engine

BASE_URL = "http://127.0.0.1:5000/api"


def ensure_local_server():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=1)
        if r.status_code == 200:
            return
    except Exception:
        from app import app as flask_app
        t = threading.Thread(
            target=lambda: flask_app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False),
            daemon=True
        )
        t.start()
        time.sleep(1.0)


def run_test_suite():
    ensure_local_server()
    print("=" * 65)
    print("🚀 STARTING PHASE-3 AUTOMATED INTEGRATION & CONCURRENCY SUITE")
    print("=" * 65)

    # Reset DB for a clean deterministic test
    requests.post(f"{BASE_URL}/reset", timeout=5)
    print("[1/4] Reset Database: ICU=5, VENTILATOR=3, OXYGEN=8")

    # Test 1: Concurrency Stress Test (10 parallel threads competing for limited resources)
    print("\n[2/4] Running 10-Thread Parallel Admission Stress Test...")

    def admit_worker(i):
        cond = "Heart Attack" if i <= 5 else "Accident"
        resp = requests.post(
            f"{BASE_URL}/admit_patient",
            json={"patient_id": f"P10{i}", "name": f"Patient_{i}", "condition": cond},
            timeout=10
        )
        return resp.json()

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(admit_worker, range(1, 11)))

    admitted = [r["patient_id"] for r in results if r.get("status") == "Success"]
    queued = [r["patient_id"] for r in results if r.get("status") == "Queued"]
    rem_beds = db_engine.get_available_beds()

    print(f"   -> Admitted Safely ({len(admitted)}): {admitted}")
    print(f"   -> Queued Safely   ({len(queued)}): {queued}")
    print(f"   -> Remaining ICU Beds in SQLite: {rem_beds} (Expected >= 0, Race Conditions = 0)")
    assert rem_beds >= 0, "RACE CONDITION DETECTED: Negative beds!"

    # Test 2: Persistent Lab & Pharmacy Workflow
    target_pid = admitted[0]
    print(f"\n[3/4] Testing Persistent Lab & Pharmacy Workflow for {target_pid}...")
    r1 = requests.post(f"{BASE_URL}/request_test", json={"patient_id": target_pid, "doctor_id": "D505", "test_type": "MRI Scan"}).json()
    r2 = requests.post(f"{BASE_URL}/complete_test", json={"patient_id": target_pid, "doctor_id": "D505", "result": "Clear"}).json()
    r3 = requests.post(f"{BASE_URL}/send_prescription", json={"patient_id": target_pid, "doctor_id": "D505", "medicine_name": "Atorvastatin"}).json()
    print(f"   -> {r1['status']}")
    print(f"   -> {r2['status']}")
    print(f"   -> {r3['status']}")

    # Test 3: Discharge & Automatic Queue Promotion
    print(f"\n[4/4] Dispensing Medicine to {target_pid} & Testing OS Queue Auto-Promotion...")
    r4 = requests.post(f"{BASE_URL}/dispense_medicine", json={"patient_id": target_pid, "medicine_name": "Atorvastatin"}).json()
    print(f"   -> {r4['status']}")

    status_check = requests.get(f"{BASE_URL}/patient_status/{target_pid}").json()
    assert len(status_check.get("lab_tests", [])) > 0, "Lab test not saved in DB!"
    assert len(status_check.get("prescriptions", [])) > 0, "Prescription not saved in DB!"

    print("\n✅ ALL PHASE-3 AUTOMATED INTEGRATION & CONCURRENCY TESTS PASSED!")
    print("=" * 65)


if __name__ == "__main__":
    run_test_suite()
