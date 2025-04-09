import os

from nicegui import ui

from . import index

ui.run(port=os.getenv("NICEGUI_PORT"))
