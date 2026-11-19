import pytest
from pydantic import ValidationError

from services.monitoring.schemas import MonitorCreate


def test_monitor_schema_normalizes_name_and_sets_defaults():
    monitor = MonitorCreate(name="  API Health  ", url="https://example.org/health")
    assert monitor.name == "API Health"
    assert str(monitor.url) == "https://example.org/health"
    assert monitor.interval_seconds == 60
    assert monitor.failure_threshold == 3


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("url", "ftp://example.org"),
        ("url", "https://name:password@example.org/health"),
        ("interval_seconds", 4),
        ("interval_seconds", 3601),
        ("interval_seconds", True),
        ("failure_threshold", 0),
        ("failure_threshold", 11),
        ("failure_threshold", False),
    ],
)
def test_monitor_schema_rejects_invalid_fields(field, value):
    data = {"name": "API", "url": "https://example.org/health"}
    data[field] = value
    with pytest.raises(ValidationError):
        MonitorCreate(**data)


def test_monitor_schema_rejects_client_supplied_owner_id():
    with pytest.raises(ValidationError):
        MonitorCreate(
            name="API",
            url="https://example.org/health",
            owner_id="2d3b4409-0101-4b43-b71f-cf2c2209fadc",
        )
