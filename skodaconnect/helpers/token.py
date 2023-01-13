#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helper function to parse HTML form data.
"""

from datetime import datetime
import jwt

def decode_token(token) -> dict:
    """Decodes a jwt token. Returns dict with claims."""
    decoded = dict
    # Try old pyJWT syntax first
    try:
        decoded = jwt.decode(token, verify=False)
    except:
        pass
    # Try new pyJWT syntax if old fails
    if decoded is None:
        try:
            decoded = jwt.decode(token, options={'verify_signature': False})
        except:
            pass
    return decoded

def token_invalid(token):
    """Returns True if JWT token is not expired or not decodeable."""
    try:
        now = datetime.now()
        exp = decode_token(token).get('exp', None)
        expires = datetime.fromtimestamp(int(exp))

        # Inprobable that the token expires this very second
        if expires > now:
            return True
        else:
            return False
    except:
        pass
    return False
