from langchain_core.messages import HumanMessage

from utilities.print_formatters import print_formatted, print_error, print_formatted_content
from utilities.util_functions import find_tools_json
from utilities.user_input import user_input
from langgraph.prebuilt import ToolInvocation
from langgraph.graph import END
from langchain_core.messages.ai import AIMessage
from tools.tools_coder_pipeline import TOOL_NOT_EXECUTED_WORD
from utilities.graphics import loading_animation
import threading
import sys

bad_json_format_msg = TOOL_NOT_EXECUTED_WORD + """Bad json format. Json should be enclosed with '```json5', '```' tags.
Code inside of json should be provided in the way that not makes json invalid.
No '```' tags should be inside of json."""
multiple_jsons_msg = TOOL_NOT_EXECUTED_WORD + """You made multiple tool calls at once. If you want to execute 
multiple actions, choose only one for now; rest you can execute later."""
no_json_msg = TOOL_NOT_EXECUTED_WORD + """Please provide a json tool call to execute an action."""


# nodes
def call_model(state, llms):
    messages = state["messages"]
    loading_animation.is_running = True
    loading_thread = threading.Thread(target=loading_animation)
    loading_thread.daemon = True
    loading_thread.start()
    try:
        for llm in llms:
            try:
                response = llm.invoke(messages)
                break
            except Exception as e:
                print_formatted(f"\nException happened: {e} with llm: {llm.bound.__class__.__name__}. Switching to next LLM if available...", color="yellow")
        else:
            print_formatted("Can not receive response from any llm", color="red")
            sys.exit()
    finally:
        loading_animation.is_running = False
        loading_thread.join()

    # Replicate returns string instead of AI Message, we need to handle it
    if 'Replicate' in str(llm):
        response = AIMessage(content=str(response))
    response.json5_tool_calls = find_tools_json(response.content)

    # Process and print the content
    print_formatted_content(response.content)

    state["messages"].append(response)

    if response.json5_tool_calls == "No json found in response.":
        state["messages"].append(HumanMessage(content=no_json_msg))
        print_error('\nNo json provided, asked to provide one.')
        return state
    for tool_call in response.json5_tool_calls:
        if tool_call is None or "tool" not in tool_call:
            state["messages"].append(HumanMessage(content=bad_json_format_msg))
            print_error('\nBad json format provided, asked to provide again.')
            return state
    return state


def call_tool(state, tool_executor):
    last_message = state["messages"][-1]
    if not hasattr(last_message, "json5_tool_calls"):
        state["messages"].append(HumanMessage(content="No tool called"))
        return state
    json5_tool_calls = last_message.json5_tool_calls
    tool_responses = [tool_executor.invoke(ToolInvocation(**tool_call)) for tool_call in json5_tool_calls]
    tool_response = "\n\n###\n\n".join(tool_responses) if len(tool_responses) > 1 else tool_responses[0]
    response_message = HumanMessage(content=tool_response)
    state["messages"].append(response_message)
    return state


def ask_human(state):
    human_message = user_input("Type (o)k if you accept or provide commentary.")
    if human_message in ['o', 'ok']:
        state["messages"].append(HumanMessage(content="Approved by human"))
    else:
        state["messages"].append(HumanMessage(content=human_message))
    return state


# conditions
def after_ask_human_condition(state):
    last_message = state["messages"][-1]

    if last_message.content == "Approved by human":
        return END
    else:
        return "agent"
