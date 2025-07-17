import uuid
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Any

from agent_builder.goal_builder import GoalItem
from agent_builder.memory_builder import Memory
from utils.llm_api import infer_llm_json
from utils.prompt_store import PromptStore


@dataclass
class ProgressReport:
    id: uuid.UUID
    name: str = ""
    short_term_memory: str = ""
    long_term_memory: str = ""
    progress: Dict[str, Any] = field(default_factory=dict)
    next_step: Dict[str, Any] = field(default_factory=dict)


def normalize_progress_report(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"Expected dict from LLM for progress report, got: {type(raw)} - {raw!r}")

    def extract_report_fields(d: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "progress": d.get("progress", {}),
            "next_step": d.get("next_step", {}),
            "short_term_memory": d.get("short_term_memory", ""),
            "long_term_memory": d.get("long_term_memory", "")
        }

    if any(k in raw for k in ("progress", "next_step", "short_term_memory", "long_term_memory")):
        return extract_report_fields(raw)

    for key, val in raw.items():
        if isinstance(val, dict) and any(
                k in val for k in ("progress", "next_step", "short_term_memory", "long_term_memory")):
            return extract_report_fields(val)
    raise ValueError(f"Could not normalize progress report from LLM output: {raw!r}")


class ProgressFactory:
    def __init__(self, prompt_store: Optional[PromptStore] = None):
        report_id = uuid.uuid4()
        self.progress_report = ProgressReport(id=report_id)
        self.prompt_store = prompt_store or PromptStore()

    def update_progress(self, task: str, execution_choices: Dict[str, Any], executed_choices: Dict[str, Any]):
        pass

    def track_progress(self, task: str, goals: List[GoalItem], memory: Memory) -> Dict[str, Any]:
        mem_items = [
            {"type": m["type"], "content": m["content"]}
            for m in memory.get_memories()
            if (
                    m.get("type") == "user"
                    or (m.get("type") == "assistant" and "tool" in m.get("content", ""))
                    or (m.get("type") == "environment" and "tool_executed" in m.get("content", ""))
            )
        ]

        prompt_values = {
            "task": task,
            "goals": [asdict(goal) for goal in goals],
            "memory": mem_items,
            "short term memory": self.progress_report.short_term_memory,
            "long term memory": self.progress_report.long_term_memory,
            "progress": self.progress_report.progress
        }

        agent_progress_tracker_prompt = self.prompt_store.get_prompt("agent_progress_tracker_instruction",
                                                                     **prompt_values)
        raw = infer_llm_json(agent_progress_tracker_prompt)
        updated_progress = normalize_progress_report(raw)

        self.progress_report = ProgressReport(
            id=self.progress_report.id,
            name=self.progress_report.name,
            short_term_memory=updated_progress["short_term_memory"],
            long_term_memory=updated_progress["long_term_memory"],
            progress=updated_progress["progress"],
            next_step=updated_progress["next_step"]
        )

        return updated_progress["next_step"]
