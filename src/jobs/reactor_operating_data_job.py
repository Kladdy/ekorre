import http.client
import threading
import time

from bs4 import BeautifulSoup
from requests import Session

from models.reactor_operating_data import PowerPlantData

from .every import every

# from models import datetime_converter
# from models.reactor_operating_data import ReactorOperatingData
# from time_series_data.reactor_operating_data import (
#     add_reactor_operating_data_point,
#     point_is_present,
# )


def get_reactor_operating_data():
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


# def


def reactor_operating_data_job():
    print("Fetching reactor operating data 🕒")
    power_plant_data_list = get_reactor_operating_data()
    for power_plant_data in power_plant_data_list:
        for block in power_plant_data.blockProductionDataList:

            try:
                print(
                    f"{block.name}: {power_plant_data.timestamp}, {block.production:.0f} {block.unit}, {block.percent:.1f} %"
                )

                # TODO
                # if not point_is_present(reactor, reactor_data):
                #     add_reactor_operating_data_point(reactor, reactor_data)
                #     print(f"Added datapoint 🟢")
                # else:
                #     print(f"Datapoint present 🔵")

            except http.client.RemoteDisconnected as e:
                print(f"Datapoint not added 🔴")
                print(f"Error: {e}")


REFRESH_INTERVAL = 10 * 60  # seconds
threading.Thread(target=lambda: every(REFRESH_INTERVAL, reactor_operating_data_job)).start()
