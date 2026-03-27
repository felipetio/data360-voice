import logging

import chainlit as cl

from app.config import settings
from app.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _make_client():
    import anthropic

    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


client = _make_client()


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("history", [])
    await cl.Message(content="Welcome to Data360 Voice! Ask me about World Bank climate and development data.").send()


@cl.on_message
async def on_message(message: cl.Message):
    # Retrieve conversation history and append new user turn
    history = cl.user_session.get("history", [])
    history.append({"role": "user", "content": message.content})

    # Trim to the last N messages in the conversation history
    max_msgs = settings.conversation_history_limit
    history = history[-max_msgs:]

    # Persist trimmed history immediately so it's bounded even if the API call fails
    cl.user_session.set("history", history)

    msg = cl.Message(content="")
    await msg.send()

    try:
        async with client.messages.stream(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=history,
        ) as stream:
            async for text in stream.text_stream:
                await msg.stream_token(text)

        await msg.update()

        # Append assistant reply to history and persist
        history.append({"role": "assistant", "content": msg.content})
        cl.user_session.set("history", history)

    except Exception as e:
        logger.exception("Error calling Claude API: %s", e)
        await msg.remove()
        await cl.Message(
            content="⚠️ Sorry, I couldn't reach the AI service. Please try again."
        ).send()
