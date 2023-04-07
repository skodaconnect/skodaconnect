#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helper functions for token handling.
"""

from datetime import datetime
from jwt import decode
from jwt.exceptions import DecodeError, ExpiredSignatureError
from vwgconnect.string.globals import SIG_VERIFY, EXPIRY


def decode_token(token) -> dict:
    """Decodes a jwt token. Returns dict with claims."""
    decoded = None
    # Try old pyJWT syntax first
    try:
        decoded = decode(token, verify=False)
    except DecodeError:
        decoded = None
    # Try new pyJWT syntax if old fails
    if decoded is None:
        try:
            decoded = decode(token, options={SIG_VERIFY: False})
        except DecodeError:
            decoded = {}
    return decoded


def token_valid(token):
    """Returns True if JWT token is not expired or not decodeable."""
    try:
        now = datetime.now()
        exp = decode_token(token).get(EXPIRY, None)
        expires = datetime.fromtimestamp(int(exp))

        # Improbable that the token expires this very second
        if expires > now:
            return True
        else:
            return False
    except ExpiredSignatureError:
        return False
    except TypeError:
        pass
    return False
