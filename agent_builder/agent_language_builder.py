import json
from dataclasses import dataclass, field
from typing import List, Dict, Any

from agent_builder.agent_factory import AgentContext
from agent_builder.resource_registry import Action, ActionContext
from agent_builder.environment_builder import Environment
from agent_builder.goal_builder import GoalItem
from agent_builder.memory_builder import Memory
from utils.prompt_store import PromptStore


@dataclass
class Prompt:
    task: str = ""
    goals: List[Dict] = field(default_factory=list)
    memory: List[Dict] = field(default_factory=list)
    actions: List[Dict] = field(default_factory=list)
    agents: List[Dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class AgentLanguage:
    def __init__(self):
        self.prompt_store = PromptStore()

    def construct_prompt(self,
                         task: str,
                         goals: List[GoalItem],
                         memory: Memory,
                         actions: List[Action],
                         inject_prompt_instruction: str,
                         environment: Environment,
                         agents: List[AgentContext] = None,
                         action_context: ActionContext = None,
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

            if item["type"] == "assistant":
                mapped_items.append({"role": "assistant", "content": content})
            elif item["type"] == "environment":
                mapped_items.append({"role": "system", "content": content})
            else:
                mapped_items.append({"role": "user", "content": content})

        return mapped_items

    def format_goals(self, goals: List[GoalItem]) -> List:
        sep = "\n-------------------\n"
        goal_instructions = "\n\n".join([f"{goal.name}:{sep}{goal.description}{sep}" for goal in goals])
        return [
            {"role": "system", "content": goal_instructions}
        ]

    def format_actions(self, actions: List[Action], limit=1024) -> List[Dict]:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": action.name,
                    "description": action.description[:limit],
                    "parameters": action.parameters,
                },
            } for action in actions
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


    def construct_prompt(self,
                         task: str,
                         goals: List[GoalItem],
                         memory: Memory,
                         actions: List[Action],
                         inject_prompt_instruction: str,
                         environment: Environment,
                         agents: List[AgentContext] = None,
                         action_context: ActionContext = None,
                         schema: Dict = None) -> Prompt:

        formatted_prompt = Prompt(
            task=task,
            goals=self.format_goals(goals),
            memory=self.format_memory(memory),
            actions=self.format_actions(actions),
            agents=self.format_agents(agents) if agents else None,
        )

        return formatted_prompt


    def adapt_prompt_after_parsing_error(self,
                                         prompt: Prompt,
                                         response: str,
                                         traceback: str,
                                         error: Any,
                                         retries_left: int) -> Prompt:

        return prompt
