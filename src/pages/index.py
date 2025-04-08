from nicegui import ui


@ui.page("/")
def index():
    ui.label("Hello NiceGUI!")

    with ui.row():
        ui.label("Okay....")
