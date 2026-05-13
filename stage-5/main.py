from agent import agent


def main():
    print("Research Agent with RAG (type 'exit' to quit)")
    print("-" * 40)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        for chunk in agent.stream({"messages": [("user", user_input)]}):
            # Tool calls — show which tools are being invoked
            if "agent" in chunk:
                for msg in chunk["agent"].get("messages", []):
                    for tc in getattr(msg, "tool_calls", []):
                        args_preview = str(tc["args"])[:80]
                        print(f"\n🔧 Tool call: {tc['name']}({args_preview})")

            # Tool results
            if "tools" in chunk:
                for msg in chunk["tools"].get("messages", []):
                    if hasattr(msg, "content") and msg.content:
                        preview = str(msg.content)[:120].replace("\n", " ")
                        print(f"📎 Result: {preview}...")

            # Final agent response
            if "agent" in chunk:
                for msg in chunk["agent"].get("messages", []):
                    if hasattr(msg, "content") and msg.content:
                        print(f"\nAgent: {msg.content}")


if __name__ == "__main__":
    main()
