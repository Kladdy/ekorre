import os

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS


def get_secret(key: str) -> str:
    # Check for _FILE suffix first
    file_env = f"{key}_FILE"
    if file_env in os.environ:
        with open(os.environ[file_env], "r") as f:
            return f.read().strip()
    # Fall back to environment variable
    return os.environ.get(key)


def get_influx_client():
    client = InfluxDBClient(
        url=os.getenv("INFLUX_URL"),
        token=get_secret("INFLUX_TOKEN"),
        org=os.getenv("INFLUX_ORG"),
    )
    return client


def get_influx_bucket(bucket_name: str):
    return f"{bucket_name}-{os.getenv("INFLUX_ENV")}"


def write_to_influx(data: Point | list[Point], bucket: str):
    client = get_influx_client()
    with client.write_api(write_options=SYNCHRONOUS) as write_api:
        write_api.write(bucket=get_influx_bucket(bucket), record=data)
    client.close()
