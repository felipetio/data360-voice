from chainlit.utils import mount_chainlit
from fastapi import FastAPI

import app.data  # noqa: F401  # registers Chainlit data layer

app = FastAPI(title="Data360 Voice")
mount_chainlit(app=app, target="app/chat.py", path="/")
