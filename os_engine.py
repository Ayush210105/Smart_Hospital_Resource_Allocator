# Triage Priority Logic
def get_priority(condition):
    emergency_keywords = ['heart attack', 'accident', 'stroke', 'emergency']
    if condition.lower() in emergency_keywords:
        return 1  # Priority 1 (High)
    return 4      # Priority 4 (Normal)

# Banker's Algorithm Simulation
def check_bankers_safety(requested_resources, available_resources):
    print("\n[OS ENGINE] Running Banker's Algorithm...")
    
    if requested_resources <= available_resources:
        print("[OS ENGINE] System State: SAFE ✅ (No deadlock detected)")
        return True
    else:
        print("[OS ENGINE] System State: UNSAFE ❌ (Deadlock Risk - Queuing process)")
        return False