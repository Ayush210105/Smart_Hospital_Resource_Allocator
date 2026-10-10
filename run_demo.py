import requests
import time

BASE_URL = "http://127.0.0.1:5000/api"

print("\n🚀 STARTING SMART HOSPITAL PHASE-2 SIMULATION...\n")
time.sleep(2)

print("👉 STEP 1: Emergency Patient Arrives (Requesting ICU Bed)")
requests.post(f"{BASE_URL}/admit_patient", json={"patient_id": "P101", "name": "Rahul", "condition": "Heart Attack"})
time.sleep(3) # 3 second ka wait taaki real lage

print("\n👉 STEP 2: Doctor Requests MRI Scan for Patient P101")
requests.post(f"{BASE_URL}/request_test", json={"doctor_id": "D505", "patient_id": "P101", "test_type": "MRI Scan"})
time.sleep(3)

print("\n👉 STEP 3: Lab Technician Uploads Report (Triggers Notification)")
requests.post(f"{BASE_URL}/complete_test", json={"patient_id": "P101", "doctor_id": "D505", "result": "Critical Blockage"})
time.sleep(3)

print("\n👉 STEP 4: Doctor Sends e-Prescription to Pharmacy")
requests.post(f"{BASE_URL}/send_prescription", json={"patient_id": "P101", "doctor_id": "D505", "medicine_name": "Aspirin"})
time.sleep(3)

print("\n👉 STEP 5: Concurrency/Deadlock Test (Second Patient Arrives)")
requests.post(f"{BASE_URL}/admit_patient", json={"patient_id": "P102", "name": "Suresh", "condition": "Accident"})
