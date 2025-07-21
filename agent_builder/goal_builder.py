import uuid
from dataclasses import dataclass, asdict
from enum import Enum
from typing import List, Any, Dict, Optional

from agent_builder.agent_factory import AgentContext
from agent_builder.memory_builder import Memory
from agent_builder.resource_registry import ResourceRegistry
from agent_builder.tools_factory import ToolsFactory
from utils.llm_api import infer_llm_json
from utils.prompt_store import PromptStore


class GoalStatus(Enum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"


@dataclass
class GoalItem:
    id: uuid.UUID
    name: str
    description: str
    short_term_goal: str
    long_term_goal: str
    status: GoalStatus = GoalStatus.PENDING
    accomplished: bool = False


def normalize_goal_list(raw: Any) -> List[Dict]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if "goals" in raw and isinstance(raw["goals"], list):
            return raw["goals"]
        if "goal" in raw:
            goal_val = raw["goal"]
            if isinstance(goal_val, list):
                return goal_val
            if isinstance(goal_val, dict):
                return [goal_val]
        for v in raw.values():
            if isinstance(v, list):
                return v
    raise ValueError(f"Could not extract a list of goals from LLM output: {raw!r}")


class GoalFactory:
    def __init__(self, prompt_store: Optional[PromptStore] = None):
        self.goal_items = []
        self.prompt_store = prompt_store or PromptStore()

    def add_goal(self, goal: GoalItem):
        self.goal_items.append(goal)

    def get_goals(self, limit: int = None) -> List[GoalItem]:
        return self.goal_items[:limit]

    def infer_goals(self,
                    task: str,
                    goals: List[GoalItem],
                    progress_report: Dict[str, Any],
                    resources: ResourceRegistry = None,
                    memory: Memory = None,
                    ) -> List[GoalItem]:

        tools_list = resources.get_tools()
        agents = resources.get_agents()

        mem_items = [
            {"type": m["type"], "content": m["content"]}
            for m in memory.get_memories()
            if (
                    m.get("type") == "user"
                    or (m.get("type") == "agent" and "tool" in m.get("content", ""))
                    or (m.get("type") == "environment" and "tool_executed" in m.get("content", ""))
            )
        ]

        if goals:
            serialized_goals = [asdict(item) for item in goals]
        else:
            serialized_goals = []
        prompt_values = {
            "task": task,
            "goals": serialized_goals,
            "progress_report": progress_report,
            "tools": tools_list,
            "agents": agents,
            "memory": mem_items
        }
        agent_goal_builder_prompt = self.prompt_store.get_prompt("agent_goal_builder_instruction", **prompt_values)
        raw = infer_llm_json(agent_goal_builder_prompt)
        goals_list = normalize_goal_list(raw)

        goals: List[GoalItem] = []
        for idx, g in enumerate(goals_list):
            if not isinstance(g, dict):
                raise TypeError(f"Expected each goal to be a dict, got {type(g)}: {g!r}")
            try:
                name = str(g["name"])
                description = str(g["description"])
                short_term_goal = str(g["short_term_goal"])
                long_term_goal = str(g["long_term_goal"])
                status = GoalStatus(g["status"])
                accomplished = bool(g["accomplished"])
            except KeyError as ke:
                raise KeyError(f"Missing field {ke} in goal: {g!r}")
            goal_id = uuid.uuid4()
            goals.append(GoalItem(id=goal_id, name=name, description=description, short_term_goal=short_term_goal,
                                  long_term_goal=long_term_goal, status=status, accomplished=accomplished))

        return goals