"""
Database Engine Module (db_engine.py)
Handles SQLite persistence, Multi-Resource Banker's allocation, Persistent Lab & Pharmacy records,
and Priority + FCFS Waitlist Queue auto-promotion.
"""

import sqlite3
import os
from typing import Dict, List, Optional
import os_engine

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hospital.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes and migrates SQLite tables for multi-resource allocation, patients, labs, and pharmacy."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resources (
                resource_name TEXT PRIMARY KEY,
                total_count INTEGER NOT NULL,
                available_count INTEGER NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                patient_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                condition TEXT NOT NULL,
                priority INTEGER NOT NULL,
                status TEXT NOT NULL,
                bed_allocated INTEGER NOT NULL DEFAULT 0,
                vent_allocated INTEGER NOT NULL DEFAULT 0,
                oxy_allocated INTEGER NOT NULL DEFAULT 0,
                hospital_id TEXT NOT NULL DEFAULT 'GEIMS-DDN-01',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Safe schema migration if an older hospital.db already exists
        for col_sql in [
            "ALTER TABLE patients ADD COLUMN vent_allocated INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE patients ADD COLUMN oxy_allocated INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE patients ADD COLUMN hospital_id TEXT NOT NULL DEFAULT 'GEIMS-DDN-01'"
        ]:
            try:
                cursor.execute(col_sql)
            except sqlite3.OperationalError:
                pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lab_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                doctor_id TEXT NOT NULL,
                test_type TEXT NOT NULL,
                result TEXT DEFAULT 'Pending',
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prescriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                doctor_id TEXT NOT NULL,
                medicine_name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Seed multi-resources: ICU_BED, VENTILATOR, OXYGEN
        default_resources = [
            ("ICU_BED", 10, 5),
            ("VENTILATOR", 6, 3),
            ("OXYGEN", 15, 8)
        ]
        for r_name, total, avail in default_resources:
            cursor.execute("SELECT available_count FROM resources WHERE resource_name = ?", (r_name,))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO resources (resource_name, total_count, available_count) VALUES (?, ?, ?)",
                    (r_name, total, avail)
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_all_resources() -> Dict[str, Dict[str, int]]:
    """Returns total and available counts for all hospital resources."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT resource_name, total_count, available_count FROM resources")
        rows = cursor.fetchall()
        result = {}
        for r in rows:
            result[r["resource_name"]] = {
                "total": int(r["total_count"]),
                "available": int(r["available_count"])
            }
        return result
    finally:
        conn.close()


def get_available_beds() -> int:
    """Returns currently available ICU beds from SQLite."""
    res = get_all_resources()
    return res.get("ICU_BED", {}).get("available", 0)


def allocate_bed_and_admit(
    patient_id: str,
    name: str,
    condition: str,
    priority: int,
    is_safe: bool = True,
    hospital_id: str = "GEIMS-DDN-01"
):
    """
    Executes Multi-Resource Banker's safety check and atomic SQLite resource allocation.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute("SELECT resource_name, available_count FROM resources")
        available = {row["resource_name"]: int(row["available_count"]) for row in cursor.fetchall()}

        cursor.execute("""
            SELECT patient_id, bed_allocated AS ICU_BED, vent_allocated AS VENTILATOR, oxy_allocated AS OXYGEN
            FROM patients WHERE bed_allocated = 1
        """)
        active_allocs = [dict(row) for row in cursor.fetchall()]

        req = os_engine.get_resource_requirements(condition, priority)

        if priority == 4:
            status = "General Ward / OPD Assigned (No ICU Resources Required)"
            bed_alloc, vent_alloc, oxy_alloc = 0, 0, 0
            admitted = True
            safe_seq = []
        else:
            banker_safe, safe_seq = os_engine.check_multi_resource_safety(available, active_allocs, req)
            if is_safe and banker_safe:
                for r_name, count in req.items():
                    if count > 0:
                        cursor.execute(
                            "UPDATE resources SET available_count = available_count - ? WHERE resource_name = ?",
                            (count, r_name)
                        )
                        available[r_name] -= count
                bed_alloc = req["ICU_BED"]
                vent_alloc = req["VENTILATOR"]
                oxy_alloc = req["OXYGEN"]
                status = f"ICU Allocated (Bed:{bed_alloc}, Vent:{vent_alloc}, Oxy:{oxy_alloc})"
                admitted = True
            else:
                status = "Queued (Waiting in Priority Schedule)"
                bed_alloc, vent_alloc, oxy_alloc = 0, 0, 0
                admitted = False

        cursor.execute("""
            INSERT OR REPLACE INTO patients
            (patient_id, name, condition, priority, status, bed_allocated, vent_allocated, oxy_allocated, hospital_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (patient_id, name, condition, priority, status, bed_alloc, vent_alloc, oxy_alloc, hospital_id))

        conn.commit()
        return {
            "admitted": admitted,
            "status": status,
            "remaining_beds": available.get("ICU_BED", 0),
            "resources": available,
            "safe_sequence": safe_seq
        }
    except Exception as e:
        conn.rollback()
        return {"admitted": False, "status": "Error", "error": str(e)}
    finally:
        conn.close()


def _promote_waiting_patients_in_tx(cursor):
    """
    OS Scheduler: Automatically promotes highest-priority (Priority 1 -> 4, then FCFS)
    queued patients when ICU resources are released.
    """
    cursor.execute("""
        SELECT patient_id, name, condition, priority
        FROM patients
        WHERE status LIKE 'Queued%'
        ORDER BY priority ASC, created_at ASC
    """)
    waiting_list = cursor.fetchall()
    promoted = []

    for pat in waiting_list:
        req = os_engine.get_resource_requirements(pat["condition"], int(pat["priority"]))
        cursor.execute("SELECT resource_name, available_count FROM resources")
        available = {r["resource_name"]: int(r["available_count"]) for r in cursor.fetchall()}

        if all(available.get(k, 0) >= v for k, v in req.items()):
            for r_name, count in req.items():
                if count > 0:
                    cursor.execute(
                        "UPDATE resources SET available_count = available_count - ? WHERE resource_name = ?",
                        (count, r_name)
                    )
            new_status = f"Auto-Promoted from Queue -> ICU (Bed:{req['ICU_BED']}, Vent:{req['VENTILATOR']}, Oxy:{req['OXYGEN']})"
            cursor.execute("""
                UPDATE patients
                SET status = ?, bed_allocated = ?, vent_allocated = ?, oxy_allocated = ?
                WHERE patient_id = ?
            """, (new_status, req["ICU_BED"], req["VENTILATOR"], req["OXYGEN"], pat["patient_id"]))
            promoted.append(pat["patient_id"])

    return promoted


def release_bed_on_completion(patient_id: str):
    """
    Releases all allocated resources (ICU Bed, Ventilator, Oxygen) when a patient is discharged
    and triggers the OS Priority Queue Scheduler to promote waiting patients.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute(
            "SELECT bed_allocated, vent_allocated, oxy_allocated, status FROM patients WHERE patient_id = ?",
            (patient_id,)
        )
        row = cursor.fetchone()

        if not row:
            conn.rollback()
            return {"released": False, "message": "Patient not found", "promoted": []}

        bed = int(row["bed_allocated"])
        vent = int(row["vent_allocated"])
        oxy = int(row["oxy_allocated"])

        if bed > 0 or vent > 0 or oxy > 0:
            for r_name, val in [("ICU_BED", bed), ("VENTILATOR", vent), ("OXYGEN", oxy)]:
                if val > 0:
                    cursor.execute(
                        "UPDATE resources SET available_count = MIN(total_count, available_count + ?) WHERE resource_name = ?",
                        (val, r_name)
                    )
            cursor.execute("""
                UPDATE patients
                SET bed_allocated = 0, vent_allocated = 0, oxy_allocated = 0,
                    status = 'Discharged (ICU Resources Released)'
                WHERE patient_id = ?
            """, (patient_id,))
            promoted = _promote_waiting_patients_in_tx(cursor)
            conn.commit()
            promo_msg = f" | Auto-Promoted from Queue: {', '.join(promoted)}" if promoted else ""
            return {"released": True, "message": f"Resources Released (+{bed} Bed, +{vent} Vent, +{oxy} Oxy){promo_msg}", "promoted": promoted}
        else:
            cursor.execute(
                "UPDATE patients SET status = 'Treatment Completed (OPD)' WHERE patient_id = ?",
                (patient_id,)
            )
            conn.commit()
            return {"released": False, "message": "OPD Treatment Completed (No ICU resources held)", "promoted": []}
    except Exception as e:
        conn.rollback()
        return {"released": False, "message": str(e), "promoted": []}
    finally:
        conn.close()


def save_lab_request(patient_id: str, doctor_id: str, test_type: str):
    """Saves a doctor's lab test request persistently in SQLite."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO lab_tests (patient_id, doctor_id, test_type, result, status) VALUES (?, ?, ?, 'Awaiting Lab', 'Requested')",
            (patient_id, doctor_id, test_type)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def complete_lab_report(patient_id: str, doctor_id: str, result: str):
    """Updates pending lab test with findings or creates a completed lab record in SQLite."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM lab_tests WHERE patient_id = ? AND status = 'Requested' ORDER BY id DESC LIMIT 1",
            (patient_id,)
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE lab_tests SET result = ?, status = 'Completed', doctor_id = ? WHERE id = ?",
                (result, doctor_id, row["id"])
            )
        else:
            cursor.execute(
                "INSERT INTO lab_tests (patient_id, doctor_id, test_type, result, status) VALUES (?, ?, 'Emergency Diagnostics', ?, 'Completed')",
                (patient_id, doctor_id, result)
            )
        conn.commit()
        return True
    finally:
        conn.close()


