import csv
from pathlib import Path
from typing import Set, List


class Map:
    def __init__(self, workshop: bool, id: str, name: str, modes: Set[str]) -> None:
        self.workshop = workshop
        self.id = id
        self.name = name
        self.modes = modes


def LoadMaps() -> List[Map]:
    maps = []
    maps_file = Path(__file__).resolve().parent.parent / "maps.csv"
    with maps_file.open("r", encoding="utf-8") as csvf:
        for row in csv.DictReader(csvf):
            maps.append(
                Map(
                    workshop=row["workshop"] == "yes",
                    id=row["id"],
                    name=row["name"],
                    modes=row["modes"].split("|"),
                )
            )

    return maps
