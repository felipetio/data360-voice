import json
import logging
from contextlib import AsyncExitStack
from typing import Any

import anthropic
import chainlit as cl
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.config import settings
from app.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# MCP session key used in cl.user_session
_MCP_SESSION_KEY = "mcp_session"
_MCP_TOOLS_KEY = "mcp_tools"
_MCP_EXIT_STACK_KEY = "mcp_exit_stack"


def _make_client():
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


client = _make_client()


# ---------------------------------------------------------------------------
# MCP lifecycle callbacks
# ---------------------------------------------------------------------------


@cl.on_mcp_connect
async def on_mcp_connect(connection, session: ClientSession) -> None:
    """Called when a Chainlit MCP connection is established (from the UI)."""
    try:
        result = await session.list_tools()
        tools = _mcp_tools_to_anthropic(result.tools)
        cl.user_session.set(_MCP_SESSION_KEY, session)
        cl.user_session.set(_MCP_TOOLS_KEY, tools)
        logger.info("MCP connected: %d tools available", len(tools))
    except Exception:
        logger.exception("Failed to list MCP tools on connect")
        cl.user_session.set(_MCP_SESSION_KEY, session)
        cl.user_session.set(_MCP_TOOLS_KEY, [])


@cl.on_mcp_disconnect
async def on_mcp_disconnect(name: str, session: ClientSession) -> None:
    """Called when an MCP connection is torn down."""
    cl.user_session.set(_MCP_SESSION_KEY, None)
    cl.user_session.set(_MCP_TOOLS_KEY, [])
    logger.info("MCP disconnected: %s", name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mcp_tools_to_anthropic(mcp_tools: list) -> list[dict[str, Any]]:
    """Convert MCP Tool objects to the Anthropic tools parameter format."""
    result = []
    for tool in mcp_tools:
        result.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            }
        )
    return result


def _extract_tool_result_text(call_result) -> str:
    """Extract text from an MCP CallToolResult, handling errors."""
    if call_result.isError:
        # Surface the error to Claude so it can narrate gracefully
        parts = []
        for block in call_result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "Error: " + (" ".join(parts) if parts else "Unknown MCP tool error")

    parts = []
    for block in call_result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    text = "\n".join(parts) if parts else ""

    max_chars = settings.tool_result_max_chars
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... truncated, results too large ...]"
    return text


# ---------------------------------------------------------------------------
# Chainlit handlers
# ---------------------------------------------------------------------------


@cl.on_chat_resume
async def on_chat_resume(thread: dict) -> None:
    """Restore conversation history when a user resumes a previous thread."""
    history: list[dict[str, Any]] = []
    steps = thread.get("steps", [])
    for step in steps:
        step_type = step.get("type", "")
        output = step.get("output", "")
        if not output:
            continue
        if step_type == "user_message":
            history.append({"role": "user", "content": output})
        elif step_type == "assistant_message":
            history.append({"role": "assistant", "content": output})
    # Trim to the configured history limit
    max_msgs = settings.conversation_history_limit
    history = history[-max_msgs:]
    cl.user_session.set("history", history)

    # Re-connect the MCP session (same pattern as on_chat_start)
    cl.user_session.set(_MCP_SESSION_KEY, None)
    cl.user_session.set(_MCP_TOOLS_KEY, [])
    cl.user_session.set(_MCP_EXIT_STACK_KEY, None)

    stack = AsyncExitStack()
    try:
        read, write, _ = await stack.enter_async_context(streamablehttp_client(url=settings.mcp_server_url))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        result = await session.list_tools()
        tools = _mcp_tools_to_anthropic(result.tools)

        cl.user_session.set(_MCP_SESSION_KEY, session)
        cl.user_session.set(_MCP_TOOLS_KEY, tools)
        cl.user_session.set(_MCP_EXIT_STACK_KEY, stack)
        logger.info("MCP reconnected on resume: %d tools available", len(tools))
    except Exception:
        logger.warning("MCP reconnect failed on resume, continuing without tools", exc_info=True)
        await stack.aclose()


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("history", [])
    cl.user_session.set(_MCP_SESSION_KEY, None)
    cl.user_session.set(_MCP_TOOLS_KEY, [])
    cl.user_session.set(_MCP_EXIT_STACK_KEY, None)

    # Auto-connect to MCP server
    stack = AsyncExitStack()
    try:
        read, write, _ = await stack.enter_async_context(streamablehttp_client(url=settings.mcp_server_url))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        result = await session.list_tools()
        tools = _mcp_tools_to_anthropic(result.tools)

        cl.user_session.set(_MCP_SESSION_KEY, session)
        cl.user_session.set(_MCP_TOOLS_KEY, tools)
        cl.user_session.set(_MCP_EXIT_STACK_KEY, stack)
        logger.info("MCP auto-connected: %d tools available", len(tools))
    except Exception:
        logger.warning("MCP auto-connect failed, continuing without tools", exc_info=True)
        await stack.aclose()

    await cl.Message(content="Welcome to Data360 Voice! Ask me about World Bank climate and development data.").send()