def save_prescription(patient_id: str, doctor_id: str, medicine_name: str):
    """Saves an e-Prescription persistently in SQLite."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO prescriptions (patient_id, doctor_id, medicine_name, status) VALUES (?, ?, ?, 'Prescribed (Pending Dispense)')",
            (patient_id, doctor_id, medicine_name)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def mark_prescription_dispensed(patient_id: str, medicine_name: str):
    """Marks a patient's prescription as Dispensed in SQLite."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM prescriptions WHERE patient_id = ? AND status LIKE 'Prescribed%' ORDER BY id DESC LIMIT 1",
            (patient_id,)
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE prescriptions SET status = 'Dispensed', medicine_name = ? WHERE id = ?",
                (medicine_name, row["id"])
            )
        else:
            cursor.execute(
                "INSERT INTO prescriptions (patient_id, doctor_id, medicine_name, status) VALUES (?, 'D505', ?, 'Dispensed')",
                (patient_id, medicine_name)
            )
        conn.commit()
    finally:
        conn.close()


def get_patient_status(patient_id: str) -> Optional[Dict]:
    """Fetches live patient status, queue position, lab reports, and prescriptions from SQLite."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT patient_id, name, condition, priority, status,
                      bed_allocated, vent_allocated, oxy_allocated, hospital_id, created_at
               FROM patients WHERE patient_id = ?""",
            (patient_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        patient_data = dict(row)

        # Calculate live queue position if patient is waiting
        cursor.execute("""
            SELECT patient_id FROM patients
            WHERE status LIKE 'Queued%'
            ORDER BY priority ASC, created_at ASC
        """)
        queue_ids = [r["patient_id"] for r in cursor.fetchall()]
        patient_data["queue_position"] = (queue_ids.index(patient_id) + 1) if patient_id in queue_ids else 0
        patient_data["total_in_queue"] = len(queue_ids)

        cursor.execute(
            "SELECT test_type, result, status, created_at FROM lab_tests WHERE patient_id = ? ORDER BY id DESC",
            (patient_id,)
        )
        patient_data["lab_tests"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            "SELECT medicine_name, status, created_at FROM prescriptions WHERE patient_id = ? ORDER BY id DESC",
            (patient_id,)
        )
        patient_data["prescriptions"] = [dict(r) for r in cursor.fetchall()]

        return patient_data
    finally:
        conn.close()


def get_all_queues_and_records() -> Dict[str, List[Dict]]:
    """Returns live tables for Admin, Lab, Pharmacy, and Patient Queue dashboards."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM patients ORDER BY priority ASC, created_at DESC")
        patients = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM lab_tests ORDER BY id DESC LIMIT 20")
        labs = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM prescriptions ORDER BY id DESC LIMIT 20")
        rx = [dict(r) for r in cursor.fetchall()]

        return {"patients": patients, "lab_tests": labs, "prescriptions": rx}
    finally:
        conn.close()


def reset_simulation_resources():
    """Resets resource counts and clears tables for clean demo/testing runs."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE resources SET available_count = 5 WHERE resource_name = 'ICU_BED'")
        cursor.execute("UPDATE resources SET available_count = 3 WHERE resource_name = 'VENTILATOR'")
        cursor.execute("UPDATE resources SET available_count = 8 WHERE resource_name = 'OXYGEN'")
        cursor.execute("DELETE FROM patients")
        cursor.execute("DELETE FROM lab_tests")
        cursor.execute("DELETE FROM prescriptions")
        conn.commit()
    finally:
        conn.close()
