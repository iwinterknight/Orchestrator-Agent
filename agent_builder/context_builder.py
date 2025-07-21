import uuid
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Any

from agent_builder.goal_builder import GoalItem
from agent_builder.memory_builder import Memory
from utils.llm_api import infer_llm_json
from utils.prompt_store import PromptStore


@dataclass
class TurnContext:
    id: uuid.UUID
    task: str = ""
    context: Any = field(default=None)


def normalize_context(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"Expected dict from LLM for turn context, got: {type(raw)} - {raw!r}")

    def extract_fields(d: Dict[str, Any]) -> Dict[str, Any]:
        task_val = d.get("task")
        context_val = d.get("context")
        if not isinstance(task_val, str):
            raise TypeError(f"'task' field must be a string, got {type(task_val)}: {task_val!r}")
        return {"task": task_val, "context": context_val}

    if "task" in raw and "context" in raw:
        return extract_fields(raw)

    for v in raw.values():
        if isinstance(v, dict) and "task" in v and "context" in v:
            return extract_fields(v)

    raise ValueError(f"Could not normalize turn context from LLM output: {raw!r}")



class ContextBuilder:
    def __init__(self, prompt_store: Optional[PromptStore] = None):
        turn_context_id = uuid.uuid4()
        self.turn_context = TurnContext(id=turn_context_id)
        self.prompt_store = prompt_store or PromptStore()

    def build_turn_context(self, task: str, memory: Memory) -> TurnContext:
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
            "memory": mem_items,
        }

        agent_context_builder_prompt = self.prompt_store.get_prompt("agent_context_builder_instruction",
                                                                     **prompt_values)
        res = infer_llm_json(agent_context_builder_prompt)
        parsed_turn_context = normalize_context(res)

        self.turn_context = TurnContext(
            id=self.turn_context.id,
            task=parsed_turn_context["task"],
            context=parsed_turn_context["context"]
        )

        return self.turn_context
