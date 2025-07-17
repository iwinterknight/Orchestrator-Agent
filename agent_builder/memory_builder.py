from typing import List, Dict


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
