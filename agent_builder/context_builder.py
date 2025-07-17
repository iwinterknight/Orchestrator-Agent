import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from agent_builder.resource_registry import ResourceRegistry
from utils.llm_api import infer_llm_json
from utils.prompt_store import PromptStore


@dataclass
class TurnContext:
    id: uuid.UUID
    task: str = ""
    execution_choices: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""


def normalize_turn_context(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"Expected dict from LLM for turn context, got: {type(raw)} - {raw!r}")

    def extract_fields(d: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "execution_choices": d.get("execution_choices", {}),
            "reasoning": d.get("reasoning", ""),
            "name": d.get("name", "")
        }

    if any(k in raw for k in ("execution_choices", "reasoning", "name")):
        return extract_fields(raw)

    for _, v in raw.items():
        if isinstance(v, dict) and any(k in v for k in ("execution_choices", "reasoning", "name")):
            return extract_fields(v)

    raise ValueError(f"Could not normalize turn context from LLM output: {raw!r}")


# noinspection PyTypeChecker
class ContextBuilder:
    def __init__(self, prompt_store: Optional[PromptStore] = None):
        self.turn_context_id = uuid.uuid4()
        self.prompt_store = prompt_store or PromptStore()
        self.turn_context: TurnContext = None

    def build_turn_context(self, task: str, resources: ResourceRegistry = None, next_step: Dict[str, Any] = None) -> \
    Dict[str, Any]:
        prompt_values = {
            "task": task,
            "next step": next_step,
            "actions": resources.get_actions(),
            "agents": resources.get_agents()
        }

        agent_context_builder_prompt = self.prompt_store.get_prompt("agent_context_builder_instruction",
                                                                    **prompt_values)
        raw = infer_llm_json(agent_context_builder_prompt)
        updated_turn_context = normalize_turn_context(raw)

        self.turn_context = TurnContext(
            id=self.turn_context_id,
            task=task,
            execution_choices=updated_turn_context.get("execution_choices", {}),
            reasoning=updated_turn_context.get("reasoning", "")
        )

        return self.turn_context.execution_choices
