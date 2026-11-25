from typing import Dict, List, Tuple

EMERGENCY_KEYWORDS = ["Heart Attack", "Accident", "Stroke", "Emergency"]
RESOURCE_TYPES = ["ICU_BED", "VENTILATOR", "OXYGEN"]


def assign_priority(condition: str) -> int:
    if not condition:
        return 4
    for keyword in EMERGENCY_KEYWORDS:
        if keyword.lower() in condition.lower():
            return 1
    return 4


def get_resource_requirements(condition: str, priority: int) -> Dict[str, int]:
    if priority == 4:
        return {"ICU_BED": 0, "VENTILATOR": 0, "OXYGEN": 0}

    cond_lower = (condition or "").lower()
    if "heart attack" in cond_lower or "stroke" in cond_lower:
        return {"ICU_BED": 1, "VENTILATOR": 1, "OXYGEN": 1}
    return {"ICU_BED": 1, "VENTILATOR": 0, "OXYGEN": 1}


def check_safety(requested_beds: int, available_beds: int) -> bool:
    if requested_beds <= 0:
        return False
    return available_beds >= requested_beds


def check_multi_resource_safety(
    available: Dict[str, int],
    active_allocations: List[Dict[str, int]],
    request: Dict[str, int]
) -> Tuple[bool, List[str]]:
    for r in RESOURCE_TYPES:
        if request.get(r, 0) > available.get(r, 0):
            return False, []

    work = {r: available.get(r, 0) - request.get(r, 0) for r in RESOURCE_TYPES}

    processes = []
    for idx, proc in enumerate(active_allocations):
        processes.append({
            "pid": proc.get("patient_id", f"P_{idx}"),
            "alloc": {r: int(proc.get(r, 0)) for r in RESOURCE_TYPES},
            "need": {r: 0 for r in RESOURCE_TYPES}
        })

    processes.append({
        "pid": "NEW_REQUEST",
        "alloc": {r: int(request.get(r, 0)) for r in RESOURCE_TYPES},
        "need": {r: 0 for r in RESOURCE_TYPES}
    })

    finish = [False] * len(processes)
    safe_sequence = []

    while True:
        progressed = False
        for i, proc in enumerate(processes):
            if not finish[i]:
                if all(proc["need"][r] <= work[r] for r in RESOURCE_TYPES):
                    for r in RESOURCE_TYPES:
                        work[r] += proc["alloc"][r]
                    finish[i] = True
                    safe_sequence.append(proc["pid"])
                    progressed = True
        if not progressed:
            break

    return all(finish), safe_sequence
