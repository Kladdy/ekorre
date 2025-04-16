from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from mashumaro.codecs.yaml import yaml_decode
from mashumaro.mixins.yaml import DataClassYAMLMixin

REACTOR_OPERATING_DATA_BUCKET = "reactor_operating_data"
REACTOR_OPERATING_DATA_MEASUREMENT = "reactor_power"


@dataclass
class RatedReactorPower(DataClassYAMLMixin):
    start: str
    power: float


@dataclass
class Reactor(DataClassYAMLMixin):
    reactor_label: str
    reactor_name: str
    reactor_type: str
    rated_reactor_powers: list[RatedReactorPower] = field(default_factory=list)

    @classmethod
    def load_many_from_file(cls, file_path: str | Path):
        if isinstance(file_path, str):
            file_path = Path(file_path)
        return yaml_decode(
            file_path.read_text(),
            list[cls],
        )
