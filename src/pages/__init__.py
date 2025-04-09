import os

from nicegui import ui

from . import index

ui.run(port=int(os.getenv("NICEGUI_PORT")))
