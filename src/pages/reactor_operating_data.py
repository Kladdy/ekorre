import asyncio
from datetime import datetime, timedelta, timezone

import plotly.graph_objects as go
import pytz
from nicegui import events, ui
from nicegui.events import ValueChangeEventArguments

from influxdb import get_datetime_of_extreme, read_from_influx
from models.reactor import (
    REACTOR_OPERATING_DATA_BUCKET,
    REACTOR_OPERATING_DATA_MEASUREMENT,
    Reactor,
)
from umm import fetch_umm_events

# from pages import theme


# Based on https://stackoverflow.com/a/13287083
def utc_to_local(utc_dt: datetime, tz: timezone):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=tz)


@ui.page("/reactor_operating_data", title="Reactor Operating Data | Ekorre")
async def reactor_operating_data():
    await ui.context.client.connected()
    try:
        browser_timezone_str = await ui.run_javascript("Intl.DateTimeFormat().resolvedOptions().timeZone")
        browser_timezone = pytz.timezone(browser_timezone_str)
    except Exception as e:
        print(f"Error getting browser timezone: {e}. Defaulting to UTC.")
        browser_timezone = pytz.timezone("UTC")

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

    # Fetch UMM once per page load (not on each date-range change)
    start_interval_utc = get_datetime_of_extreme(
        REACTOR_OPERATING_DATA_BUCKET,
        REACTOR_OPERATING_DATA_MEASUREMENT,
        "first",
    )
    stop_interval_utc = get_datetime_of_extreme(
        REACTOR_OPERATING_DATA_BUCKET,
        REACTOR_OPERATING_DATA_MEASUREMENT,
        "last",
    )

    umm_events = []
    umm_error: str | None = None
    try:
        umm_events, umm_url = await asyncio.to_thread(
            fetch_umm_events,
            event_stop_utc=datetime.now(timezone.utc),
            limit=10000,
        )
        print(f"UMM RSS URL: {umm_url}")
        print(f"Fetched {len(umm_events)} UMM events")
    except Exception as e:
        umm_error = str(e)
        print(f"Error fetching UMM: {umm_error}")

    @ui.refreshable
    def plot_cards(start_local: datetime | None = None, stop_local: datetime | None = None):
        if start_local is None:
            stop_local = datetime.now(tz=browser_timezone)
            start_local = stop_local - timedelta(weeks=2)
        if stop_local is None:
            stop_local = datetime.now(tz=browser_timezone)

        start_earliest_on_local_day = start_local.replace(hour=0, minute=0, second=0, microsecond=0)
        stop_latest_on_local_day = stop_local.replace(hour=23, minute=59, second=59, microsecond=999999)

        with ui.row().classes("items-center"):
            ui.icon("edit_calendar", size="md", color="primary").on("click", date_range_menu.open).classes(
                "cursor-pointer ml-2 bg-slate-800 hover:bg-slate-700 rounded-full h-12 w-12"
            )
            with ui.row().classes("text-lg font-mono"):
                if start_local.date() == stop_local.date():
                    ui.markdown(f"Showing data from **{start_local.date()}**")
                else:
                    ui.markdown(f"Showing data from **{start_local.date()}** to **{stop_local.date()}**")

        ui.separator().classes("mb-2")
        if umm_error:
            ui.label(f"UMM unavailable: {umm_error}").classes("text-xs text-red-400 font-mono")

        with ui.row():
            for reactor in Reactor.load_many_from_file("data/reactor_operating_data/reactors.yaml"):

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
                                ui.label(reactor.reactor_name).classes("text-lg font-bold font-mono")
                                ui.label(reactor.reactor_type).classes("text-xs font-mono")
                        ui.label("No data")
                    continue

                x = [utc_to_local(record.get_time(), browser_timezone) for record in records]
                y = [record.get_value() for record in records]

                # Sort the rated reactor powers by start date, reverse order
                reactor.rated_reactor_powers.sort(key=lambda x: x.start, reverse=True)

                # Normalize each y value using the rated reactor power, using each datapoints datetime as a reference
                assert (
                    len(reactor.rated_reactor_powers) > 0
                ), f"Reactor {reactor.reactor_name} has no rated reactor power"
                for idx, (x_value, y_value) in enumerate(zip(x, y, strict=True)):
                    # Get the rated reactor power for the given x value

                    rated_reactor_power = next(
                        (r.power for r in reactor.rated_reactor_powers if r.start <= x_value),
                        None,
                    )
                    if rated_reactor_power is None:
                        raise ValueError(f"Reactor {reactor.reactor_name} has no rated reactor power for {x_value}")

                    y[idx] = y_value / rated_reactor_power * 100

                # Time window to allow values to not exist over before inserting null values
                time_window_minutes = 180

                # Loop over all x values. If there is more than time_window minutes between two x values, insert that time in x and a None value in y. This breaks the plot line if data is missing. Updates are expected every 10 minutes.
                i = 0
                while i < len(x) - 1:
                    if y[i] != None and x[i] + timedelta(minutes=time_window_minutes) < x[i + 1]:
                        x.insert(i + 1, x[i] + timedelta(minutes=time_window_minutes))
                        y.insert(i + 1, None)
                    i += 1

                # As we might have None values
                max_of_non_none_y = max([y for y in y if y is not None], default=0)

                max_y_axis = max(100, max_of_non_none_y) + 10
                fig = go.Figure(
                    go.Scatter(x=x, y=y),
                    layout=go.Layout(
                        yaxis=dict(range=[0, max_y_axis]),
                        template="plotly_dark",
                    ),
                )

                # Add invisible scatter segments for UMM hover tooltips
                try:
                    range_start = (
                        browser_timezone.localize(start_earliest_on_local_day)
                        if start_earliest_on_local_day.tzinfo is None
                        else start_earliest_on_local_day
                    )
                    range_stop = (
                        browser_timezone.localize(stop_latest_on_local_day)
                        if stop_latest_on_local_day.tzinfo is None
                        else stop_latest_on_local_day
                    )

                    for ev in umm_events:
                        if ev.unit_label != reactor.reactor_label:
                            continue

                        ev_start = ev.start.astimezone(browser_timezone)
                        ev_stop = ev.stop.astimezone(browser_timezone)
                        if ev_stop < range_start or ev_start > range_stop:
                            continue

                        hover = "UMM"
                        if ev.unavailable_mw is not None:
                            hover = f"Unavailable: {int(round(ev.unavailable_mw))} MW"
                        if ev.available_mw is not None:
                            hover += f"<br>Available: {int(round(ev.available_mw))} MW"
                        hover += f"<br>{ev_start.strftime('%Y-%m-%d %H:%M')} → {ev_stop.strftime('%Y-%m-%d %H:%M')}"

                        # A transparent trace so that hovering within the window shows tooltip.
                        fig.add_trace(
                            go.Scatter(
                                x=[ev_start, ev_stop],
                                y=[0, 0],
                                mode="lines",
                                line=dict(width=30, color="rgba(255,0,0,0)"),
                                hovertemplate=hover + "<extra></extra>",
                                showlegend=False,
                            )
                        )
                except Exception:
                    pass

                # Overlay Nord Pool UMM unavailability as shaded time windows
                try:
                    range_start = (
                        browser_timezone.localize(start_earliest_on_local_day)
                        if start_earliest_on_local_day.tzinfo is None
                        else start_earliest_on_local_day
                    )
                    range_stop = (
                        browser_timezone.localize(stop_latest_on_local_day)
                        if stop_latest_on_local_day.tzinfo is None
                        else stop_latest_on_local_day
                    )

                    for ev in umm_events:
                        if ev.unit_label != reactor.reactor_label:
                            continue

                        ev_start = ev.start.astimezone(browser_timezone)
                        ev_stop = ev.stop.astimezone(browser_timezone)

                        # Only show if overlapping current interval
                        if ev_stop < range_start or ev_start > range_stop:
                            continue

                        label = "UMM"
                        if ev.unavailable_mw is not None:
                            label = f"-{int(round(ev.unavailable_mw))} MW"

                        # Yellow for partial reductions, red for full outage (available == 0)
                        fill = "yellow"
                        if ev.available_mw is not None and float(ev.available_mw) == 0.0:
                            fill = "red"

                        fig.add_vrect(
                            x0=ev_start,
                            x1=ev_stop,
                            fillcolor=fill,
                            opacity=0.18,
                            line_width=0,
                            # No always-visible text; rely on hover instead
                        )
                except Exception:
                    # Never break plotting because of UMM parsing/overlay issues
                    pass

                fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
                with ui.card():
                    with ui.row().classes("w-full"):
                        with ui.row().classes("items-baseline"):
                            ui.label(reactor.reactor_name).classes("text-lg font-bold font-mono")
                            ui.label(reactor.reactor_type).classes("text-xs font-mono")
                        ui.space()
                        ui.circular_progress(
                            round(y[-1]),
                            min=0,
                            max=100,
                            size="md",
                        ).classes("mr-2")
                    ui.plotly(fig).classes("w-96 h-40")

        # Table of UMMs in selected period
        ui.separator().classes("my-4")
        ui.label("UMM messages in selected period").classes("text-sm font-mono text-slate-200")

        try:
            range_start = (
                browser_timezone.localize(start_earliest_on_local_day)
                if start_earliest_on_local_day.tzinfo is None
                else start_earliest_on_local_day
            )
            range_stop = (
                browser_timezone.localize(stop_latest_on_local_day)
                if stop_latest_on_local_day.tzinfo is None
                else stop_latest_on_local_day
            )

            # Map unit label -> human readable name
            reactors = Reactor.load_many_from_file("data/reactor_operating_data/reactors.yaml")
            name_by_label = {r.reactor_label: r.reactor_name for r in reactors}

            rows = []
            for ev in umm_events:
                ev_start = ev.start.astimezone(browser_timezone)
                ev_stop = ev.stop.astimezone(browser_timezone)
                if ev_stop < range_start or ev_start > range_stop:
                    continue

                rows.append(
                    {
                        "block": name_by_label.get(ev.unit_label, ev.unit_label),
                        "start": ev_start.strftime("%Y-%m-%d %H:%M"),
                        "stop": ev_stop.strftime("%Y-%m-%d %H:%M"),
                        "available_mw": "" if ev.available_mw is None else int(round(ev.available_mw)),
                        "unavailable_mw": "" if ev.unavailable_mw is None else int(round(ev.unavailable_mw)),
                        "link": ev.link or "",
                        "_id": f"{ev.unit_label}-{ev.start.isoformat()}-{ev.stop.isoformat()}" ,
                    }
                )

            rows.sort(key=lambda r: (r["block"], r["start"]))

            columns = [
                {"name": "block", "label": "Block", "field": "block", "align": "left"},
                {"name": "start", "label": "Start", "field": "start", "align": "left"},
                {"name": "stop", "label": "Stop", "field": "stop", "align": "left"},
                {"name": "available_mw", "label": "Available (MW)", "field": "available_mw", "align": "right"},
                {"name": "unavailable_mw", "label": "Unavailable (MW)", "field": "unavailable_mw", "align": "right"},
            ]

            if len(rows) == 0:
                ui.label("No UMMs in this period.").classes("text-xs font-mono text-slate-400")
            else:
                table = ui.table(columns=columns, rows=rows, row_key="_id").classes("w-fit")
                table.props("flat")

                # Make each row clickable to open the UMM message in a new tab
                def _on_row_click(e: events.GenericEventArguments):
                    try:
                        link = (e.args or {}).get("row", {}).get("link")
                        if link:
                            ui.run_javascript(f"window.open('{link}', '_blank')")
                    except Exception:
                        pass

                table.on("rowClick", _on_row_click)
        except Exception as e:
            ui.label(f"UMM table error: {e}").classes("text-xs font-mono text-red-400")

    # with theme.frame():
    # Dates picker
    with ui.row():
        start_interval = start_interval_utc
        stop_interval = stop_interval_utc
        start_interval_date_str = utc_to_local(start_interval, browser_timezone).strftime("%Y/%m/%d")
        stop_interval_date_str = utc_to_local(stop_interval, browser_timezone).strftime("%Y/%m/%d")

        today = datetime.now(timezone.utc)
        if today < start_interval:
            today = start_interval
        elif today > stop_interval:
            today = stop_interval
        today_interval_str_dashes = utc_to_local(today, browser_timezone).strftime("%Y-%m-%d")
        two_weeks_ago = today - timedelta(weeks=2)
        two_weeks_ago_interval_str_dashes = utc_to_local(two_weeks_ago, browser_timezone).strftime("%Y-%m-%d")

        async def refresh_plot_cards(
            x: ValueChangeEventArguments,
            date_range: ui.date,
            date_range_menu: ui.menu,
        ):
            date_range.disable()
            date_range.update()
            await asyncio.sleep(0.01)
            plot_cards.refresh(*get_dates_from_value_change_event(x))
            date_range.enable()
            date_range_menu.close()

        with ui.menu() as date_range_menu:
            with ui.date(
                value={
                    "from": two_weeks_ago_interval_str_dashes,
                    "to": today_interval_str_dashes,
                },
                on_change=lambda x: x.value is not None and refresh_plot_cards(x, date_range, date_range_menu),
            ).props(
                f"""
                range 
                first-day-of-week=1
                :options="date => date >= '{start_interval_date_str}' && date <= '{stop_interval_date_str}'"
                """
            ) as date_range:
                with ui.row().classes("justify-end"):
                    ui.button("Close", on_click=date_range_menu.close).props("flat")

    plot_cards()
