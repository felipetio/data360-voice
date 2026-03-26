import logging

import anthropic
import chainlit as cl

from app.config import settings
from app.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("history", [])
    await cl.Message(content="Welcome to Data360 Voice! Ask me about World Bank climate and development data.").send()


@cl.on_message
async def on_message(message: cl.Message):
    # Retrieve or initialise conversation history
    history = cl.user_session.get("history", [])
    history.append({"role": "user", "content": message.content})

    # Trim to last N messages (keep pairs: user + assistant)
    max_msgs = settings.conversation_history_limit
    history = history[-max_msgs:]

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

        # Append assistant reply to history
        history.append({"role": "assistant", "content": msg.content})
        cl.user_session.set("history", history)

    except Exception as e:
        logger.exception("Error calling Claude API: %s", e)
        await msg.remove()
        await cl.Message(content=f"⚠️ Sorry, I couldn't reach the AI service. Please try again.\n\n_Error: {e}_").send()
