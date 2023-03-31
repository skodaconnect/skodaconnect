"""
skodaconnect - A Python 3 library for interacting with Skoda Connect.

For more details and documentation, visit the github page at:
    https://github.com/skodaconnect/skodaconnect

This models the different MBB API Endpoints into parseable objects.
"""


class SkodaDataModel:
    """Base Data Model for representing API data."""

    def __init__(self, data: dict = None):
        """Init class."""
        self._data = {}
        if type(data) is dict:
            self.data = data.copy()

    @property
    def data(self):
        """Returns raw data."""
        return self._data

    @data.setter
    def data(self, data: dict):
        """Update object data."""
        # Do nothing if provided data is not dict
        if type(data) is dict:
            self._data.update(data)


class SkodaCharger(SkodaDataModel):
    """Skoda Charger data model."""


class SkodaAirCon(SkodaDataModel):
    """Skoda Air-conditioning data model."""


class SkodaStatus(SkodaDataModel):
    """Skoda status data model."""


class SkodaPosition(SkodaDataModel):
    """Skoda Charger data model."""


class SkodaTimer(SkodaDataModel):
    """Skoda Timer data model."""
