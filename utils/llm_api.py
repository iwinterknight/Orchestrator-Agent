import json
import os
from typing import List, Dict, Any

from openai import OpenAI

from utils.prompt_store import PromptStore
from agent_builder.tools_factory import ToolsFactory


# os.environ["OPENAI_API_KEY"] = "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"
os.environ["OPENAI_API_KEY"] = "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"


client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)


prompt_store = PromptStore()


def extract_markdown_block(response: str, block_type: str = "json") -> str:
    if not '```' in response:
        return response

    code_block = response.split('```')[1].strip()

    if code_block.startswith(block_type):
        code_block = code_block[len(block_type):].strip()

    return code_block


def to_openai_functions(tools_factory: ToolsFactory):
    """
    Turn your ToolsFactory’s registry into the `functions=` list that
    chat.completions.create expects when using function_call="auto".
    """
    openai_funcs = []
    for tool_name, meta in tools_factory.tools.items():
        # pick your JSON‐Schema: prefer input_schema if present
        schema = meta.get("input_schema") or meta["parameters"]

        openai_funcs.append({
            "name": tool_name,
            "description": meta["description"][:1024],
            "parameters": schema,
        })
    return openai_funcs


def infer_llm_json(prompt: str,
                   model="gpt-4o",
                   temperature=0.2,
                   max_tokens=None,
                   num_retries=3):
    for i in range(num_retries):
        try:
            chat_completion = client.chat.completions.create(
                messages=(
                    {"role": "system",
                     "content": "You are a helpful assistant. Always respond with a valid JSON object. Remove any backticks or line breaks from the output json string."},
                    {"role": "user", "content": prompt}
                ),
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
            res_str = chat_completion.choices[0].message.content
            res_str = res_str.replace("`", "")
            res_str = res_str.replace("\n", "")
            res_str = res_str.replace("json", "")
            res = json.loads(res_str)
            if type(res) == dict:
                return res
        except Exception as e:
            if i == num_retries - 1:
                return {
                    "Error": {"message": f"LLM call failed: {e}"}
                }

def infer_llm_task_routing(
        task: str,
        goals: List[Dict],
        memory: List[Dict],
        tools: List[Dict],
        agents: List[Dict] = None,
        turn_context: Dict[str, Any] = None,
        model: str = "gpt-4.1",
        max_tokens: int = 1024,
        num_retries: int = 3
):
    prompt_values = {
        "task": task,
        "goals": goals,
        "memory": memory,
        "tools": tools,
        "agents": agents,
        "turn_context": turn_context
    }
    formatted_prompt = prompt_store.get_prompt("agent_routing_prompt", **prompt_values)
    routing_response = infer_llm_json(prompt=formatted_prompt, model=model, temperature=0.0, max_tokens=max_tokens, num_retries=num_retries)
    return routing_response


def infer_llm_tool_selection(
    task: str,
    goals: List[Dict],
    memory: List[Dict],
    tools_factory: ToolsFactory,
    turn_context: Dict[str, Any] = None,
    model: str = "gpt-4o",
    max_tokens: int = 8096,
    num_retries: int = 3
) -> Dict[str, Any]:
    """
    Ask the LLM to pick exactly one function per turn, enforce clean arguments,
    and unwrap any nested invocation that it might accidentally emit.
    """
    # 1) Build the enhanced instruction
    system_instruction = (
        f"Your task : {task}\n\n"
        "Remove any backticks or line breaks from the output. "
        "When you act, pick one of the available functions and return it via function_call.\n\n"
        "RULES:\n"
        "- Your function_call arguments must be a JSON object containing *only* that function’s parameters.\n"
        "- Do NOT wrap any other keys (like “tool” or “args”) inside the arguments object.\n"
        "- Invoke exactly one function per response.\n"
        "- Do not invent new tools or agents.\n"
        "- Given the memory and the responses from the function calls and agent invocations, you can reframe the task with additional information. If not, return the original `task` as the `reframed_task` value.\n"
        "- Except for any termination tool, do not call a function or agent multiple times unless there is additional information available in the task being given to the function or agent.\n"
        "- Use Context as a guideline for which tool to execute and how."
    )

    # 2) Annotated GOALS and MEMORY blocks
    goal_block = {
        "role": "system",
        "content": "## GOALS ##\n" + json.dumps(goals, indent=2)
    }
    memory_block = {
        "role": "system",
        "content": "## MEMORY ##\n" + json.dumps(memory, indent=2)
    }

    context_block = {
        "role": "system",
        "content": "## CONTEXT ##\n" + json.dumps(turn_context, indent=2)
    }

    # 3) Final message list
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_instruction},
        goal_block,
        memory_block,
    ]

    # 3) Prepare function specs
    functions = to_openai_functions(tools_factory)

    params = {
        "model":         model,
        "messages":      messages,
        "functions":     functions,
        "function_call": "auto",
        "max_tokens":    max_tokens,
        "temperature":   0,
        "top_p":         1.0,
        "n":             1,
        "frequency_penalty": 0,
        "presence_penalty":  0,
    }

    # 4) Retry loop
    for attempt in range(num_retries):
        try:
            resp = client.chat.completions.create(**params)
            msg  = resp.choices[0].message

            # A) Preferred: official function_call channel
            if msg.function_call:
                call = msg.function_call
                tool = call.name
                raw_args = json.loads(call.arguments or "{}")

                # Unwrap nested invocation if needed
                if (
                    isinstance(raw_args, dict)
                    and "tool" in raw_args
                    and "args" in raw_args
                    and raw_args["tool"] == tool
                ):
                    args = raw_args["args"]
                else:
                    args = raw_args

            # B) Fallback: parse raw JSON in content
            else:
                content = (msg.content or "").strip()
                try:
                    invocation = json.loads(content)
                    tool = invocation.get("tool") or invocation.get("name")
                    args = invocation.get("args") or invocation.get("arguments") or {}
                except json.JSONDecodeError as e:
                    return {
                        "tool": "Error",
                        "args": {"message": f"error message : {e}\nmessage content : {content}"}
                    }

            # 5) Strip any legacy prefix
            if isinstance(tool, str) and tool.startswith("functions."):
                tool = tool.split(".", 1)[1]

            return {"tool": tool, "args": args}

        except Exception as e:
            if attempt == num_retries - 1:
                return {
                    "tool": "error",
                    "args": {"message": f"LLM call failed: {e}"}
                }
    return {"tool": "error", "args": {"message": "Unknown inference error"}}


def infer_llm_generation(prompt: str,
                         model="gpt-4o",
                         temperature=0.2,
                         max_tokens=None,
                         num_retries=3):
    system_msg = {
        "role": "system",
        "content": (
            "You are a helpful assistant. "
            "Please respond with clean prose. No JSON or function calls in this mode."
        )
    }
    user_msg = {"role": "user", "content": prompt}

    for i in range(num_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[system_msg, user_msg],
                temperature=temperature,
                max_tokens=max_tokens
            )
            return resp.choices[0].message.content

        except Exception as e:
            if i == num_retries - 1:
                return {
                    "tool": "error",
                    "args": {"message": f"LLM call failed: {e}"}
                }

    return None
