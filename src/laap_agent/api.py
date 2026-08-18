from fastapi import FastAPI, BackgroundTasks
from .models import PSI5State
from .db import get_latest_psi5, init_db
from .engine import run_daily_simulation

app = FastAPI(title="LAAP Agent Internal API")

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/status", response_model=PSI5State)
def get_status():
    """Returns the latest PSI5 state of the agent."""
    return get_latest_psi5()

@app.post("/trigger_simulation")
def trigger_simulation(background_tasks: BackgroundTasks):
    """Triggers a forward simulation manually."""
    background_tasks.add_task(run_daily_simulation)
    return {"message": "Simulation triggered in background."}
