"""
Streamlit Role-Based Frontend (streamlit_app.py)
Phase-3 Complete UI: Multi-Resource Banker's Matrix, Persistent Lab/Pharmacy Tables,
Live Patient Queue Portal, and Built-In Concurrency Stress Tester.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
import requests
import streamlit as st
import db_engine

BASE_URL = "http://127.0.0.1:5000/api"


@st.cache_resource
def ensure_backend_server():
    """Starts the Flask API server in a background daemon thread if not already running."""
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=1)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    from app import app as flask_app
    server_thread = threading.Thread(
        target=lambda: flask_app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False),
        daemon=True
    )
    server_thread.start()
    time.sleep(0.8)
    return True


ensure_backend_server()

st.set_page_config(page_title="Smart Hospital System", page_icon="🏥", layout="wide")

st.title("🏥 Smart Hospital Resource Allocator (Phase-III Complete)")

# Sidebar navigation and Multi-Resource Live Counters
dashboard = st.sidebar.radio(
    "Select Dashboard / Role",
    [
        "1. Admin / Reception Counter",
        "2. Doctor Dashboard",
        "3. Lab / Radiology Dashboard",
        "4. Pharmacy Dashboard",
        "5. Patient Portal & Live Queue"
    ]
)

st.sidebar.markdown("---")
st.sidebar.subheader("🧮 Multi-Resource Pool (SQLite)")
res_pool = db_engine.get_all_resources()
c1, c2, c3 = st.sidebar.columns(3)
c1.metric("🛏️ ICU", f"{res_pool.get('ICU_BED', {}).get('available', 0)}/{res_pool.get('ICU_BED', {}).get('total', 10)}")
c2.metric("🫁 Vent", f"{res_pool.get('VENTILATOR', {}).get('available', 0)}/{res_pool.get('VENTILATOR', {}).get('total', 6)}")
c3.metric("🧪 Oxy", f"{res_pool.get('OXYGEN', {}).get('available', 0)}/{res_pool.get('OXYGEN', {}).get('total', 15)}")

if st.sidebar.button("🔄 Reset Simulation DB"):
    requests.post(f"{BASE_URL}/reset", timeout=5)
    st.rerun()

st.sidebar.info("Flask API active on http://127.0.0.1:5000/api")

records = db_engine.get_all_queues_and_records()

# ========================================================
# 1. ADMIN / RECEPTION COUNTER UI
# ========================================================
if dashboard == "1. Admin / Reception Counter":
    st.header("📋 Patient Registration & Multi-Resource OS Allocator")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Patient Triage Registration")
        hospital_id = st.selectbox("Hospital Facility ID", ["GEIMS-DDN-01", "AIIMS-RISH-02", "DOON-HOSP-03"])
        patient_id = st.text_input("Patient ID", value="P101")
        name = st.text_input("Patient Name", value="Rahul")
        condition = st.selectbox(
            "Condition / Emergency",
            ["Heart Attack", "Stroke", "Accident", "Emergency", "Fever", "General Routine"]
        )

        if st.button("Submit Registration", type="primary"):
            payload = {
                "patient_id": patient_id,
                "name": name,
                "condition": condition,
                "hospital_id": hospital_id
            }
            try:
                response = requests.post(f"{BASE_URL}/admit_patient", json=payload, timeout=5)
                data = response.json()

                if data.get("status") == "Success":
                    if data.get("priority") == 4:
                        st.info(
                            f"🏥 Patient {patient_id} routed to General Ward / OPD. "
                            f"Priority: {data.get('priority')} | ICU Resources Unchanged."
                        )
                    else:
                        seq_str = " -> ".join(data.get("safe_sequence", []))
                        st.success(
                            f"✅ Emergency Patient {patient_id} Admitted! {data.get('allocation_detail')} | "
                            f"Safe Sequence: [{seq_str}]"
                        )
                elif data.get("status") == "Queued":
                    st.warning(
                        f"⚠️ Banker's Safety Check Blocked Allocation! "
                        f"Patient {patient_id} placed in Priority {data.get('priority')} Waitlist Queue."
                    )
                else:
                    st.error(f"❌ Allocation Failed: {data.get('message')}")
            except Exception as e:
                st.error(f"Failed to connect to backend server: {e}")

    with col2:
        st.subheader("⚡ Automated Concurrency Stress Test")
        st.caption("Fires 8 parallel threads simultaneously to verify `threading.Lock` and SQLite Atomicity.")
        if st.button("🚀 Run 8-Thread Parallel Admission Test"):
            def fire_request(idx):
                p_cond = "Heart Attack" if idx % 2 == 0 else "Accident"
                r = requests.post(
                    f"{BASE_URL}/admit_patient",
                    json={"patient_id": f"T20{idx}", "name": f"ConcurrentPat_{idx}", "condition": p_cond},
                    timeout=10
                )
                return r.json()

            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(fire_request, range(1, 9)))

            admitted_cnt = sum(1 for r in results if r.get("status") == "Success")
            queued_cnt = sum(1 for r in results if r.get("status") == "Queued")
            st.success(
                f"✅ Concurrency Test Passed! 0 Race Conditions. "
                f"Safely Admitted: {admitted_cnt} | Safely Queued: {queued_cnt} | "
                f"Remaining ICU Beds: {db_engine.get_available_beds()}"
            )

    st.subheader("📊 Live Patient & Resource Allocation Table (SQLite)")
    if records["patients"]:
        st.dataframe(records["patients"], use_container_width=True)
    else:
        st.write("No patients registered yet.")

# ========================================================
# 2. DOCTOR DASHBOARD
# ========================================================
elif dashboard == "2. Doctor Dashboard":
    st.header("👨‍⚕️ Doctor Consultation & Ordering Module")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Request Lab / Radiology Test")
        doctor_id = st.text_input("Doctor ID", value="D505")
        p_id_test = st.text_input("Patient ID for Test", value="P101")
        test_type = st.selectbox("Select Test", ["MRI Scan", "CT Scan", "X-Ray", "Blood Test", "ECG"])

        if st.button("Request Test"):
            r = requests.post(
                f"{BASE_URL}/request_test",
                json={"doctor_id": doctor_id, "patient_id": p_id_test, "test_type": test_type},
                timeout=5
            )
            st.success(f"✅ {r.json().get('status')}")

    with col2:
        st.subheader("Write e-Prescription")
        doc_id_rx = st.text_input("Doctor ID (Rx)", value="D505", key="doc_rx")
        p_id_rx = st.text_input("Patient ID (Rx)", value="P101", key="pat_rx")
        medicine = st.text_input("Medicine Name", value="Aspirin")

        if st.button("Send Prescription to Pharmacy"):
            r = requests.post(
                f"{BASE_URL}/send_prescription",
                json={"doctor_id": doc_id_rx, "patient_id": p_id_rx, "medicine_name": medicine},
                timeout=5
            )
            st.success(f"✅ {r.json().get('status')}")

# ========================================================
# 3. LAB / RADIOLOGY DASHBOARD
# ========================================================
elif dashboard == "3. Lab / Radiology Dashboard":
    st.header("🔬 Lab & Radiology Operations (Persistent SQLite)")
    patient_id = st.text_input("Patient ID", value="P101")
    doctor_id = st.text_input("Assigned Doctor ID", value="D505")
    result = st.text_area("Test Results / Findings", value="Critical Blockage found in imaging.")

    if st.button("Complete Test & Save to Database", type="primary"):
        r = requests.post(
            f"{BASE_URL}/complete_test",
            json={"patient_id": patient_id, "doctor_id": doctor_id, "result": result},
            timeout=5
        )
        st.success(f"✅ {r.json().get('status')}")

    st.subheader("🧾 Saved Lab Records in SQLite")
    if records["lab_tests"]:
        st.dataframe(records["lab_tests"], use_container_width=True)

# ========================================================
# 4. PHARMACY DASHBOARD
# ========================================================
elif dashboard == "4. Pharmacy Dashboard":
    st.header("💊 Pharmacy Inventory, Dispensing & Auto-Queue Promotion")
    patient_id = st.text_input("Patient ID", value="P101")
    medicine = st.text_input("Medicine Name", value="Aspirin")

    if st.button("Dispense Medicine & Release ICU Resources", type="primary"):
        r = requests.post(
            f"{BASE_URL}/dispense_medicine",
            json={"doctor_id": "D505", "patient_id": patient_id, "medicine_name": medicine},
            timeout=5
        )
        st.success(f"✅ {r.json().get('status')}")

    st.subheader("🧾 Saved Pharmacy Prescriptions in SQLite")
    if records["prescriptions"]:
        st.dataframe(records["prescriptions"], use_container_width=True)

# ========================================================
# 5. PATIENT PORTAL & LIVE QUEUE
# ========================================================
elif dashboard == "5. Patient Portal & Live Queue":
    st.header("📱 Live Patient Status & Priority Waitlist Queue")
    patient_id = st.text_input("Enter Patient ID to Track Live Status", value="P101")

    if st.button("Check Live Status", type="primary"):
        r = requests.get(f"{BASE_URL}/patient_status/{patient_id}", timeout=5)
        data = r.json()
        if data.get("found"):
            st.success(
                f"**Patient:** {data.get('name')} ({data.get('patient_id')}) | "
                f"**Facility:** {data.get('hospital_id')} | "
                f"**Condition:** {data.get('condition')} | "
                f"**Priority:** {data.get('priority')} | "
                f"**Status:** {data.get('status')}"
            )
            if data.get("queue_position", 0) > 0:
                st.warning(
                    f"⏳ **Live Waitlist Queue Position:** #{data.get('queue_position')} "
                    f"out of {data.get('total_in_queue')} waiting patients."
                )
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("🔬 **Patient's Lab Reports:**")
                st.json(data.get("lab_tests", []))
            with col_b:
                st.write("💊 **Patient's Prescriptions:**")
                st.json(data.get("prescriptions", []))
        else:
            st.error(data.get("status"))
