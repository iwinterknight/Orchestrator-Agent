import json
import uuid
from dataclasses import dataclass, field, is_dataclass, asdict
from typing import List, Dict, Any

from agent_builder.agent_factory import AgentContext
from agent_builder.context_builder import TurnContext
from agent_builder.environment_builder import Environment
from agent_builder.feedback_builder import AgentFeedback
from agent_builder.memory_builder import Memory
from agent_builder.plan_builder import Plan
from agent_builder.resource_registry import Tool, ToolContext
from utils.prompt_store import PromptStore


@dataclass
class Prompt:
    task: str = ""
    plan: Dict = field(default_factory=dict)
    memory: Any = None
    tools: List[Dict] = field(default_factory=list)
    agents: List[Dict] = field(default_factory=list)
    turn_context: Dict = field(default_factory=dict)
    feedback: Dict[str, Any] = field(default_factory=dict)


class AgentLanguage:
    def __init__(self):
        self.prompt_store = PromptStore()

    def construct_prompt(self,
                         task: str,
                         plan: Plan,
                         tools: List[Tool],
                         inject_prompt_instruction: str,
                         environment: Environment,
                         memory: Memory = None,
                         agents: List[AgentContext] = None,
                         turn_context: TurnContext = None,
                         feedback: AgentFeedback = None,
                         tool_context: ToolContext = None,
                         schema: Dict = None) -> Prompt:
        raise NotImplementedError("Subclasses must implement this method")

    def parse_response(self, response: str) -> dict:
        raise NotImplementedError("Subclasses must implement this method")


class AgentFunctionCallingActionLanguage(AgentLanguage):
    def __init__(self):
        super().__init__()

    def format_memory(self, memory: Memory) -> List:
        items = memory.get_memories()
        mapped_items = []
        for item in items:
            content = item.get("content", None)
            if not content:
                content = json.dumps(item, indent=4)

            if item["type"] == "agent":
                mapped_items.append({"role": "agent", "content": content})
            elif item["type"] == "environment":
                mapped_items.append({"role": "system", "content": content})
            else:
                mapped_items.append({"role": "user", "content": content})

        return mapped_items

    def format_plan(self, plan: Plan = None) -> Dict:
        if plan:
            if is_dataclass(plan):
                data = asdict(plan)
            elif hasattr(plan, "__dict__"):
                data = plan.__dict__.copy()
            else:
                raise TypeError(f"Cannot convert object of type {type(plan)} to dict")

            id_val = data.get("id")
            if isinstance(id_val, uuid.UUID):
                data["id"] = str(id_val)

            return data
        return {}

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

    def format_turn_context(self, turn_context: TurnContext) -> Dict:
        serialized_turn_context = {
            "id": str(turn_context.id),
            "task": turn_context.task,
            "context": turn_context.context,  # assuming it's already a JSON-serializable array
            "data": turn_context.data
        }
        return serialized_turn_context

    def format_agent_feedback(self, agent_feedback: AgentFeedback) -> Dict[str, Any]:
        return {
            "id": str(agent_feedback.id),
            "task": agent_feedback.task,
            "status": agent_feedback.status.value,
            "reasoning": agent_feedback.reasoning,
        }

    def construct_prompt(self,
                         task: str,
                         plan: Plan,
                         tools: List[Tool],
                         inject_prompt_instruction: str,
                         environment: Environment,
                         memory: Memory = None,
                         agents: List[AgentContext] = None,
                         turn_context: TurnContext = None,
                         feedback: AgentFeedback = None,
                         tool_context: ToolContext = None,
                         schema: Dict = None) -> Prompt:

        formatted_prompt = Prompt(
            task=task,
            plan=self.format_plan(plan),
            tools=self.format_tools(tools) if tools else None,
            agents=self.format_agents(agents) if agents else None,
            memory=memory if memory else None,
            feedback=self.format_agent_feedback(feedback) if feedback else None,
            turn_context=self.format_turn_context(turn_context) if turn_context else None
        )

        return formatted_prompt

    def adapt_prompt_after_parsing_error(self,
                                         prompt: Prompt,
                                         response: str,
                                         traceback: str,
                                         error: Any,
                                         retries_left: int) -> Prompt:

        return prompt
