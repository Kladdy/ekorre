from dataclasses import dataclass
from enum import Enum, auto

import numpy as np
import plotly.graph_objects as go
from nicegui import ui
from scipy.signal import convolve2d

from models.lekstuga.scenarios import LekstugaScenario

MAX_AGE = 4  # years
CYCLE_LENGTH = 1  # years
NUMBER_OF_STEPS = 20
BURNUP_STEP_SIZE = CYCLE_LENGTH / NUMBER_OF_STEPS


def kinf_curve(burnup: np.ndarray) -> np.ndarray:
    # Burnup is given in years. First it should go up until the first year, then down, roughly.
    kinf_map = -0.4 * np.sqrt((np.exp(-burnup / 0.4))) + 1.45 - burnup * 0.15
    return kinf_map


# import matplotlib.pyplot as plt

# plt.plot(np.linspace(0, MAX_AGE, 100), [kinf_curve(bu) for bu in np.linspace(0, MAX_AGE, 100)])
# plt.savefig("kinf_curve.png")
# plt.close()

power_kernel = np.array([[0.04, 0.08, 0.04], [0.08, 0.36, 0.08], [0.04, 0.08, 0.04]])
power_kernel = power_kernel / np.sum(power_kernel)  # Normalize


class Parameter(Enum):
    BURNUP = "Utbränning (år)"
    KINF = "Reaktivitetsvärde (kinf)"
    POWER = "Effektfördelning"
    LEAKAGE = "Läckage (%)"
    # SDM = "Avstängningsmarginal (ASM, SDM)"


@dataclass
class AgeCount:
    age: int
    count: int


@dataclass
class BurnupStepData:
    burnup: float
    burnup_map: np.ndarray
    kinf_map: np.ndarray
    power_map: np.ndarray
    leakage: float
    # sdm_map: np.ndarray


@dataclass
class AnalysisData:
    age_counts: list[AgeCount]
    total_fuel_elements: int
    burnup_step_data: list[BurnupStepData]


def calculate_analysis_data(fuel_age_map: np.ndarray) -> AnalysisData:
    unique, counts = np.unique(fuel_age_map[fuel_age_map != None], return_counts=True)
    # Add to age counts even ages with 0 count
    full_unique = np.arange(0, MAX_AGE + 1)
    full_counts = [counts[unique.tolist().index(u)] if u in unique else 0 for u in full_unique]
    age_counts = [AgeCount(age=int(u), count=int(c)) for u, c in zip(full_unique, full_counts)]

    total_fuel_elements = np.sum(counts)

    burnup_step_data = []  # Placeholder for actual burnup step data calculation

    # Initialize first burnup step data (BOC)
    burnup_map_boc = np.array(fuel_age_map, dtype=float)  # Convert so that None gets np.naa
    kinf_map_boc = kinf_curve(burnup_map_boc)
    kinf_map_filled_boc = np.where(np.isnan(kinf_map_boc), 0, kinf_map_boc)  # Fill NaNs with 0 for convolution
    power_map_boc = convolve2d(kinf_map_filled_boc, power_kernel, mode="same", boundary="fill", fillvalue=0)
    power_map_boc = np.where(
        np.isnan(burnup_map_boc), np.nan, power_map_boc
    )  # Make power_map NaN where there is no fuel
    power_map_boc = power_map_boc / np.nanmean(power_map_boc)  # Normalize power map

    # sdm_map_boc

    # Calcualte leakage by summing power in outer ring vs total power
    total_power = np.nansum(power_map_boc)
    outer_ring_power = np.nansum(
        np.concatenate(
            [
                power_map_boc[0, :],
                power_map_boc[-1, :],
                power_map_boc[1:-1, 0],
                power_map_boc[1:-1, -1],
            ]
        )
    )
    leakage_boc = (outer_ring_power / total_power) * 100 if total_power > 0 else 0.0

    burnup_step_data.append(
        BurnupStepData(
            burnup=0.0, burnup_map=burnup_map_boc, kinf_map=kinf_map_boc, power_map=power_map_boc, leakage=leakage_boc
        )
    )

    for step in np.linspace(0, CYCLE_LENGTH, NUMBER_OF_STEPS)[1:]:
        # Increase burnup based on previous power map
        burnup_map = burnup_step_data[-1].burnup_map + BURNUP_STEP_SIZE * burnup_step_data[-1].power_map
        kinf_map = kinf_curve(burnup_map)
        kinf_map_filled = np.where(np.isnan(kinf_map), 0, kinf_map)  # Fill NaNs with 0 for convolution
        power_map = convolve2d(kinf_map_filled, power_kernel, mode="same", boundary="fill", fillvalue=0)
        power_map = np.where(np.isnan(burnup_map), np.nan, power_map)  # Make power_map NaN where there is no fuel
        power_map = power_map / np.nanmean(power_map)  # Normalize power map
        # sdm_map

        # Calculate leakage by summing power in outer ring vs total power
        total_power = np.nansum(power_map)
        outer_ring_power = np.nansum(
            np.concatenate(
                [
                    power_map[0, :],
                    power_map[-1, :],
                    power_map[1:-1, 0],
                    power_map[1:-1, -1],
                ]
            )
        )
        leakage = (outer_ring_power / total_power) * 100 if total_power > 0 else 0.0

        burnup_step_data.append(
            BurnupStepData(burnup=step, burnup_map=burnup_map, kinf_map=kinf_map, power_map=power_map, leakage=leakage)
        )

    return AnalysisData(
        age_counts=age_counts, total_fuel_elements=total_fuel_elements, burnup_step_data=burnup_step_data
    )


