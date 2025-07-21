import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any, List

from agent_builder.agent_factory import AgentContext
from agent_builder.resource_registry import ResourceRegistry, Tool
from utils.llm_api import infer_llm_json
from utils.prompt_store import PromptStore


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CLARIFICATION = "clarification"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentFeedback:
    id: uuid.UUID
    task: str = ""
    status: TaskStatus = TaskStatus.PENDING
    reasoning: str = ""


def normalize_feedback(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"Expected dict from LLM for feedback, got: {type(raw)} - {raw!r}")

    def extract_fields(d: Dict[str, Any]) -> Dict[str, Any]:
        status_val = d.get("status")
        reasoning_val = d.get("reasoning", "")
        if not isinstance(status_val, str):
            raise TypeError(f"'status' field must be a string, got {type(status_val)}: {status_val!r}")
        try:
            status_enum = TaskStatus(status_val)
        except ValueError:
            raise ValueError(f"Invalid status value: {status_val!r}")
        return {
            "status": status_enum,
            "reasoning": reasoning_val
        }

    if "status" in raw and "reasoning" in raw:
        return extract_fields(raw)

    for v in raw.values():
        if isinstance(v, dict) and "status" in v and "reasoning" in v:
            return extract_fields(v)

    raise ValueError(f"Could not normalize agent feedback from LLM output: {raw!r}")


class FeedbackBuilder:
    def __init__(self, prompt_store: Optional[PromptStore] = None):
        feedback_id = uuid.uuid4()
        self.agent_feedback = AgentFeedback(id=feedback_id)
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

    def format_action(self, action: ResourceRegistry) -> List[Dict]:
        pass

    def build_agent_feedback(self, task: str, action: ResourceRegistry = None, observation: Any = None,
                             resources: ResourceRegistry = None) -> AgentFeedback:
        tools, agents = resources.get_tools(), resources.get_agents()

        prompt_values = {
            "task": task,
            "action": action,
            "observation": observation,
        }

        agent_feedback_builder_prompt = self.prompt_store.get_prompt("agent_feedback_builder_instruction",
                                                                     **prompt_values)
        res = infer_llm_json(agent_feedback_builder_prompt)
        parsed_agent_feedback = normalize_feedback(res)

        self.agent_feedback = AgentFeedback(
            id=self.agent_feedback.id,
            task=task,
            status=parsed_agent_feedback.get("status", TaskStatus.PENDING),
            reasoning=parsed_agent_feedback.get("reasoning", "")
        )

        return self.agent_feedback
