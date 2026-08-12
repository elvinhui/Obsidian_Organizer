import sqlite3
import json
import os
from .models import PSI5State, AgentContext, SimulationResult, MemoryEntry

DB_PATH = os.path.join(os.path.dirname(__file__), "laap_memory.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            context TEXT NOT NULL,
            psi5_before TEXT NOT NULL,
            simulation_result TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def save_memory(entry: MemoryEntry):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO memory (timestamp, context, psi5_before, simulation_result)
        VALUES (?, ?, ?, ?)
    ''', (
        entry.timestamp,
        entry.context.model_dump_json(),
        entry.psi5_state_before.model_dump_json(),
        entry.simulation_result.model_dump_json()
    ))
    conn.commit()
    conn.close()

def get_latest_psi5() -> PSI5State:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT simulation_result FROM memory ORDER BY id DESC LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    
    if row:
        sim_res = SimulationResult.model_validate_json(row[0])
        return sim_res.psi5_after
    return PSI5State() # return default 100/80 state if no history

def get_memory_history(limit=5) -> list[MemoryEntry]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, timestamp, context, psi5_before, simulation_result FROM memory ORDER BY id DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for r in rows:
        history.append(MemoryEntry(
            id=r[0],
            timestamp=r[1],
            context=AgentContext.model_validate_json(r[2]),
            psi5_state_before=PSI5State.model_validate_json(r[3]),
            simulation_result=SimulationResult.model_validate_json(r[4])
        ))
    return history