@ui.refreshable
def fint_peak_plot(fuel_age_map: np.ndarray = None):
    analysis_data = calculate_analysis_data(fuel_age_map)

    x = [x.burnup for x in analysis_data.burnup_step_data]
    y = [np.nanmax(x.power_map) for x in analysis_data.burnup_step_data]
    avg_leakage = (np.mean([x.leakage for x in analysis_data.burnup_step_data]) - 23) / 7 * 100

    with ui.column():

        with ui.card().classes("w-158"):
            ui.label("Effektformfaktor (nära 1 är bra)").classes("text-lg font-bold")

            fig = go.Figure(
                go.Scatter(
                    x=x,
                    y=y,
                ),
                layout=go.Layout(
                    yaxis=dict(range=[1, max(np.nanmax(y), 1.3) + 0.05]),
                    template="plotly_dark",
                ),
            )
            fig.update_layout(
                margin=dict(l=0, r=0, t=0, b=0), xaxis_title="Utbränning (år)", yaxis_title="Effektformfaktor"
            )

            ui.plotly(fig).classes("w-150 h-60")

        with ui.card().classes("w-158"):
            ui.label("Läckage över utbränningscykeln (nära 0 är bra)").classes("text-lg font-bold")
            ui.circular_progress(
                min(max(round(avg_leakage, 0), 0), 100),
                min=0,
                max=100,
                size="lg",
                color="green" if avg_leakage < 50 else "red",
            )


@ui.refreshable
def analysis_data_presenter(fuel_age_map: np.ndarray = None):
    analysis_data = calculate_analysis_data(fuel_age_map)

    with ui.column():
        with ui.card().classes("w-108"):
            # Burnup steps. Show a slider and a selectable parameter to show.
            ui.label("Utbränningssteg").classes("text-lg font-bold")

            # Make these reactive variables
            step_value, set_step = ui.state(0)
            parameter_value, set_parameter = ui.state(Parameter.BURNUP.value)

            step_slider = ui.slider(
                min=0,
                max=len(analysis_data.burnup_step_data) - 1,
                value=step_value,
                step=1,
                on_change=lambda e: set_step(e.value),
            ).classes("w-64")

            parameter_select = ui.select(
                options=[(param.value) for param in Parameter if param != Parameter.LEAKAGE],
                value=parameter_value,
                on_change=lambda e: set_parameter(e.value),
            ).classes("w-48")

            @ui.refreshable
            def display_core_map():
                selected_parameter = parameter_value
                step_index = step_value

                parameter_display = ui.label("")

                match selected_parameter:
                    case Parameter.BURNUP.value:
                        parameter_values_map = analysis_data.burnup_step_data[step_index].burnup_map
                    case Parameter.KINF.value:
                        parameter_values_map = analysis_data.burnup_step_data[step_index].kinf_map
                    case Parameter.POWER.value:
                        parameter_values_map = analysis_data.burnup_step_data[step_index].power_map
                    case _:
                        raise ValueError("Okänd parameter vald")

                parameter_display.text = (
                    f"{selected_parameter} vid steg {step_index} "
                    f"(utbränning {analysis_data.burnup_step_data[step_index].burnup:.2f} år)"
                )

                with ui.card(align_items="center"):
                    for row in parameter_values_map:
                        with ui.row():
                            for val in row:
                                # Calculate color based on value range
                                if selected_parameter == Parameter.BURNUP.value:
                                    # Burnup from -2 to MAX_AGE + 2
                                    ratio = (val - (-2)) / (MAX_AGE + 2 + 1) if not np.isnan(val) else 0
                                    red = int(255 * ratio)
                                    green = int(255 * (1 - ratio))
                                    color = f"rgb({red}, {green}, 0)"
                                elif selected_parameter == Parameter.KINF.value:
                                    # kinf from 0.5 to 1.3
                                    ratio = (val - 0.5) / (1.3 - 0.5) if not np.isnan(val) else 0
                                    red = int(255 * (1 - ratio))
                                    green = int(255 * ratio)
                                    color = f"rgb({red}, {green}, 0)"
                                elif selected_parameter == Parameter.POWER.value:
                                    # power from 0.5 to 1.5 (approx)
                                    ratio = (val - 0.5) / (1.5 - 0.5) if not np.isnan(val) else 0
                                    red = int(255 * (1 - ratio))
                                    green = int(255 * ratio)
                                    color = f"rgb({red}, {green}, 0)"
                                else:
                                    color = "rgb(200, 200, 200)"
                                with (
                                    ui.card()
                                    .classes(f"w-8 h-8 p-0 grid place-items-center rounded-sm")
                                    .style(f"background-color: {color};") as column_card
                                ):
                                    if not np.isnan(val):
                                        ui.label(f"{val:.2f}").classes("text-xs rounded-sm").style(
                                            "background-color: rgba(40, 40, 40, 0.4);"
                                        )
                                    else:
                                        column_card.set_visibility(False)

            display_core_map()

        with ui.card().classes("w-108"):
            ui.label("Analys av bränsleåldrar").classes("text-lg font-bold")
            ui.table(
                rows=[
                    {
                        "Ålder (år)": ac.age,
                        "Antal laddade": ac.count,
                        "Önskat antal": f"~{analysis_data.total_fuel_elements // (MAX_AGE+1)}",
                    }
                    for ac in analysis_data.age_counts
                ],
            )


