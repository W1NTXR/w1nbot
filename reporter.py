def generate_final_report(task, history):
    prompt = f"""
    You are summarizing a completed engineering discussion.

    Task:
    {task['title']}

    Conversation:
    {history}

    ## Output:
    1. Final agreed approach
    2. Key decisions made
    3. Implementation plan
    4. Risks / considerations
    5. Next steps
    """

    return call_codex(prompt)
