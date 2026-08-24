import pytest
from pydantic import ValidationError

from app.models import DeviceIn, DevicePatch, SimulationIn


def test_device_rejects_invalid_coordinates_and_thresholds():
    with pytest.raises(ValidationError):
        DeviceIn(name="iPhone", latitude=120, longitude=104)

    with pytest.raises(ValidationError):
        DeviceIn(name="iPhone", latitude=30, longitude=104, min_magnitude=-1)

    with pytest.raises(ValidationError):
        DeviceIn(name="iPhone", latitude=30, longitude=104, max_distance_km=0)


def test_device_patch_rejects_extreme_thresholds():
    with pytest.raises(ValidationError):
        DevicePatch(max_distance_km=30000)

    with pytest.raises(ValidationError):
        DevicePatch(min_intensity=9)


def test_simulation_rejects_unbounded_countdown():
    with pytest.raises(ValidationError):
        SimulationIn(countdown_seconds=7200)
