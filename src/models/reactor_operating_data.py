from dataclasses import dataclass, field

from mashumaro.mixins.json import DataClassJSONMixin


@dataclass
class BlockProductionData:
    name: str
    production: float
    unit: str
    percent: float


@dataclass
class PowerPlantData(DataClassJSONMixin):
    timestamp: str
    powerPlant: str
    blockProductionDataList: list[BlockProductionData] = field(default_factory=list)
