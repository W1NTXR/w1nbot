def call_codex(messages):
    """
    messages = [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "..."},
    ]
    """

    # TEMP (replace with actual API later)
    print("\n--- CONTEXT SENT TO CODEX ---\n")
    for m in messages:
        print(f"{m['role'].upper()}: {m['content']}\n")

    response = input("Paste Codex response:\n")

    return response
