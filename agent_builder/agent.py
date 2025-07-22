import json
import uuid
from collections import Counter
from enum import Enum
from typing import Dict, Callable, Any

from utils.llm_api import infer_llm_generation

from agent_builder.agent_factory import AgentCard, AgentContext
from agent_builder.agent_language_builder import Prompt, AgentLanguage
from agent_builder.context_builder import ContextBuilder, TurnContext
from agent_builder.environment_builder import Environment
from agent_builder.feedback_builder import FeedbackBuilder, AgentFeedback
from agent_builder.memory_builder import Memory, PayloadMemory
from agent_builder.plan_builder import PlanBuilder, Plan
from agent_builder.resource_registry import ResourceRegistry, ToolContext
from agent_builder.tools_factory import ToolsFactory
from utils.llm_api import infer_llm_tool_selection, infer_llm_task_routing, infer_llm_json
from utils.prompt_store import PromptStore


class AgentRole(Enum):
    STANDALONE = "standalone"
    ORCHESTRATOR = "orchestrator"
    PEER = "peer"
    HIERARCHICAL = "hierarchical"


def prompt_adaptor(tools_factory: ToolsFactory, task="routing") -> Callable[[Prompt], Dict[str, Any]]:
    def tool_selection_adaptor(prompt: Prompt) -> Dict:
        return infer_llm_tool_selection(
            task=prompt.task,
            plan=prompt.plan,
            tools_factory=tools_factory,
            turn_context=prompt.turn_context
        )

    def routing_adaptor(prompt: Prompt) -> Dict:
        return infer_llm_task_routing(
            task=prompt.task,
            plan=prompt.plan,
            tools=prompt.tools,
            agents=prompt.agents,
            turn_context=prompt.turn_context
        )

    return routing_adaptor if task == "routing" else tool_selection_adaptor


