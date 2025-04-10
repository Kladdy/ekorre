from dataclasses import dataclass
from pathlib import Path

from mashumaro.codecs.yaml import yaml_decode
from mashumaro.mixins.yaml import DataClassYAMLMixin


@dataclass
class ReactorOperatingData(DataClassYAMLMixin):
    reactor_label: str
    reactor_name: str
    reactor_type: str

    @classmethod
    def load_many_from_file(cls, file_path: str | Path):
        if isinstance(file_path, str):
            file_path = Path(file_path)
        return yaml_decode(
            file_path.read_text(),
            list[cls],
        )
