import subprocess
from memory import load_memory, save_memory
from codex_client import call_codex

SYSTEM_PROMPT = """
You are a senior software engineer discussing a task before implementation.

- Do NOT jump to code
- Focus on clarity, requirements, edge cases
- Ask questions if needed
- Keep answers structured but conversational
"""


def run_discussion(task):
    history = load_memory(task["id"])

    print(f"Starting discussion for: {task['title']}")

    while True:
        user_input = input("You: ")

        if user_input.lower().strip() = "end discussion":
            break

        history.append({"role": "user", "content": user_input})

        response = call_codex_discussion(task, history)

        print(f"W1NBOT: {response} ")
        history.append({"role":"assistant", "content": response})

        return history

def run_codex(task):
    prompt = f""
