"""
Memory System for Jenny AI
Handles storage, retrieval, and management of user memories
"""

import json
import os
from typing import Dict, Any, Optional, Set

class MemorySystem:
    def __init__(self, memory_file: str = "memories.json", admin_users: Set[str] = None):
        self.memory_file = memory_file
        self.admin_users = admin_users or set()
        self.memories: Dict[str, Any] = {}
        self.load_memories()

    def set_admin_users(self, admin_users: Set[str]) -> None:
        """Set the set of admin users who can control memory"""
        self.admin_users = admin_users

    def is_admin(self, user_id: str) -> bool:
        """Check if a user is an admin"""
        return user_id in self.admin_users

    def load_memories(self) -> None:
        """Load memories from JSON file"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    self.memories = json.load(f)
            except Exception as e:
                print(f"[Warning] Failed to load memories: {e}")
                self.memories = {}
        else:
            self.memories = {}

    def save_memories(self) -> None:
        """Save memories to JSON file"""
        try:
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(self.memories, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Error] Failed to save memories: {e}")

    def remember(self, key: str, value: Any, user_id: str = None) -> bool:
        """Store a memory - admin only if admin users are set"""
        # If admin users are defined, check authorization
        if self.admin_users and user_id is not None:
            if not self.is_admin(user_id):
                print(f"[Memory] Unauthorized attempt to store memory by {user_id}")
                return False

        try:
            self.memories[key] = value
            self.save_memories()
            return True
        except Exception as e:
            print(f"[Error] Failed to store memory: {e}")
            return False

    def recall(self, key: str, user_id: str = None) -> Optional[Any]:
        """Retrieve a memory - admin only if admin users are set"""
        # If admin users are defined, check authorization
        if self.admin_users and user_id is not None:
            if not self.is_admin(user_id):
                print(f"[Memory] Unauthorized attempt to recall memory by {user_id}")
                return None

        return self.memories.get(key)

    def forget(self, key: str, user_id: str = None) -> bool:
        """Remove a memory - admin only if admin users are set"""
        # If admin users are defined, check authorization
        if self.admin_users and user_id is not None:
            if not self.is_admin(user_id):
                print(f"[Memory] Unauthorized attempt to forget memory by {user_id}")
                return False

        if key in self.memories:
            try:
                del self.memories[key]
                self.save_memories()
                return True
            except Exception as e:
                print(f"[Error] Failed to forget memory: {e}")
                return False
        return False

    def list_memories(self, user_id: str = None) -> Dict[str, Any]:
        """Get all memories - admin only if admin users are set"""
        # If admin users are defined, check authorization
        if self.admin_users and user_id is not None:
            if not self.is_admin(user_id):
                print(f"[Memory] Unauthorized attempt to list memories by {user_id}")
                return {}

        return self.memories.copy()

    def get_memory_context(self) -> str:
        """Get formatted memory context for AI prompts"""
        if not self.memories:
            return ""

        memory_items = [f"{k}: {v}" for k, v in self.memories.items()]
        return "\n\nRelevant information I remember:\n" + "\n".join(memory_items)

# Global instance for easy access
memory_system = MemorySystem()

# Convenience functions
def load_memories():
    memory_system.load_memories()

def save_memories():
    memory_system.save_memories()

def remember(key: str, value: Any, user_id: str = None) -> bool:
    return memory_system.remember(key, value, user_id)

def recall(key: str, user_id: str = None) -> Optional[Any]:
    return memory_system.recall(key, user_id)

def forget(key: str, user_id: str = None) -> bool:
    return memory_system.forget(key, user_id)

def list_memories(user_id: str = None) -> Dict[str, Any]:
    return memory_system.list_memories(user_id)

def get_memory_context() -> str:
    return memory_system.get_memory_context()