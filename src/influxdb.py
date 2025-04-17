import os
from datetime import datetime, timezone
from typing import Literal

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


def read_from_influx(
    bucket: str,
    measurement: str,
    field: str,
    start: datetime | None = None,
    stop: datetime | None = None,
    tags: dict = None,
):
    client = get_influx_client()
    query_api = client.query_api()

    tag_filters = []
    if tags:
        for key, value in tags.items():
            tag_filters.append(f'|> filter(fn: (r) => r.{key} == "{value}")')
    tag_filters = "\n".join(tag_filters)

    start_range = start.astimezone(timezone.utc).isoformat() if start else 0
    stop_range = stop.astimezone(timezone.utc).isoformat() if stop else "now()"

    flux = f"""
    from(bucket: "{get_influx_bucket(bucket)}")
      |> range(start: {start_range}, stop: {stop_range})
      {f'|> filter(fn: (r) => r._measurement == "{measurement}")' if measurement else ''}
      {f'|> filter(fn: (r) => r._field == "{field}")' if field else ''}
      {tag_filters}
    """

    result = query_api.query(flux)
    client.close()

    return [record for table in result for record in table.records]


def get_datetime_of_extreme(
    bucket: str, measurement: str, extreme: Literal["first", "last"]
) -> datetime | None:
    client = get_influx_client()
    query_api = client.query_api()

    flux = f"""
    from(bucket: "{get_influx_bucket(bucket)}")
      |> range(start: 0)
      {f'|> filter(fn: (r) => r._measurement == "{measurement}")' if measurement else ''}
      |> {extreme}()
    """

    result = query_api.query(flux)
    client.close()

    if result:
        # Extract the last timestamp from the result
        for table in result:
            for record in table.records:
                return record.get_time()
