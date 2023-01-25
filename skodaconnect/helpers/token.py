#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helper function to parse HTML form data.
"""

from datetime import datetime
import jwt
from skodaconnect.strings.globals import (
    SIG_VERIFY, EXPIRY
)

def decode_token(token) -> dict:
    """Decodes a jwt token. Returns dict with claims."""
    decoded = None
    # Try old pyJWT syntax first
    try:
        decoded = jwt.decode(token, verify=False)
    except: # pylint: disable=bare-except
        decoded = None
    # Try new pyJWT syntax if old fails
    if decoded is None:
        try:
            decoded = jwt.decode(token, options={SIG_VERIFY: False})
        except: # pylint: disable=bare-except
            decoded = {}
    return decoded

def token_valid(token):
    """Returns True if JWT token is not expired or not decodeable."""
    try:
        now = datetime.now()
        exp = decode_token(token).get(EXPIRY, None)
        expires = datetime.fromtimestamp(int(exp))

        # Inprobable that the token expires this very second
        if expires > now:
            return True
        else:
            return False
    except jwt.ExpiredSignatureError:
        return False
    except: # pylint: disable=bare-except
        pass
    return False
