import uuid
from typing import List, Dict, Any


class Memory:
    def __init__(self):
        self.items = []

    def add_memory(self, memory: dict):
        self.items.append(memory)

    def get_memories(self, limit: int = None) -> List[Dict]:
        return self.items[:limit]

    def copy_without_system_memories(self):
        filtered_items = [m for m in self.items if m["type"] != "system"]
        memory = Memory()
        memory.items = filtered_items
        return memory


class PayloadMemory:
    def __init__(self):
        self.items = {}

    def add_payload(self, payload: Any):
        payload_id = str(uuid.uuid4())
        self.items[payload_id] = payload
        return payload_id

    def retrieve_payload(self, payload_id: str):
        result = self.items.get(payload_id.strip(), None)
        return result