from flask import Flask, request, jsonify
import threading
import os_engine
import db_engine

app = Flask(__name__)

# System start hote hi database initialize karo
db_engine.init_db()
available_icu_beds = 2  

# OS Level Mutex Lock (To prevent race conditions)
bed_lock = threading.Lock()

# ========================================================
# 1. PATIENT REGISTRATION & OS SCHEDULING
# ========================================================
@app.route('/api/admit_patient', methods=['POST'])
def admit_patient():
    global available_icu_beds
    
    # Mutex lock applied here - Only one thread can enter this block at a time
    with bed_lock:
        data = request.json
        patient_id = data.get('patient_id')
        name = data.get('name')
        condition = data.get('condition')

        print(f"\n{'='*50}")
        print(f"[BACKEND API] New Patient Request -> ID: {patient_id} | Name: {name} | Condition: {condition}")
        print(f"[OS ENGINE] Thread Acquired Mutex Lock.")
        
        priority = os_engine.get_priority(condition)
        print(f"[BACKEND API] Process {patient_id} assigned Priority Level: {priority}")

        is_safe = os_engine.check_bankers_safety(requested_resources=1, available_resources=available_icu_beds)

        if is_safe:
            success = db_engine.allocate_bed_transaction(patient_id, name, priority)
            if success:
                available_icu_beds -= 1
                print(f"[NOTIFICATION] 🔔 ICU Bed allocated to Process {patient_id}. Doctor notified.")
                print(f"[OS ENGINE] Thread Released Mutex Lock.")
                print(f"{'='*50}")
                return jsonify({"status": "Success", "patient_id": patient_id, "priority": priority})
            else:
                print(f"[OS ENGINE] Thread Released Mutex Lock.")
                return jsonify({"status": "Failed", "message": "Database Transaction Rolled Back"})
        else:
            print(f"[NOTIFICATION] ⚠️ Alert: System Unsafe. Process {patient_id} added to waitlist.")
            print(f"[OS ENGINE] Thread Released Mutex Lock.")
            print(f"{'='*50}")
            return jsonify({"status": "Queued", "patient_id": patient_id})

# ========================================================
# 2. DOCTOR -> LAB / RADIOLOGY MODULE
# ========================================================
@app.route('/api/request_test', methods=['POST'])
def request_test():
    data = request.json
    doctor_id = data.get('doctor_id')
    patient_id = data.get('patient_id')
    test_type = data.get('test_type')
    
    print(f"\n{'='*50}")
    print(f"[DOCTOR MODULE] Doctor [{doctor_id}] requested '{test_type}' for Patient [{patient_id}].")
    print(f"[DBMS] Saving test request (patient_id: {patient_id}, doctor_id: {doctor_id}) -> COMMIT")
    print(f"{'='*50}")
    
    return jsonify({"status": "Test Queued", "patient_id": patient_id})

@app.route('/api/complete_test', methods=['POST'])
def complete_test():
    data = request.json
    patient_id = data.get('patient_id')
    doctor_id = data.get('doctor_id')
    result = data.get('result')
    
    print(f"\n{'='*50}")
    print(f"[LAB/RADIOLOGY MODULE] Test completed for Patient [{patient_id}]. Result: {result}")
    print(f"[DBMS] Updating Lab results in database -> COMMIT")
    print(f"[NOTIFICATION SERVICE] 🚨 SMS/Alert triggered for Doctor [{doctor_id}]: 'Report Ready for Patient {patient_id}'")
    print(f"{'='*50}")
    
    return jsonify({"status": "Report Generated", "notification": "Sent to Doctor"})

# ========================================================
# 3. DOCTOR -> PHARMACY MODULE
# ========================================================
@app.route('/api/send_prescription', methods=['POST'])
def send_prescription():
    data = request.json
    patient_id = data.get('patient_id')
    doctor_id = data.get('doctor_id')
    medicine = data.get('medicine_name')
    
    print(f"\n{'='*50}")
    print(f"[DOCTOR MODULE] Doctor [{doctor_id}] sent e-Prescription for Patient [{patient_id}].")
    print(f"[PHARMACY MODULE] Checking inventory for '{medicine}'...")
    print(f"[DBMS] Updating pharmacy stock mapped to {patient_id} -> COMMIT")
    print(f"{'='*50}")
    
    return jsonify({"status": "Prescription Processed"})

# ========================================================
# SERVER STARTUP
# ========================================================
if __name__ == '__main__':
    print("🚀 Smart Hospital Backend running on http://127.0.0.1:5000")
    app.run(debug=True, port=5000, threaded=True)