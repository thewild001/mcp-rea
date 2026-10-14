"""REA Coordination Model - Manages REA agent coordination data."""

from typing import Dict, List, Optional, Any


class CoordinationModel:
    """Model for tracking REA agent coordination state."""

    def __init__(self):
        # In a real implementation, this would load from a persistent store
        # or REA's internal state
        self._agents: Dict[str, Dict[str, Any]] = {
            "planner": {
                "id": "planner",
                "name": "REA Planner",
                "status": "idle",
                "capabilities": ["implementation_planning", "task_breakdown"],
            },
            "architect": {
                "id": "architect",
                "name": "REA Architect",
                "status": "idle",
                "capabilities": ["system_design", "scalability_analysis"],
            },
            "code_reviewer": {
                "id": "code_reviewer",
                "name": "REA Code Reviewer",
                "status": "idle",
                "capabilities": ["code_review", "quality_metrics"],
            },
            "security_reviewer": {
                "id": "security_reviewer",
                "name": "REA Security Reviewer",
                "status": "idle",
                "capabilities": ["vulnerability_detection", "security_audit"],
            },
            "tdd_guide": {
                "id": "tdd_guide",
                "name": "REA TDD Guide",
                "status": "idle",
                "capabilities": ["test_driven_development", "red_green_refactor"],
            },
        }

    def list_agents(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available REA agents, optionally filtered by category."""
        agents = list(self._agents.values())
        if category:
            # Filter by capabilities containing the category keyword
            agents = [
                a for a in agents
                if any(category in cap for cap in a["capabilities"])
            ]
        return agents

    def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        """Get status of a specific REA agent."""
        agent = self._agents.get(agent_id, {
            "id": agent_id,
            "name": agent_id,
            "status": "unknown",
            "capabilities": [],
        })
        return agent

    def update_agent_status(self, agent_id: str, status: str) -> None:
        """Update agent status."""
        if agent_id in self._agents:
            self._agents[agent_id]["status"] = status

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all agents."""
        return self._agents.copy()
