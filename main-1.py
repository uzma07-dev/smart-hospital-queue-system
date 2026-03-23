from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import datetime

app = FastAPI(title="SmartQueue AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

queue_store = []

SYMPTOM_WEIGHTS = {
    "chest": ("Critical", 95),
    "heart": ("Critical", 92),
    "breath": ("Critical", 90),
    "bleed": ("Critical", 88),
    "stroke": ("Critical", 87),
    "seizure": ("Critical", 85),
    "fracture": ("Urgent", 70),
    "pain": ("Urgent", 65),
    "fever": ("Urgent", 60),
    "vomit": ("Urgent", 55),
    "nausea": ("Urgent", 50),
    "dizzy": ("Urgent", 58),
    "rash": ("Regular", 35),
    "cough": ("Regular", 30),
    "cold": ("Regular", 25),
    "checkup": ("Regular", 20),
}

DEPT_BASE_WAIT = {
    "Cardiology": 20,
    "Emergency": 5,
    "Orthopedics": 25,
    "General OPD": 30,
    "Neurology": 22,
    "Pediatrics": 18,
}

def triage_score(symptoms, age):
    text = symptoms.lower()
    best_priority = "Regular"
    best_score = 20
    for keyword in SYMPTOM_WEIGHTS:
        priority, score = SYMPTOM_WEIGHTS[keyword]
        if keyword in text and score > best_score:
            best_score = score
            best_priority = priority
    if age >= 70 and best_priority == "Regular":
        best_priority = "Urgent"
        best_score = 55
    return best_priority, best_score

def predict_wait_time(department, priority):
    base = DEPT_BASE_WAIT.get(department, 25)
    modifier = {"Critical": 0.2, "Urgent": 0.6, "Regular": 1.0}[priority]
    return max(2, int(base * modifier))

class PatientIn(BaseModel):
    name: str
    age: int
    department: str
    symptoms: str

@app.get("/")
def root():
    return {"message": "SmartQueue AI Backend Running"}

@app.post("/api/checkin")
def checkin(patient: PatientIn):
    priority, score = triage_score(patient.symptoms, patient.age)
    wait_min = predict_wait_time(patient.department, priority)
    token = "T-" + str(uuid.uuid4())[:4].upper()
    entry = {
        "token": token,
        "name": patient.name,
        "department": patient.department,
        "priority": priority,
        "triage_score": score,
        "est_wait_min": wait_min,
        "checked_in": datetime.datetime.utcnow().isoformat(),
        "status": "Waiting"
    }
    queue_store.append(entry)
    return entry

@app.get("/api/queue")
def get_queue():
    order = {"Critical": 0, "Urgent": 1, "Regular": 2}
    return sorted(queue_store, key=lambda x: order[x["priority"]])

@app.get("/api/queue/{token}")
def get_patient(token: str):
    for p in queue_store:
        if p["token"] == token:
            return p
    raise HTTPException(status_code=404, detail="Patient not found")

@app.post("/api/emergency")
def declare_emergency():
    for p in queue_store:
        if p["status"] == "Waiting":
            p["est_wait_min"] = int(p["est_wait_min"] * 1.2)
    return {"status": "recalculated", "affected": len(queue_store)}

@app.put("/api/queue/{token}/status")
def update_status(token: str, status: str):
    for p in queue_store:
        if p["token"] == token:
            p["status"] = status
            return p
    raise HTTPException(status_code=404, detail="Not found")

@app.get("/api/stats")
def get_stats():
    total = len(queue_store)
    critical = sum(1 for p in queue_store if p["priority"] == "Critical")
    urgent = sum(1 for p in queue_store if p["priority"] == "Urgent")
    avg_wait = round(sum(p["est_wait_min"] for p in queue_store) / max(total, 1), 1)
    return {
        "total": total,
        "critical": critical,
        "urgent": urgent,
        "avg_wait_min": avg_wait
    }

@app.delete("/api/queue/{token}")
def remove_patient(token: str):
    global queue_store
    before = len(queue_store)
    queue_store = [p for p in queue_store if p["token"] != token]
    if len(queue_store) == before:
        raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": token}
