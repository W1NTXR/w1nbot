import json
import os

MEMORY_DIR = "memory"

os.makedirs(MEMORY_DIR, exist_ok = True)

def get_memory_path(task_id):
    return os.path.join(MEMORY_DIR,f"{task_id}.json")

def load_memory(task_id):
    path = get_memory_path(task_id)

    if not os.path.exists(path):
        return []

    with open(path,"r") as f:
        return json.load(f)

def save_memory(task_id, history):
    path = get_memory_path(task_id)

    with open(path, "w") as f:
        json.dump(history, f, indent=2)
