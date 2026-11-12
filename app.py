"""
Flask Backend API (app.py)
Exposes REST API endpoints for Multi-Resource Admission, Persistent Lab Tests,
Pharmacy Dispensing, Queue Promotion, and Concurrency Stress Testing.
Protected by Python threading.Lock for concurrency safety.
"""

import threading
from flask import Flask, request, jsonify
import os_engine
import db_engine

app = Flask(__name__)

# Mutex lock to prevent race conditions during concurrent ICU resource operations
admission_lock = threading.Lock()

# Initialize SQLite tables on startup
db_engine.init_db()


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "available_icu_beds": db_engine.get_available_beds(),
        "resources": db_engine.get_all_resources()
    }), 200


@app.route("/api/admit_patient", methods=["POST"])
def admit_patient():
    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id", "P101").strip()
    name = data.get("name", "Unknown").strip()
    condition = data.get("condition", "General Routine").strip()
    hospital_id = data.get("hospital_id", "GEIMS-DDN-01").strip()

    with admission_lock:
        priority = os_engine.assign_priority(condition)
        available_beds = db_engine.get_available_beds()
        is_safe = os_engine.check_safety(requested_beds=1, available_beds=available_beds)

        tx_result = db_engine.allocate_bed_and_admit(
            patient_id=patient_id,
            name=name,
            condition=condition,
            priority=priority,
            is_safe=is_safe,
            hospital_id=hospital_id
        )

        if tx_result.get("status") == "Error":
            return jsonify({
                "status": "Failed",
                "message": tx_result.get("error", "Database transaction error")
            }), 500

        if tx_result.get("admitted"):
            return jsonify({
                "status": "Success",
                "patient_id": patient_id,
                "priority": priority,
                "allocation_detail": tx_result.get("status"),
                "remaining_beds": tx_result.get("remaining_beds"),
                "resources": tx_result.get("resources"),
                "safe_sequence": tx_result.get("safe_sequence", []),
                "message": f"Patient {patient_id} processed ({tx_result.get('status')})."
            }), 200
        else:
            return jsonify({
                "status": "Queued",
                "patient_id": patient_id,
                "priority": priority,
                "remaining_beds": tx_result.get("remaining_beds", 0),
                "resources": tx_result.get("resources"),
                "message": "System Unsafe (Multi-Resource Banker's Check). Added to Priority Waitlist Queue."
            }), 200


@app.route("/api/request_test", methods=["POST"])
def request_test():
    data = request.get_json(silent=True) or {}
    doctor_id = data.get("doctor_id", "D505").strip()
    patient_id = data.get("patient_id", "P101").strip()
    test_type = data.get("test_type", "Blood Test").strip()

    with admission_lock:
        test_id = db_engine.save_lab_request(patient_id, doctor_id, test_type)

    return jsonify({
        "status": f"Test #{test_id} ('{test_type}') saved in SQLite for Patient {patient_id}",
        "doctor_id": doctor_id,
        "patient_id": patient_id,
        "test_type": test_type
    }), 200


@app.route("/api/complete_test", methods=["POST"])
def complete_test():
    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id", "P101").strip()
    doctor_id = data.get("doctor_id", "D505").strip()
    result = data.get("result", "Normal").strip()

    with admission_lock:
        db_engine.complete_lab_report(patient_id, doctor_id, result)

    return jsonify({
        "status": "Report Saved to SQLite & Doctor Alerted",
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "result": result
    }), 200


@app.route("/api/send_prescription", methods=["POST"])
def send_prescription():
    data = request.get_json(silent=True) or {}
    doctor_id = data.get("doctor_id", "D505").strip()
    patient_id = data.get("patient_id", "P101").strip()
    medicine_name = data.get("medicine_name", "Aspirin").strip()

    with admission_lock:
        rx_id = db_engine.save_prescription(patient_id, doctor_id, medicine_name)

    return jsonify({
        "status": f"Prescription #{rx_id} ('{medicine_name}') saved to SQLite Pharmacy Queue",
        "doctor_id": doctor_id,
        "patient_id": patient_id,
        "medicine_name": medicine_name
    }), 200


@app.route("/api/dispense_medicine", methods=["POST"])
def dispense_medicine():
    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id", "P101").strip()
    medicine_name = data.get("medicine_name", "Aspirin").strip()

    with admission_lock:
        db_engine.mark_prescription_dispensed(patient_id, medicine_name)
        release_info_res = db_engine.release_bed_on_completion(patient_id)
        remaining = db_engine.get_available_beds()

    return jsonify({
        "status": f"Medicine '{medicine_name}' dispensed to {patient_id} | {release_info_res['message']} | Available ICU Beds: {remaining}",
        "patient_id": patient_id,
        "medicine_name": medicine_name,
        "remaining_beds": remaining,
        "promoted_patients": release_info_res.get("promoted", [])
    }), 200


@app.route("/api/patient_status/<patient_id>", methods=["GET"])
def patient_status(patient_id):
    record = db_engine.get_patient_status(patient_id)
    if record:
        return jsonify({
            "found": True,
            "patient_id": record["patient_id"],
            "name": record["name"],
            "condition": record["condition"],
            "priority": record["priority"],
            "status": record["status"],
            "hospital_id": record.get("hospital_id", "GEIMS-DDN-01"),
            "bed_allocated": bool(record["bed_allocated"]),
            "vent_allocated": bool(record.get("vent_allocated", 0)),
            "oxy_allocated": bool(record.get("oxy_allocated", 0)),
            "queue_position": record.get("queue_position", 0),
            "total_in_queue": record.get("total_in_queue", 0),
            "lab_tests": record.get("lab_tests", []),
            "prescriptions": record.get("prescriptions", [])
        }), 200
    return jsonify({
        "found": False,
        "patient_id": patient_id,
        "status": "No record found in SQLite for this Patient ID."
    }), 200


@app.route("/api/reset", methods=["POST"])
def reset_system():
    with admission_lock:
        db_engine.reset_simulation_resources()
    return jsonify({"status": "System resources and tables reset to initial state."}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
