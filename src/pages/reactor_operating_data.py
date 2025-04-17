from datetime import datetime, timedelta, timezone

import plotly.graph_objects as go
from nicegui import events, ui

from influxdb import get_datetime_of_extreme, read_from_influx
from models.reactor import (
    REACTOR_OPERATING_DATA_BUCKET,
    REACTOR_OPERATING_DATA_MEASUREMENT,
    Reactor,
)

# from pages import theme


# Based on https://stackoverflow.com/a/13287083
def utc_to_local(utc_dt: datetime):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


@ui.page("/reactor_operating_data")
def reactor_operating_data():

    def get_dates_from_value_change_event(
        event: events.ValueChangeEventArguments,
    ):
        if type(event.value) == str:
            start = datetime.strptime(event.value, "%Y-%m-%d")
            stop = start
        elif type(event.value) == dict:
            start = datetime.strptime(event.value["from"], "%Y-%m-%d")
            stop = datetime.strptime(event.value["to"], "%Y-%m-%d")
        else:
            start = None
            stop = None

        return start, stop

    @ui.refreshable
    def plot_cards(
        start_local: datetime | None = None, stop_local: datetime | None = None
    ):
        if start_local is None:
            start_local = datetime.now()
        if stop_local is None:
            stop_local = datetime.now()

        start_earliest_on_local_day = start_local.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        stop_latest_on_local_day = stop_local.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        with ui.row().classes("items-center"):
            ui.icon("edit_calendar", size="md", color="primary").on(
                "click", date_range_menu.open
            ).classes(
                "cursor-pointer ml-2 bg-slate-800 hover:bg-slate-700 rounded-full h-12 w-12"
            )
            with ui.row().classes("text-lg font-mono"):
                if start_local.date() == stop_local.date():
                    ui.markdown(f"Showing data from **{start_local.date()}**")
                else:
                    ui.markdown(
                        f"Showing data from **{start_local.date()}** to **{stop_local.date()}**"
                    )

        ui.separator().classes("mb-2")

        with ui.row():
            for reactor in Reactor.load_many_from_file(
                "data/reactor_operating_data/reactors.yaml"
            ):

                # Get data from InfluxDB
                records = read_from_influx(
                    REACTOR_OPERATING_DATA_BUCKET,
                    REACTOR_OPERATING_DATA_MEASUREMENT,
                    "MW",
                    tags={"block": reactor.reactor_label},
                    start=start_earliest_on_local_day,
                    stop=stop_latest_on_local_day,
                )

                if len(records) == 0:
                    with ui.card():
                        with ui.row().classes("w-full"):
                            with ui.row().classes("items-baseline"):
                                ui.label(reactor.reactor_name).classes(
                                    "text-lg font-bold font-mono"
                                )
                                ui.label(reactor.reactor_type).classes(
                                    "text-xs font-mono"
                                )
                        ui.label("No data")
                    continue

                x = [utc_to_local(record.get_time()) for record in records]
                y = [record.get_value() for record in records]

                # Sort the rated reactor powers by start date, reverse order
                reactor.rated_reactor_powers.sort(
                    key=lambda x: datetime.fromisoformat(x.start), reverse=True
                )

                # Normalize each y value using the rated reactor power, using each datapoints datetime as a reference
                assert (
                    len(reactor.rated_reactor_powers) > 0
                ), f"Reactor {reactor.reactor_name} has no rated reactor power"
                for idx, (x_value, y_value) in enumerate(
                    zip(x, y, strict=True)
                ):
                    # Get the rated reactor power for the given x value

                    rated_reactor_power = next(
                        (
                            r.power
                            for r in reactor.rated_reactor_powers
                            if datetime.fromisoformat(r.start) <= x_value
                        ),
                        None,
                    )
                    if rated_reactor_power is None:
                        raise ValueError(
                            f"Reactor {reactor.reactor_name} has no rated reactor power for {x_value}"
                        )

                    y[idx] = y_value / rated_reactor_power * 100

                # Time window to allow values to not exist over before inserting null values
                time_window_minutes = 180

                # Loop over all x values. If there is more than time_window minutes between two x values, insert that time in x and a None value in y. This breaks the plot line if data is missing. Updates are expected every 10 minutes.
                i = 0
                while i < len(x) - 1:
                    if (
                        y[i] != None
                        and x[i] + timedelta(minutes=time_window_minutes)
                        < x[i + 1]
                    ):
                        x.insert(
                            i + 1, x[i] + timedelta(minutes=time_window_minutes)
                        )
                        y.insert(i + 1, None)
                    i += 1

                # As we might have None values
                max_of_non_none_y = max(
                    [y for y in y if y is not None], default=0
                )

                max_y_axis = max(100, max_of_non_none_y) + 10
                fig = go.Figure(
                    go.Scatter(x=x, y=y),
                    layout=go.Layout(
                        yaxis=dict(range=[0, max_y_axis]),
                        template="plotly_dark",
                    ),
                )
                fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
                with ui.card():
                    with ui.row().classes("w-full"):
                        with ui.row().classes("items-baseline"):
                            ui.label(reactor.reactor_name).classes(
                                "text-lg font-bold font-mono"
                            )
                            ui.label(reactor.reactor_type).classes(
                                "text-xs font-mono"
                            )
                        ui.space()
                        ui.circular_progress(
                            round(y[-1]),
                            min=0,
                            max=100,
                            size="md",
                        ).classes("mr-2")
                    ui.plotly(fig).classes("w-96 h-40")

    # with theme.frame():
    # Dates picker
    with ui.row():
        start_interval = get_datetime_of_extreme(
            REACTOR_OPERATING_DATA_BUCKET,
            REACTOR_OPERATING_DATA_MEASUREMENT,
            "first",
        )
        stop_interval = get_datetime_of_extreme(
            REACTOR_OPERATING_DATA_BUCKET,
            REACTOR_OPERATING_DATA_MEASUREMENT,
            "last",
        )
        start_interval_date_str = utc_to_local(start_interval).strftime(
            "%Y/%m/%d"
        )
        stop_interval_date_str = utc_to_local(stop_interval).strftime(
            "%Y/%m/%d"
        )

        today = datetime.now(timezone.utc)
        if today < start_interval:
            today = start_interval
        elif today > stop_interval:
            today = stop_interval
        today_interval_str_dashes = utc_to_local(today).strftime("%Y-%m-%d")

        with ui.menu() as date_range_menu:
            with ui.date(
                value=today_interval_str_dashes,
                on_change=lambda x: x.value is not None
                and (date_range_menu.close() or True)
                and plot_cards.refresh(*get_dates_from_value_change_event(x)),
            ).props(
                f'''range :options="date => date >= '{start_interval_date_str}' && date <= '{stop_interval_date_str}'"'''
            ):
                with ui.row().classes("justify-end"):
                    ui.button("Close", on_click=date_range_menu.close).props(
                        "flat"
                    )

    plot_cards()
