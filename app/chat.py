import chainlit as cl


@cl.on_chat_start
async def on_chat_start():
    await cl.Message(content="Welcome to Data360 Voice! Ask me about climate data.").send()


@cl.on_message
async def on_message(message: cl.Message):
    # Stub: echo back — replaced in Story 2.2
    await cl.Message(content=f"[echo] {message.content}").send()