@ui.page("/lekstuga", title="Lekstuga | Ekorre")
def lekstuga():

    scenarios = LekstugaScenario.load_many_from_file("data/lekstuga/scenarios.yaml")
    scenario = scenarios[0]

    # Layout map contains "_" for empty slots. Create a NxN index map with None for empty slots.
    # The layout map is currently a list of lists of int (or "_"), where the int represents the index of the fuel assembly.
    index_map = np.full((len(scenario.layout.map), len(scenario.layout.map[0])), None)
    for row_idx, row in enumerate(scenario.layout.map):
        for col_idx, col in enumerate(row):
            if col != "_":
                index_map[row_idx, col_idx] = col

    fuel_age_map = np.zeros_like(index_map, dtype=object)
    fuel_age_map[index_map == None] = None

    labels = {}
    buttons = {}

    def update_button_visibility(row: int, col: int):
        """Hide add/remove buttons when the fuel age hits the bounds."""
        if (row, col) not in buttons:
            return
        age = fuel_age_map[row, col]
        buttons[(row, col)]["add"].set_visibility(age < MAX_AGE)
        buttons[(row, col)]["remove"].set_visibility(age > 0)

    def adjust_fuel_age(row: int, col: int, delta: int, core_size: int):
        nonlocal fuel_age_map
        if index_map[row, col] is not None:
            new_age = fuel_age_map[row, col] + delta
            if 0 <= new_age <= MAX_AGE:

                # Adjust the quarter core rotational symmetry positions
                if core_size % 2 == 0:
                    sym_positions = [
                        (row, col),
                        (col, core_size - 1 - row),
                        (core_size - 1 - row, core_size - 1 - col),
                        (core_size - 1 - col, row),
                    ]
                else:
                    sym_positions = [
                        (row, col),
                        (col, core_size - 1 - row),
                        (core_size - 1 - row, core_size - 1 - col),
                        (core_size - 1 - col, row),
                    ]

                for r, c in sym_positions:
                    fuel_age_map[r, c] = new_age
                    labels[(r, c)].text = f"{index_map[r, c]+1} | {new_age} år"
                    update_button_visibility(r, c)
                analysis_data_presenter.refresh()
                fint_peak_plot.refresh()
                ui.notify(
                    f"Bränsle {index_map[row, col]+1} (och symmetrier) justerades till {new_age} år",
                    group="fuel_age_adjust_success",
                )
            else:
                ui.notify(
                    f"Bränsleåldern måste vara mellan 0 och {MAX_AGE} år", color="red", group="fuel_age_adjust_fail"
                )

    with ui.row():

        with ui.column():
            with ui.card(align_items="center"):

                # Map
                for row_idx, row in enumerate(index_map):
                    # Classes to make sure cards dont wrap but rather overflow
                    with ui.row().classes("flex-nowrap "):
                        for col_idx, col in enumerate(row):
                            with ui.card().classes("w-18 h-18 grid grid-rows-3 p-0 pb-2 pl-1") as column_card:
                                if col is not None:
                                    with ui.row():
                                        add_btn = ui.button(
                                            icon="add",
                                            on_click=lambda r=row_idx, c=col_idx, rw=row: adjust_fuel_age(
                                                r, c, 1, len(rw)
                                            ),
                                            color="green",
                                        ).classes("w-16 h-5 min-h-0 py-0 text-xs")
                                    with ui.row():
                                        lbl = ui.label(f"{col+1} | {fuel_age_map[row_idx, col_idx]} år")
                                        labels[(row_idx, col_idx)] = lbl  # store label reference
                                    with ui.row():
                                        remove_btn = ui.button(
                                            icon="remove",
                                            on_click=lambda r=row_idx, c=col_idx, rw=row: adjust_fuel_age(
                                                r, c, -1, len(rw)
                                            ),
                                            color="red",
                                        ).classes("w-16 h-5 min-h-0 py-0 text-xs")
                                    buttons[(row_idx, col_idx)] = {"add": add_btn, "remove": remove_btn}
                                    update_button_visibility(row_idx, col_idx)
                                else:
                                    column_card.set_visibility(False)
            fint_peak_plot(fuel_age_map)

        analysis_data_presenter(fuel_age_map)
