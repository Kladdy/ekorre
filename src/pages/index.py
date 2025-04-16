from nicegui import ui


@ui.page("/")
def index():
    # Go to the site /reactor_operating_data
    ui.navigate.to("/reactor_operating_data")
