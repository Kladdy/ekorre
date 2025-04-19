from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from mashumaro import field_options
from mashumaro.codecs.yaml import yaml_decode
from mashumaro.mixins.yaml import DataClassYAMLMixin
from mashumaro.types import SerializationStrategy

REACTOR_OPERATING_DATA_BUCKET = "reactor_operating_data"
REACTOR_OPERATING_DATA_MEASUREMENT = "reactor_power"


class DateTimeSerializationStrategy(SerializationStrategy, use_annotations=True):
    def serialize(self, value: datetime) -> str:
        return value.isoformat()

    def deserialize(self, value: str) -> datetime:
        return datetime.fromisoformat(value)


@dataclass
class RatedReactorPower(DataClassYAMLMixin):
    start: datetime = field(metadata=field_options(serialization_strategy=DateTimeSerializationStrategy()))
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
