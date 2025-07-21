import uuid

from agent_builder.tools_factory import ToolsFactory
from agent_builder.agent_factory import AgentCard, AgentContext
from typing import List, Callable, Dict, Any, Optional


class Tool:
    def __init__(self, name: str, function: Callable, description: str, parameters: Dict, input_schema: Dict = None, output_schema: Dict = None, terminal: bool = False):
        self.name = name
        self.function = function
        self.description = description
        self.parameters = parameters
        self.terminal = terminal
        self.input_schema = input_schema
        self.output_schema = output_schema

    def execute(self, **args) -> Any:
        return self.function(**args)


class ToolContext:
    def __init__(self, properties: Dict=None):
        self.context_id = str(uuid.uuid4())
        self.properties = properties or {}

    def get(self, key: str, default=None):
        return self.properties.get(key, default)

    def get_memory(self):
        return self.properties.get("memory", None)


class ResourceRegistry:
    def __init__(self):
        self.tools = {}
        self.agents = {}

    def register_tool(self, tool: Tool):
        self.tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[Tool]:
        return self.tools.get(name, None)

    def get_tools(self) -> List[Tool]:
        return list(self.tools.values())

    def register_agent(self, agent_name: str, agent_context: AgentContext):
        self.agents[agent_name] = agent_context

    def get_agent(self, agent_name: str) -> Optional[AgentContext]:
        return self.agents.get(agent_name, None)

    def get_agents(self) -> List[AgentContext]:
        return list(self.agents.values()) if self.agents else None


class ExecutableResourceRegistry(ResourceRegistry):
    def __init__(self, tools_factory: ToolsFactory, agents: List[AgentContext] = None, tags: List[str] = None, tool_names: List[str] = None):
        super().__init__()
        self.tools = tools_factory.tools
        self.terminate_tool = None

        for tool_name, tool_desc in self.tools.items():
            if tool_name == "terminate":
                self.terminate_tool = tool_desc

            if tool_names and tool_name not in tool_names:
                continue

            tool_tags = tool_desc.get("tags", [])
            if tags and not any(tag in tool_tags for tag in tags):
                continue

            self.register_tool(Tool(
                name=tool_name,
                function=tool_desc["function"],
                description=tool_desc["description"],
                parameters=tool_desc.get("parameters", {}),
                input_schema=tool_desc.get("input_schema"),
                output_schema=tool_desc.get("output_schema"),
                terminal=tool_desc.get("terminal", False)
            ))

        if agents:
            for agent_context in agents:
                self.register_agent(agent_name=agent_context.agent_card.name, agent_context=agent_context)


    def register_terminate_tool(self):
        if self.terminate_tool:
            self.register_tool(Tool(
                name="terminate",
                function=self.terminate_tool["function"],
                description=self.terminate_tool["description"],
                parameters=self.terminate_tool.get("parameters", {}),
                terminal=self.terminate_tool.get("terminal", False)
            ))
        else:
            raise Exception("Terminate tool not found in tool registry")
