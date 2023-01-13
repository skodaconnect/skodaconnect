#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Client class with Skoda Connect services
Handles API calls and tokens.
"""

from __future__ import annotations
from typing import Union, Optional
from skodaconnect.api.apiclient import APIClient

class Technical(APIClient):
    """
    'Technical' API Client used for communication with Skoda Connect.
    Used mainly for requests to api.connect.skoda-auto.cz.
    'Garage' information for all cars and vehicle data for Enyaq.
    """
