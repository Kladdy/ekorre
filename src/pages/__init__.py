import os

from nicegui import ui

from . import index

ui.run(port=str(os.getenv("NICEGUI_PORT")))
