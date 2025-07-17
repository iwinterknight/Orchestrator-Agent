import json
import uuid
import time
from collections import Counter
from enum import Enum
from typing import List, Dict, Callable, Any

from agent_builder.agent_factory import AgentCard, AgentContext
from agent_builder.agent_language_builder import Prompt, GoalItem, AgentLanguage
from agent_builder.environment_builder import Environment
from agent_builder.goal_builder import GoalFactory
from agent_builder.memory_builder import Memory
from agent_builder.resource_registry import ResourceRegistry, ActionContext
from agent_builder.tools_factory import ToolsFactory
from utils.llm_api import infer_llm_action_selection, infer_llm_task_routing
from utils.prompt_store import PromptStore


class AgentRole(Enum):
    STANDALONE = "standalone"
    ORCHESTRATOR = "orchestrator"
    PEER = "peer"
    HIERARCHICAL = "hierarchical"


def prompt_adaptor(tools_factory: ToolsFactory, task="routing") -> Callable[[Prompt], Dict[str, Any]]:

    def tool_selection_adaptor(prompt: Prompt) -> Dict:
        return infer_llm_action_selection(
            task=prompt.task,
            goals=prompt.goals,
            memory=prompt.memory,
            tools_factory=tools_factory
        )

    def routing_adaptor(prompt: Prompt) -> Dict:
        return infer_llm_task_routing(
            task=prompt.task,
            goals=prompt.goals,
            memory=prompt.memory,
            actions=prompt.actions,
            agents=prompt.agents
        )

    return routing_adaptor if task == "routing" else tool_selection_adaptor


