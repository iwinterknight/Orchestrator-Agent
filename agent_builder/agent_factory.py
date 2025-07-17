from dataclasses import dataclass, field
from typing import List, Dict, Optional

from agent_builder.memory_builder import Memory


@dataclass(frozen=True)
class AgentSkill:
    id: str
    name: str
    description: str
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentCard:
    name: str
    persona: str
    description: str
    skills: List[AgentSkill] = field(default_factory=list)
    version: Optional[str] = None
    url: Optional[str] = None


class AgentContext:
    def __init__(self, properties: Dict, memory: Memory, invoke: callable):
        if "id" not in properties:
            raise Exception("Agent id not specified.")
        self.agent_id = properties["id"]

        if "agent_card" not in properties:
            raise Exception("Agent card not found.")
        self.agent_card = properties["agent_card"]

        self.interaction_summary = []
        self.properties = properties

        self.memory = memory
        self.invoke = invoke

    def get(self, key: str, default=None):
        return self.properties.get(key, default)

    # TO-DO : selective memory sharing
    def get_memory(self):
        return self.memory

    def invoke(self):
        return self.invoke