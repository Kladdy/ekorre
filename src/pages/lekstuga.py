from dataclasses import dataclass

from nicegui import ui

from models.lekstuga.scenarios import LekstugaScenario


@dataclass
class FuelGeneration:
    age: int
    label: str


fuel_generaions: list[FuelGeneration] = [
    FuelGeneration(0, "Färsk"),
    *[FuelGeneration(n, f"{n}-åring") for n in range(1, 6)],
]


@ui.page("/lekstuga", title="Lekstuga | Ekorre")
def lekstuga():

    scenarios = LekstugaScenario.load_many_from_file("data/lekstuga/scenarios.yaml")
    scenario = scenarios[0]

    with ui.card(align_items="center"):

        # Map
        for row in scenario.layout.map:
            with ui.row():
                for column in row:
                    with ui.card().classes("w-24 h-24") as column_card:
                        if column is not None:
                            ui.select({n.age: n.label for n in fuel_generaions})
                            ui.label(f"{column}")
                        else:

                            column_card.set_visibility(False)
