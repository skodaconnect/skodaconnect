#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Client class for communcating with VW Group API
Handles API calls and tokens.
"""

from __future__ import annotations
from typing import Union, Optional
from skodaconnect.api.apiclient import APIClient

class MBB(APIClient):
    """
    'MBB' API Client used for communication with VW Group API.
    Used mainly for requests related to vehicle data for all cars not Enyaq.
    Depends on the 'Connect' API client for tokens.
    API [server].prd.eu.dp.vwg-connect.com.
    """
