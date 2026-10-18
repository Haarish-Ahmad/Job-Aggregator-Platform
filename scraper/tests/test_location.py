import pytest

from scraper.location import in_india, location_matches


@pytest.mark.parametrize("loc", [
    "Bengaluru, KA, IN / Bengaluru, Karnataka, IN",
    "India / Remote (US)",
    "SG / HK / IN / US / Remote (SG; HK; IN; US)",
    "South East Asia & India",
    "Bengaluru, India; Delhi, India; India; Mumbai, India",
    "Remote - India",
    "Remote (IN)",
    "IN / Remote (IN)",
    "Bangalore", "Hyderabad, Telangana", "Remote - Pune", "Bengaluru, Karnataka",
])
def test_in_india(loc):
    assert in_india(loc)


@pytest.mark.parametrize("loc", [
    "Indianapolis, IN, US", "Chicago, Illinois; Indiana", "Remote (US)", "Remote",
    "San Francisco, CA, US / Remote (US; CA)", "Dublin", "", "Hyderabad, Sindh, PK",
])
def test_not_in_india(loc):
    assert not in_india(loc)


def test_location_matches():
    assert location_matches("Anywhere", [])
    assert location_matches("Anywhere", [""])
    assert location_matches("Bengaluru, India", ["India"])
    assert not location_matches("Dublin", ["India"])
    assert location_matches("Dublin, Ireland", ["dublin"])
