import http.client
import os
import threading
import time
from datetime import datetime

from bs4 import BeautifulSoup
from influxdb_client import Point
from requests import Session

from influxdb import get_datetime_of_extreme, write_to_influx
from models.reactor import (
    REACTOR_OPERATING_DATA_BUCKET,
    REACTOR_OPERATING_DATA_MEASUREMENT,
)
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
    script_tags_with_json = soup.find_all("script", {"type": "application/json"})
    json_contents = [tag.string for tag in script_tags_with_json]

    # Parse the JSON data as a list of PowerPlantData objects
    power_plant_data_list = [PowerPlantData.from_json(json_content) for json_content in json_contents]

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

    datetime_of_last = get_datetime_of_extreme(
        REACTOR_OPERATING_DATA_BUCKET,
        REACTOR_OPERATING_DATA_MEASUREMENT,
        "last",
    )
    if datetime_of_last is None:
        datetime_of_last = datetime.fromtimestamp(0)
    print(f"Latest data in InfluxDB: {datetime_of_last} (from '{REACTOR_OPERATING_DATA_BUCKET}')")

    for power_plant_data in power_plant_data_list:
        for block in power_plant_data.blockProductionDataList:
            point_datetime = datetime.fromisoformat(power_plant_data.timestamp)

            point = (
                Point("reactor_power")
                .tag("block", block.name)
                .field(block.unit, block.production)
                .field("percent", block.percent)
                .time(
                    point_datetime,
                    write_precision="s",
                )
            )

            # Check if the point already exists in InfluxDB
            if point_datetime.replace(microsecond=0) > datetime_of_last.replace(microsecond=0):
                points.append(point)
                print(
                    f"Adding datapoint 🟢 {block.name}: {power_plant_data.timestamp}, {block.production:.0f} {block.unit}, {block.percent:.1f} %"
                )
            else:
                print(
                    f"Datapoint not newer than latest data 🔵 {block.name}: {power_plant_data.timestamp}, {block.production:.0f} {block.unit}, {block.percent:.1f} %"
                )

    # Write the points to InfluxDB
    if len(points) == 0:
        print("No new data to write to InfluxDB 🔵")
        return
    print(f"Writing {len(points)} new datapoints to InfluxDB 🟢")
    write_to_influx(points, REACTOR_OPERATING_DATA_BUCKET)


# Check if the NO_FETCH_REACTOR_DATA=1 environment variable is set.
if os.getenv("NO_FETCH_REACTOR_DATA") == "1":
    print("Skipping reactor operating data fetch 🔴")
else:
    REFRESH_INTERVAL = 3 * 60
    threading.Thread(
        target=lambda: every(REFRESH_INTERVAL, reactor_operating_data_job),
        daemon=True,
    ).start()
