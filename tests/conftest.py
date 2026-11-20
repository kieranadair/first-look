import pytest

from firstlook.challenges import automatic_challenges
from firstlook.discovery import discover
from firstlook.examples import load_example


@pytest.fixture
def dataset():
    return load_example("reversal")


@pytest.fixture
def investigation(dataset):
    inv = discover(dataset)
    automatic_challenges(dataset, inv)
    return inv
