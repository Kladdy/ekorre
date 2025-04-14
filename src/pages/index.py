from nicegui import ui

from influxdb import read_from_influx
from models.reactor import (
    REACTOR_OPERATING_DATA_BUCKET,
    REACTOR_OPERATING_DATA_MEASUREMENT,
    ReactorOperatingData,
)


@ui.page("/")
def index():
    # Go to the site /reactor_operating_data
    ui.navigate.to("/reactor_operating_data")
