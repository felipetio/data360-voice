from chainlit.utils import mount_chainlit
from fastapi import FastAPI

app = FastAPI(title="Data360 Voice")
mount_chainlit(app=app, target="app/chat.py", path="/")
