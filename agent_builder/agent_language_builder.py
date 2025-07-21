import json
from dataclasses import dataclass, field
from typing import List, Dict, Any

from agent_builder.agent_factory import AgentContext
from agent_builder.context_builder import TurnContext
from agent_builder.resource_registry import Tool, ToolContext
from agent_builder.environment_builder import Environment
from agent_builder.goal_builder import GoalItem
from agent_builder.memory_builder import Memory
from utils.prompt_store import PromptStore


@dataclass
class Prompt:
    task: str = ""
    goals: List[Dict] = field(default_factory=list)
    memory: List[Dict] = field(default_factory=list)
    tools: List[Dict] = field(default_factory=list)
    agents: List[Dict] = field(default_factory=list)
    turn_context: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)


class AgentLanguage:
    def __init__(self):
        self.prompt_store = PromptStore()

    def construct_prompt(self,
                         task: str,
                         goals: List[GoalItem],
                         memory: Memory,
                         tools: List[Tool],
                         inject_prompt_instruction: str,
                         environment: Environment,
                         agents: List[AgentContext] = None,
                         turn_context: TurnContext = None,
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

    def format_goals(self, goals: List[GoalItem]) -> List:
        sep = "\n-------------------\n"
        # goal_instructions = "\n\n".join([f"{goal.name}:{sep}{goal.description}{sep}" for goal in goals])
        goal_instructions = "\n\n".join([f"{goal.short_term_goal}:{sep}{goal.long_term_goal}{sep}:{sep}{goal.status}{sep}::{sep}{goal.accomplished}{sep}" for goal in goals])
        return [
            {"role": "system", "content": goal_instructions}
        ]

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
            "context": turn_context.context  # assuming it's already a JSON-serializable array
        }
        return serialized_turn_context



    def construct_prompt(self,
                         task: str,
                         goals: List[GoalItem],
                         memory: Memory,
                         tools: List[Tool],
                         inject_prompt_instruction: str,
                         environment: Environment,
                         agents: List[AgentContext] = None,
                         turn_context: TurnContext = None,
                         tool_context: ToolContext = None,
                         schema: Dict = None) -> Prompt:

        formatted_prompt = Prompt(
            task=task,
            goals=self.format_goals(goals),
            memory=self.format_memory(memory),
            tools=self.format_tools(tools),
            agents=self.format_agents(agents) if agents else None,
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
