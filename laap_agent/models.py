from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class PSI5State(BaseModel):
    """
    PSI5 Needs-Driven System State
    All values are 0-100, where 100 means the need is fully satisfied.
    """
    energy: float = Field(default=100.0, description="认知带宽与物理精力 (Energy)")
    certainty: float = Field(default=80.0, description="对环境与未来的确定感 (Certainty)")
    competence: float = Field(default=80.0, description="掌控感与胜任能力 (Competence)")
    autonomy: float = Field(default=100.0, description="自主选择权 (Autonomy)")
    affiliation: float = Field(default=50.0, description="归属感与连接 (Affiliation)")

class AgentContext(BaseModel):
    """
    Context perceived by the agent from the environment (Obsidian).
    """
    pending_tasks: List[str] = Field(default_factory=list)
    recent_insights: List[str] = Field(default_factory=list)
    review_stats: dict = Field(default_factory=dict)
    identity_kernel: str = Field(default="")

class SimulationResult(BaseModel):
    """
    The result of a forward simulation by the LLM.
    """
    date: str
    psi5_after: PSI5State
    analysis: str
    action_advice: str
    
class MemoryEntry(BaseModel):
    id: Optional[int] = None
    timestamp: str
    context: AgentContext
    psi5_state_before: PSI5State
    simulation_result: SimulationResult
