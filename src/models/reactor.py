from dataclasses import dataclass

from mashumaro.mixins.yaml import DataClassYAMLMixin


@dataclass
class ReactorOperatingData(DataClassYAMLMixin):
    reactor_label: str
    reactor_name: str
    reactor_type: str
