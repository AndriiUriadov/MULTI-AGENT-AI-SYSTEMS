from google import genai
from google.genai import types

from config import SYSTEM_PROMPT, Settings
from tools import TOOL_DEFINITIONS, execute_tool

settings = Settings()

client = genai.Client(api_key=settings.api_key.get_secret_value())

_generate_config = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[types.Tool(function_declarations=TOOL_DEFINITIONS)],
)


class ResearchAgent:
    def __init__(self):
        # Full conversation history managed manually (no MemorySaver).
        self.history: list[types.Content] = []

    def run(self, user_input: str) -> str:
        self.history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=user_input)])
        )

        for _ in range(settings.max_iterations):
            response = client.models.generate_content(
                model=settings.model_name,
                contents=self.history,
                config=_generate_config,
            )

            candidate = response.candidates[0]
            content = candidate.content

            if content is None:
                if candidate.finish_reason.name == "MALFORMED_FUNCTION_CALL":
                    print("⚠️  Malformed function call — asking model to retry with shorter content.")
                    self.history.append(
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(
                                text=(
                                    "Your last function call was malformed (likely because the report content "
                                    "was too long). Please write a more concise report and call write_report again."
                                )
                            )],
                        )
                    )
                    continue
                print(f"⚠️  Empty content. finish_reason={candidate.finish_reason}, safety={candidate.safety_ratings}")
                return "No response generated (model returned empty content)."

            # Append model turn to history before processing
            self.history.append(content)

            # Collect function calls (parts with a non-empty function_call)
            function_calls = [
                part.function_call
                for part in content.parts
                if part.function_call and part.function_call.name
            ]

            if not function_calls:
                # No tool calls — extract text from parts and return
                text_parts = [part.text for part in content.parts if part.text]
                return " ".join(text_parts).strip() if text_parts else "No response generated."

            # Execute each tool and collect responses
            tool_response_parts = []
            for fn in function_calls:
                args = dict(fn.args) if fn.args else {}
                args_display = ", ".join(f'{k}="{v}"' for k, v in args.items())
                print(f"\n🔧 Tool call: {fn.name}({args_display})")

                try:
                    result = execute_tool(fn.name, args)
                except Exception as e:
                    result = f"Error: {e}"

                preview = result[:200] + "..." if len(result) > 200 else result
                print(f"📎 Result: {preview}")

                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=fn.name,
                        response={"result": result},
                    )
                )

            # Add all tool results as a single user turn
            self.history.append(
                types.Content(role="user", parts=tool_response_parts)
            )

        return "Max iterations reached without a final response."


agent = ResearchAgent()
