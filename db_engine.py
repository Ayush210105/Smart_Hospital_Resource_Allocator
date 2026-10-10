import sqlite3

def init_db():
    conn = sqlite3.connect('hospital.db')
    c = conn.cursor()
    
    # Tables banana (ID ke sath)
    c.execute('''CREATE TABLE IF NOT EXISTS resources (name TEXT PRIMARY KEY, available INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS patients (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, name TEXT, priority INTEGER, status TEXT)''')
    
    # Check agar beds insert nahi hue hain toh 2 ICU beds daal do
    c.execute("SELECT count(*) FROM resources")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO resources (name, available) VALUES ('ICU_Bed', 2)")
    
    conn.commit()
    conn.close()

def allocate_bed_transaction(patient_id, name, priority):
    conn = sqlite3.connect('hospital.db')
    try:
        print("[DBMS] BEGIN TRANSACTION triggered (Row-level lock applied).")
        conn.execute("BEGIN TRANSACTION")
        
        c = conn.cursor()
        c.execute("SELECT available FROM resources WHERE name='ICU_Bed'")
        beds = c.fetchone()[0]
        
        if beds > 0:
            print(f"[DBMS] {beds} ICU beds available. Updating tables...")
            c.execute("UPDATE resources SET available = available - 1 WHERE name='ICU_Bed'")
            c.execute("INSERT INTO patients (patient_id, name, priority, status) VALUES (?, ?, ?, 'Allocated')", (patient_id, name, priority))
            
            conn.commit()
            print("[DBMS] COMMIT successful. Data securely saved.")
            return True
        else:
            print("[DBMS] No beds available! Triggering ROLLBACK to prevent corrupted state.")
            conn.rollback()
            return False
            
    except Exception as e:
        print(f"[DBMS] Error occurred: {e}. Triggering ROLLBACK.")
        conn.rollback()
        return False
    finally:
        conn.close()