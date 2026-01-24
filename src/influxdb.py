import os
from datetime import datetime, timezone
from pathlib import Path
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


_client = None
_verified_buckets = set()


def get_influx_client():
    global _client

    if _client is not None:
        return _client

    url = os.getenv("INFLUX_URL")
    token = get_secret("INFLUX_TOKEN")
    org = str(os.getenv("INFLUX_ORG"))

    print(f"Connecting to InfluxDB at '{url}' with org '{org}'")

    _client = InfluxDBClient(url=url, token=token, org=org)

    # Ensure organization exists
    try:
        orgs_api = _client.organizations_api()
        orgs = orgs_api.find_organizations()
        org_exists = any(o.name == org for o in orgs)

        if not org_exists:
            orgs_api.create_organization(name=org)
    except Exception as e:
        print(f"Warning: Could not verify/create organization '{org}': {e}")
        raise e

    return _client


def get_influx_bucket(bucket_name: str):
    influx_env = os.getenv("INFLUX_ENV")
    return f"{bucket_name}-{influx_env}"


def ensure_bucket_exists(client: InfluxDBClient, bucket_name: str):
    """Ensure the bucket exists, creating it if necessary."""
    full_bucket_name = get_influx_bucket(bucket_name)
    if full_bucket_name in _verified_buckets:
        return
    try:
        buckets_api = client.buckets_api()
        buckets = buckets_api.find_bucket_by_name(full_bucket_name)
        if buckets is None:
            buckets_api.create_bucket(bucket_name=full_bucket_name)
        _verified_buckets.add(full_bucket_name)
    except Exception as e:
        print(f"Warning: Could not verify/create bucket {full_bucket_name}: {e}")
        raise e


def write_to_influx(data: Point | list[Point], bucket: str):
    print(f"InfluxDB: Writing data to bucket '{get_influx_bucket(bucket)}'")
    client = get_influx_client()
    ensure_bucket_exists(client, bucket)
    with client.write_api(write_options=SYNCHRONOUS) as write_api:
        write_api.write(bucket=get_influx_bucket(bucket), record=data)


def read_from_influx(
    bucket: str,
    measurement: str,
    field: str,
    start: datetime | None = None,
    stop: datetime | None = None,
    tags: dict = None,
):
    print(
        f"InfluxDB: Reading data from bucket '{get_influx_bucket(bucket)}', measurement '{measurement}', field '{field}'"
    )
    client = get_influx_client()
    ensure_bucket_exists(client, bucket)
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

    return [record for table in result for record in table.records]


def write_all_influx_data_to_csv(bucket: str, measurement: str, field: str, filename: str | Path):
    print(
        f"InfluxDB: Exporting data from bucket '{get_influx_bucket(bucket)}', measurement '{measurement}', field '{field}' to '{filename}'"
    )
    client = get_influx_client()
    ensure_bucket_exists(client, bucket)
    query_api = client.query_api()

    flux = f"""
    from(bucket: "{get_influx_bucket(bucket)}")
      |> range(start: 0)
      {f'|> filter(fn: (r) => r._measurement == "{measurement}")' if measurement else ''}
      {f'|> filter(fn: (r) => r._field == "{field}")' if field else ''}
    """

    result = query_api.query_csv(flux)

    if not isinstance(filename, Path):
        filename = Path(filename)

    results_as_values = result.to_values()

    filename.parent.mkdir(parents=True, exist_ok=True)
    filename.write_text("\n".join([",".join(x) for x in results_as_values]))

    return len(results_as_values)  # Return the count


def get_datetime_of_extreme(bucket: str, measurement: str, extreme: Literal["first", "last"]) -> datetime | None:
    print(
        f"InfluxDB: Getting {extreme} datetime from bucket '{get_influx_bucket(bucket)}', measurement '{measurement}'"
    )
    client = get_influx_client()
    ensure_bucket_exists(client, bucket)
    query_api = client.query_api()

    flux = f"""
    from(bucket: "{get_influx_bucket(bucket)}")
      |> range(start: 0)
      {f'|> filter(fn: (r) => r._measurement == "{measurement}")' if measurement else ''}
      |> {extreme}()
    """

    result = query_api.query(flux)

    if result:
        # Extract the last timestamp from the result
        for table in result:
            for record in table.records:
                return record.get_time()
