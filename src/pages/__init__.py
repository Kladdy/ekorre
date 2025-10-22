import os

from nicegui import ui

from . import index, lekstuga, reactor_operating_data

ui.run(port=int(os.getenv("NICEGUI_PORT")), dark=True)