class Agent:
    def __init__(self,
                 agent_card: AgentCard,
                 agent_language: AgentLanguage,
                 resources: ResourceRegistry,
                 generate_response_routing: Callable[[Prompt], Dict[str, Any]],
                 generate_response_tool_selection: Callable[[Prompt], Dict[str, Any]],
                 generate_response: Callable[[Prompt], str],
                 environment: Environment,
                 payload_memory: PayloadMemory,
                 tool_context: ToolContext = None):
        self.prompt_store = PromptStore()
        self.agent_id = uuid.uuid4()
        self.agent_card = agent_card
        self.agent_language = agent_language
        self.resources = resources
        self.environment = environment
        self.generate_response_routing = generate_response_routing
        self.generate_response_tool_selection = generate_response_tool_selection
        self.generate_response = generate_response
        self.tool_context = tool_context
        self.payload_memory = payload_memory
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

    def construct_prompt_for_resource_selection(self, task: str, plan: Plan,
                                                resources: ResourceRegistry, inject_prompt_instruction: str = None,
                                                schema: Dict = None, turn_context: TurnContext = None, feedback: AgentFeedback = None) -> Prompt:
        return self.agent_language.construct_prompt(
            task=task,
            tools=resources.get_tools(),
            agents=resources.get_agents(),
            inject_prompt_instruction=inject_prompt_instruction,
            environment=self.environment,
            plan=plan,
            tool_context=self.tool_context,
            feedback=feedback,
            schema=schema,
            turn_context=turn_context
        )

    def get_tool(self, invocation: dict):
        tool_name = invocation.get("tool")
        if tool_name is None:
            raise KeyError(f"Invocation missing 'tool' key: {invocation!r}")

        args = invocation.get("args", {})
        if not isinstance(args, dict):
            raise TypeError(f"Invocation 'args' must be a dict, got {type(args)}")

        tool = self.resources.get_tool(tool_name)
        if tool is None:
            return {
                "tool": "Error",
                "args": {"message": f"No tool chosen."}
            }

        normalized_invocation = {
            "tool": tool_name,
            "args": args
        }

        return tool, normalized_invocation

    def generate_response_from_payload(self, task: str, response: str, content: str = ""):
        data = []
        if "response" in response:
            payload_ids = response["response"]["payload_ids"]
        else:
            payload_ids = response["payload_id"]
        for payload_id in payload_ids:
            data.append({
                "payload_id": payload_id,
                "payload": self.payload_memory.retrieve_payload(payload_id)
            })
        prompt = (
            f"Directions: {task}\nContent: {content}\nContext: {data}\n"
        )
        agent_response = infer_llm_generation(prompt)
        return agent_response

    def should_terminate(self, invocation: Dict) -> bool:
        try:
            tool_def, _ = self.get_tool(invocation)
            if not hasattr(tool_def, 'terminal'):
                print("[WARN] tool_def missing 'terminal'. Defaulting to False.")
                return False
            return tool_def.terminal
        except Exception as e:
            print(f"Error during termination routing : {e}")

    def set_current_task(self, memory: Memory, task: str):
        memory.add_memory({"type": "user", "content": task})

    def update_memory(self, memory: Memory, invocation: Any = None, result: Any = None, response: Any = None) -> None:
        """
        Record the agent’s chosen function (invocation) and the tool’s result
        as two separate, typed memory entries.
        """
        if invocation or response:
            memory.add_memory({
                "type": "agent",
                "content": json.dumps(invocation) if invocation else response,
            })

        if result:
            memory.add_memory({
                "type": "environment",
                "content": json.dumps(result),
            })

        # self.__update_agent_memory(updated_memory=memory)

    def prompt_llm_for_tool_selection(self, prompt: Prompt) -> Dict:
        res = self.generate_response_tool_selection(prompt)
        return res

    def prompt_llm_for_routing(self, prompt: Prompt) -> Dict:
        res = self.generate_response_routing(prompt)
        return res

    def construct_payload(self, memory: Memory, invocation: Any, result: Any):
        prompt_values = {
            "memory": memory,
            "invocation": invocation
        }
        agent_payload_memory_builder_prompt = self.prompt_store.get_prompt(
            "agent_payload_memory_builder_instruction",
            **prompt_values)
        res = infer_llm_json(agent_payload_memory_builder_prompt)
        payload_description = res.get("description", json.dumps(invocation))
        payload_id = self.payload_memory.add_payload(result)
        return payload_id, payload_description

    def run(self, task: str, memory=None, max_iterations: int = 50) -> Memory:
        self.set_current_task(task=task, memory=memory)

        invocations_counter = Counter()
        plan_builder = PlanBuilder()
        context_builder = ContextBuilder(payload_memory=self.payload_memory)
        feedback_builder = FeedbackBuilder()
        turn_feedback, turn_action, turn_observation = None, None, None
        plan = plan_builder.build_plan(task=task, resources=self.resources, memory=memory)

        VIOLET = "\033[38;5;93m"  # try 93, 129, or 135 for different violets
        RESET = "\033[0m"
        print(f"{VIOLET}Plan: {plan.plan}{RESET}")

        for iteration in range(max_iterations):
            if turn_feedback:
                print(f"\033[33mObservation: {turn_feedback.reasoning}\033[0m")

            turn_context = context_builder.build_turn_context(task=task, memory=memory, feedback=turn_feedback)

            if turn_context.comments:
                print(f"\033[34mThought: {turn_context.comments}\033[0m")
            routing_prompt = self.construct_prompt_for_resource_selection(task=task, plan=plan, resources=self.resources,
                                                                          turn_context=turn_context, feedback=turn_feedback)
            routing_response = self.prompt_llm_for_routing(prompt=routing_prompt)
            if routing_response:
                if "type" in routing_response and routing_response["type"] == "generate_response_and_terminate":
                    if "response" in routing_response and routing_response["response"]:
                        invocation = "generate_response_and_terminate"
                        content = routing_response["response"]
                        if "payload_ids" in routing_response["response"] and routing_response["response"]["payload_ids"]:
                            agent_response = self.generate_response_from_payload(task=task, response=routing_response["response"])
                        else:
                            agent_response = routing_response.get("response")
                        # res_len = len(json.dumps(agent_response).split())
                        # if res_len > 100:
                        #     payload_id, payload_description = self.construct_payload(memory=memory,
                        #                                                              invocation=invocation,
                        #                                                              result=agent_response)
                        #     result = {
                        #         "description": "Reference to the memory store where result is being stored and can be retrieved using the `payload_id`. Refer to `payload_description` for more information about the result.",
                        #         "payload_id": str(payload_id),
                        #         "payload_description": payload_description
                        #     }
                        #     self.update_memory(memory=memory, invocation=invocation, result=result)
                        # else:
                        #     self.update_memory(memory=memory, result=agent_response)
                        self.update_memory(memory=memory, result=agent_response)
                        return agent_response
                    else:
                        print("[WARN] routing_response missing 'response'")
                if "reframed_task" in routing_response and routing_response["reframed_task"]:
                    reframed_task = routing_response["reframed_task"]
                else:
                    reframed_task = task
                invoked_item = routing_response["name"]
                invocations_counter[invoked_item] += 1

                # if invocations_counter[invoked_item] > 2:
                #     agent_response = self.generate_response_from_payload(task=reframed_task,
                #                                                          response=json.loads(
                #                                                              memory.get_memories()[-1]["content"]))
                #     return agent_response

                if "type" in routing_response and routing_response["type"] == "agent":
                    scheduled_agent_name = routing_response["name"]
                    print(f"Agent Decision: Calling agent {scheduled_agent_name}")
                    scheduled_agent = self.resources.get_agent(agent_name=scheduled_agent_name)
                    result = scheduled_agent.invoke(task=task, memory=memory)
                    scheduled_agent_memory = scheduled_agent.get_memory()
                    invocation = {
                        'agent': scheduled_agent_name,
                        'task': reframed_task
                    }
                    res_len = len(json.dumps(result).split())
                    if res_len > 100:
                        payload_id, payload_description = self.construct_payload(memory=memory, invocation=invocation,
                                                                                 result=result["result"] if "result" in result else result)
                        result = {
                            "tool_executed": result["tool_executed"] if "tool_executed" in result else "",
                            "description": "Reference to the memory store where result is being stored and can be retrieved using the `payload_id`. Refer to `payload_description` for more information about the result.",
                            "payload_id": str(payload_id),
                            "payload_description": payload_description
                        }
                        self.update_memory(memory=memory, invocation=invocation, result=result)
                    else:
                        self.update_memory(memory=memory, invocation=invocation, result=result)
                    turn_action = invocation
                    turn_observation = result
                elif "type" in routing_response and routing_response["type"] == "tool":
                    if "terminate" in routing_response["name"]:
                        reframed_task = routing_response["name"]

                    routing_prompt.task = reframed_task
                    selection_response = self.prompt_llm_for_tool_selection(routing_prompt)

                    GREEN = "\033[92m"
                    print(f"{GREEN}Agent Decision: {selection_response}{RESET}")

                    if "tool" in selection_response:
                        invocation = None
                        try:
                            tool, invocation = self.get_tool(selection_response)
                            args = invocation.get("args", {})
                            result = self.environment.execute_tool(tool, args)
                        except Exception as e:
                            result = f"Failed to execute tool: {e}"
                        res_len = len(json.dumps(result).split())
                        if res_len > 100:
                            payload_id, payload_description = self.construct_payload(memory=memory, invocation=invocation, result=result["result"] if "result" in result else result)
                            result = {
                                "tool_executed": result["tool_executed"],
                                "description": "Reference to the memory store where result is being stored and can be retrieved using the `payload_id`. Refer to `payload_description` for more information about the result.",
                                "payload_id": str(payload_id),
                                "payload_description": payload_description
                            }
                            self.update_memory(memory=memory, invocation=invocation, result=result)
                        else:
                            self.update_memory(memory=memory, invocation=invocation, result=result)
                        turn_action = invocation
                        turn_observation = result
                    else:
                        json_selection_response = json.dumps(selection_response)
                        self.update_memory(memory=memory, response=json_selection_response)
                        turn_action = json_selection_response
                        turn_observation = None

                    # if self.should_terminate(selection_response):
                    #     agent_response = self.generate_response_from_payload(task=task,
                    #                                                          response=json.loads(memory.get_memories()[-1]["content"]), content=selection_response)
                    #     return agent_response

            turn_feedback = feedback_builder.build_agent_feedback(task=task, action=turn_action, observation=turn_observation,
                                                  resources=self.resources)
        final_response = json.loads(memory.get_memories()[-1]["content"])
        return final_response
