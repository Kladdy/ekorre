import http.client
import threading
import time
from datetime import datetime

from bs4 import BeautifulSoup
from influxdb_client import InfluxDBClient, Point
from requests import Session

from influxdb import write_to_influx
from models.reactor_operating_data import PowerPlantData

from .every import every


def get_reactor_operating_data() -> list[PowerPlantData]:
    DATA_URL = "https://group.vattenfall.com/se/var-verksamhet/vara-energislag/karnkraft/aktuell-karnkraftsproduktion"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15"
    }

    session = Session()
    page = session.get(DATA_URL, headers=headers)
    soup = BeautifulSoup(page.content, "html.parser")
    script_tags_with_json = soup.find_all(
        "script", {"type": "application/json"}
    )
    json_contents = [tag.string for tag in script_tags_with_json]

    # Parse the JSON data as a list of PowerPlantData objects
    power_plant_data_list = [
        PowerPlantData.from_json(json_content) for json_content in json_contents
    ]

    return power_plant_data_list


def reactor_operating_data_job():
    print("Fetching reactor operating data 🕒")
    try:
        power_plant_data_list = get_reactor_operating_data()

    except http.client.RemoteDisconnected as e:
        print(f"Datapoint not added 🔴")
        print(f"Error: {e}")
        return

    points: list[Point] = []

    for power_plant_data in power_plant_data_list:
        for block in power_plant_data.blockProductionDataList:

            print(
                f"Adding datapoint 🟢 {block.name}: {power_plant_data.timestamp}, {block.production:.0f} {block.unit}, {block.percent:.1f} %"
            )

            points.append(
                Point("reactor_power")
                .tag("block", block.name)
                .field(block.unit, block.production)
                .field("percent", block.percent)
                .time(
                    datetime.fromisoformat(power_plant_data.timestamp),
                    write_precision="s",
                )
            )

    # Write the points to InfluxDB
    write_to_influx(points, "reactor_operating_data")


REFRESH_INTERVAL = 10 * 60  # seconds
threading.Thread(
    target=lambda: every(REFRESH_INTERVAL, reactor_operating_data_job),
    daemon=True,
).start()
