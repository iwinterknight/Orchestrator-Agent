import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List

from agent_builder.agent_factory import AgentContext
from agent_builder.feedback_builder import AgentFeedback
from agent_builder.memory_builder import Memory
from agent_builder.resource_registry import ResourceRegistry, Tool
from utils.llm_api import infer_llm_json
from utils.prompt_store import PromptStore


@dataclass
class Plan:
    id: uuid.UUID
    task: str = ""
    plan: Any = field(default=None)


def normalize_plan(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError(f"Could not parse LLM output as JSON: {raw!r}")

    if not isinstance(raw, dict):
        raise ValueError(f"Expected a dict with 'task' and 'plan', got {type(raw)}: {raw!r}")

    if "task" not in raw or "plan" not in raw:
        raise KeyError(f"Missing 'task' or 'plan' in LLM output: {raw!r}")

    task = raw["task"]
    plan = raw["plan"]

    if isinstance(plan, str):
        plan_str = plan.strip()
        if plan_str.startswith("{") or plan_str.startswith("["):
            try:
                plan = json.loads(plan_str)
            except json.JSONDecodeError:
                pass

    return {"task": task, "plan": plan}


class PlanBuilder:
    def __init__(self, prompt_store: Optional[PromptStore] = None):
        plan_id = uuid.uuid4()
        self.plan: Plan = Plan(id=plan_id)
        self.prompt_store = prompt_store or PromptStore()

    def format_tools(self, tools: List[Tool], limit=1024) -> List[Dict]:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description[:limit],
                    "parameters": tool.parameters,
                },
            } for tool in tools
        ]
        return tools

    def format_agents(self, agents: List[AgentContext]) -> List[Dict]:
        formatted_agents = []
        for agent_context in agents:
            context_item = {
                "name": agent_context.agent_card.name,
                "persona": agent_context.agent_card.persona,
                "description": agent_context.agent_card.description,
                "skills": agent_context.agent_card.skills,
                "interaction_summary": agent_context.interaction_summary
            }
            formatted_agents.append(context_item)
        return formatted_agents

    def format_agent_feedback(self, agent_feedback: AgentFeedback) -> Dict[str, Any]:
        return {
            "id": str(agent_feedback.id),
            "task": agent_feedback.task,
            "status": agent_feedback.status.value,
            "reasoning": agent_feedback.reasoning,
        }

    def build_plan(self,
                   task: str,
                   feedback: AgentFeedback = None,
                   resources: ResourceRegistry = None,
                   memory: Memory = None,
                   ) -> Plan:
        tools = resources.get_tools()
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

        prompt_values = {
            "task": task,
            "feedback": self.format_agent_feedback(feedback) if feedback else None,
            "tools": self.format_tools(tools) if tools else None,
            "agents": self.format_agents(agents) if agents else None,
            "memory": mem_items
        }
        agent_goal_builder_prompt = self.prompt_store.get_prompt("agent_plan_builder_instruction", **prompt_values)
        raw = infer_llm_json(agent_goal_builder_prompt)
        parsed_plan = normalize_plan(raw)

        self.plan = Plan(
            id=self.plan.id,
            task=parsed_plan["task"],
            plan=parsed_plan["plan"]
        )

        return self.plan
