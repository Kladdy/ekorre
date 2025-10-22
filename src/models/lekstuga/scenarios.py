from dataclasses import dataclass, field
from pathlib import Path

from mashumaro.codecs.yaml import yaml_decode
from mashumaro.mixins.json import DataClassJSONMixin


@dataclass
class LekstugaCoreLayout:
    map: list[list[int | None]]


@dataclass
class LekstugaScenario(DataClassJSONMixin):
    layout: LekstugaCoreLayout

    @classmethod
    def load_many_from_file(cls, file_path: str | Path):
        if isinstance(file_path, str):
            file_path = Path(file_path)
        return yaml_decode(
            file_path.read_text(),
            list[cls],
        )