class Agent:
    def __init__(self,
                 agent_card: AgentCard,
                 goals: GoalFactory,
                 agent_language: AgentLanguage,
                 resources: ResourceRegistry,
                 generate_response_routing: Callable[[Prompt], Dict[str, Any]],
                 generate_response_action_selection: Callable[[Prompt], Dict[str, Any]],
                 generate_response: Callable[[Prompt], str],
                 environment: Environment,
                 action_context: ActionContext = None):
        self.prompt_store = PromptStore()
        self.agent_id = uuid.uuid4()
        self.agent_card = agent_card
        self.goals = goals
        self.agent_language = agent_language
        self.resources = resources
        self.environment = environment
        self.generate_response_routing = generate_response_routing
        self.generate_response_action_selection = generate_response_action_selection
        self.generate_response = generate_response
        self.action_context = action_context
        self.agent_context = None
        self.__create_agent_context()


    def __create_agent_context(self):
        agent_properties = {
            "id": self.agent_id,
            "agent_card": self.agent_card,
        }
        self.agent_context = AgentContext(properties=agent_properties, memory=Memory(), invoke=self.run)


    def __update_agent_memory(self, updated_memory: Memory):
        agent_properties = {
            "id": self.agent_id,
            "agent_card": self.agent_card,
        }

        # memory reframing (contraction / expansion) logic

        self.agent_context = AgentContext(properties=agent_properties, memory=updated_memory, invoke=self.run)


    def construct_prompt_for_resource_selection(self, task: str, goals: List[GoalItem], memory: Memory,
                                                resources: ResourceRegistry, inject_prompt_instruction: str = None, schema: Dict = None) -> Prompt:
        return self.agent_language.construct_prompt(
            task=task,
            actions=resources.get_actions(),
            agents=resources.get_agents(),
            inject_prompt_instruction=inject_prompt_instruction,
            environment=self.environment,
            goals=goals,
            memory=memory,
            action_context=self.action_context,
            schema=schema
        )

    def get_action(self, invocation: dict):
        """
        Normalize the raw invocation into:
          { "tool": <tool_name>, "args": <dict> }
        then look up and return the corresponding Action.
        """
        # 1) Extract the tool name
        tool_name = invocation.get("tool")
        if tool_name is None:
            raise KeyError(f"Invocation missing 'tool' key: {invocation!r}")

        # 2) Extract or default the args dict
        args = invocation.get("args", {})
        if not isinstance(args, dict):
            raise TypeError(f"Invocation 'args' must be a dict, got {type(args)}")

        # 3) Lookup the Action
        action = self.resources.get_action(tool_name)
        if action is None:
            return {
                "tool": "Error",
                "args": {"message": f"No action chosen."}
            }

        # 4) Build the normalized invocation structure
        normalized_invocation = {
            "tool": tool_name,
            "args": args
        }

        return action, normalized_invocation

    def should_terminate(self, invocation: Dict) -> bool:
        try:
            action_def, _ = self.get_action(invocation)
            if not hasattr(action_def, 'terminal'):
                print("[WARN] action_def missing 'terminal'. Defaulting to False.")
                return False
            return action_def.terminal
        except Exception as e:
            print(f"Error during termination routing : {e}")

    def set_current_task(self, memory: Memory, task: str):
        memory.add_memory({"type": "user", "content": task})

    def update_memory(self, memory: Memory, invocation: dict = None, result: dict = None, response: str = None) -> None:
        """
        Record the agent’s chosen function (invocation) and the tool’s result
        as two separate, typed memory entries.
        """
        if invocation or response:
            memory.add_memory({
                "type": "assistant",
                "content": json.dumps(invocation) if invocation else response,
            })

        if result:
            memory.add_memory({
                "type": "environment",
                "content": json.dumps(result),
            })

        # self.__update_agent_memory(updated_memory=memory)

    def prompt_llm_for_action_selection(self, prompt: Prompt) -> Dict:
        res = self.generate_response_action_selection(prompt)
        return res

    def prompt_llm_for_routing(self, prompt: Prompt) -> Dict:
        res = self.generate_response_routing(prompt)
        return res

    def run(self, task: str, memory=None, max_iterations: int = 50) -> Memory:
        self.set_current_task(task=task, memory=memory)

        invocations_counter = Counter()

        for _ in range(max_iterations):
            routing_prompt = self.construct_prompt_for_resource_selection(task=task, goals=self.goals.get_goals(), memory=memory, resources=self.resources)

            print("Agent thinking...")
            routing_response = self.prompt_llm_for_routing(routing_prompt)
            if routing_response:
                if "reframed_task" in routing_response and routing_response["reframed_task"]:
                    reframed_task = routing_response["reframed_task"]
                else:
                    reframed_task = task
                invoked_item = routing_response["name"]
                invocations_counter[invoked_item] += 1
                if invocations_counter[invoked_item] > 2:
                    break
                if "type" in routing_response and routing_response["type"] == "agent":
                    scheduled_agent_name = routing_response["name"]
                    print(f"Agent Decision: Calling agent {scheduled_agent_name}")
                    scheduled_agent = self.resources.get_agent(agent_name=scheduled_agent_name)
                    agent_response = scheduled_agent.invoke(task=task, memory=memory)
                    scheduled_agent_memory = scheduled_agent.get_memory()
                    invocation = {
                        'agent': scheduled_agent_name,
                        'task': reframed_task
                    }
                    self.update_memory(memory=memory, invocation=invocation, result=agent_response)
                elif "type" in routing_response and routing_response["type"] == "action":
                    if "terminate" in routing_response["name"]:
                        reframed_task = routing_response["name"]

                    routing_prompt.task = reframed_task
                    selection_response = self.prompt_llm_for_action_selection(routing_prompt)
                    print(f"Agent Decision: {selection_response}")

                    if "tool" in selection_response:
                        invocation = None
                        try:
                            action, invocation = self.get_action(selection_response)
                            args = invocation.get("args", {})
                            result = self.environment.execute_action(action, args)
                            print(f"Action Result: {result}")
                        except Exception as e:
                            result = f"Failed to execute action: {e}"
                        self.update_memory(memory=memory, invocation=invocation, result=result)
                    else:
                        self.update_memory(memory=memory, response=json.dumps(selection_response))

                    if self.should_terminate(selection_response):
                        break

        final_response = json.loads(memory.get_memories()[-1]["content"])
        return final_response
