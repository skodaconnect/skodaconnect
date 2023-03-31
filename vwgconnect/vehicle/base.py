#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abstract base class for Vehicle data model.
Models methods and properties common for all vehicle classes.
"""

from __future__ import annotations
from types import SimpleNamespace
import json
from abc import ABC, abstractmethod
from vwgconnect.platform import APIClient
from .const import CHARGER, AIRCON, ACCESS, FUEL, MEASUREMENTS, POSITION, STATE, LIGHTS


class Car(ABC):
    """Base class for Car data model."""

    def __init__(self: Car, conn: APIClient, vin: str) -> None:
        """
        Init Car data model class

        Arguments:
            conn: class, the platform API client to use for interactions with the car
        """
        self.platform = conn
        self.vin = vin
        self.data = {}

    # Common methods for all car data models, implement per platform
    @abstractmethod
    async def update(self):
        """Update car status information."""