@cl.on_chat_end
async def on_chat_end():
    stack: AsyncExitStack | None = cl.user_session.get(_MCP_EXIT_STACK_KEY)
    if stack:
        try:
            await stack.aclose()
        except Exception:
            logger.warning("Error closing MCP connection", exc_info=True)


@cl.on_message
async def on_message(message: cl.Message):
    # Retrieve conversation history and append new user turn
    history = cl.user_session.get("history", [])
    history.append({"role": "user", "content": message.content})

    # Trim to the last N messages in the conversation history
    max_msgs = settings.conversation_history_limit
    history = history[-max_msgs:]

    # Persist trimmed history immediately
    cl.user_session.set("history", history)

    # Get MCP tools and session (may be None/empty if MCP not connected)
    mcp_session: ClientSession | None = cl.user_session.get(_MCP_SESSION_KEY)
    tools: list[dict[str, Any]] = cl.user_session.get(_MCP_TOOLS_KEY) or []

    msg = cl.Message(content="")
    await msg.send()

    try:
        # Mutable copy of history for the agentic loop
        loop_history = list(history)

        await _agentic_loop(loop_history, tools, mcp_session, msg)

        await msg.update()

        # Append assistant reply to persistent history (use msg.content for consistency
        # with what was actually streamed to the user)
        history.append({"role": "assistant", "content": msg.content})
        cl.user_session.set("history", history)

    except Exception as e:
        logger.exception("Error during message handling: %s", e)
        await msg.remove()
        await cl.Message(content="⚠️ Sorry, I couldn't reach the AI service. Please try again.").send()


async def _agentic_loop(
    history: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    mcp_session: ClientSession | None,
    msg: cl.Message,
) -> str:
    """
    Drive the Claude agentic loop:
      1. Call Claude (with tools if available).
      2. If Claude returns tool_use blocks, execute them via MCP and append results.
      3. Repeat until Claude returns a final text response (stop_reason != "tool_use").
      4. Stream the final text response token by token.

    Returns the final assembled text.
    """
    call_kwargs: dict[str, Any] = {
        "model": settings.claude_model,
        "max_tokens": settings.claude_max_tokens,
        "system": SYSTEM_PROMPT,
    }
    if tools:
        call_kwargs["tools"] = tools

    max_rounds = settings.max_tool_rounds
    tool_round = 0

    while True:
        tool_round += 1
        if tool_round > max_rounds:
            logger.error("Exceeded maximum tool rounds (%d), aborting agentic loop.", max_rounds)
            return (
                "I'm sorry, but I had to stop because I exceeded the maximum number "
                "of tool calls. Please try rephrasing or simplifying your request."
            )
        call_kwargs["messages"] = history

        async with client.messages.stream(**call_kwargs) as stream:
            tokens: list[str] = []
            async for text_token in stream.text_stream:
                tokens.append(text_token)
                await msg.stream_token(text_token)

            final_message = await stream.get_final_message()

        stop_reason = final_message.stop_reason

        if stop_reason != "tool_use":
            return "".join(tokens)

        # Reset the UI message for the next iteration so intermediate
        # "thinking" text from tool-use rounds doesn't leak to the user.
        msg.content = ""

        # --- Handle tool_use blocks ---
        # Append assistant response (may contain both text and tool_use blocks)
        assistant_content = final_message.content  # list of content blocks
        history.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in assistant_content]})

        # Process each tool_use block
        tool_results = []
        for block in assistant_content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            tool_use_id = block.id

            # Show intermediate step in UI
            async with cl.Step(name=f"🔧 {tool_name}", type="tool") as step:
                step.input = json.dumps(tool_input, indent=2)

                if mcp_session is not None:
                    try:
                        call_result = await mcp_session.call_tool(tool_name, arguments=tool_input)
                        tool_output = _extract_tool_result_text(call_result)
                    except Exception as exc:
                        logger.error("MCP tool call failed for %s: %s", tool_name, exc)
                        tool_output = f"Error calling tool '{tool_name}': {exc}"
                else:
                    tool_output = (
                        f"Error: MCP server is not connected. Cannot call tool '{tool_name}'. "
                        "The Data360 API is currently unavailable."
                    )

                step.output = tool_output[:500] + "…" if len(tool_output) > 500 else tool_output

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": tool_output,
                }
            )

        # Append tool results to history and loop
        history.append({"role": "user", "content": tool_results})
