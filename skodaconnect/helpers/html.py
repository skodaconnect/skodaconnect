#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helper functions to parse HTML form data.
"""

from __future__ import annotations
from base64 import b64encode
import re
import json
import hashlib
import secrets
import string
from bs4 import BeautifulSoup


def get_nonce() -> str:
    """Returns a 'nonce' string."""
    chars = string.ascii_letters + string.digits
    text = "".join(secrets.choice(chars) for i in range(10))
    sha256 = hashlib.sha256()
    sha256.update(text.encode())
    return b64encode(sha256.digest()).decode("utf-8")[:-1]


def get_state() -> str:
    """Returns a 'state' string, same as a nonce."""
    return get_nonce()


def parse_form(html: str) -> dict:
    """Method to parse HTML form and return input values and action."""
    # Extract form and extract attributes
    try:
        form_data = dict()
        html_soup = BeautifulSoup(html, "html.parser")
        if html_soup is None:
            raise Exception("Unable to parse HTML data.")

        # There are two possibilities, either hard coded HTML form or JS form
        html_form = html_soup.find("form")
        js_scripts = html_soup.find_all("script", {"src": False})

        # If form is built by HTML, extract input fields
        if html_form is not None:
            form_data["type"] = "html"
            for field in html_form.find_all("input", type="hidden"):
                if form_data.get(field["name"], False):
                    form_data[field["name"]] = form_data[field["name"]] + " " + field["value"]
                else:
                    form_data[field["name"]] = field["value"]
            action = html_soup.find("form").get("action", None)
            if action is not None:
                form_data["action"] = action
        elif js_scripts is not None:
            # Our form is dynamically built by javascript, extract JSON data
            form_data["type"] = "js"
            # The interesting data is in "templateModel" in an inline script
            pattern = re.compile("templateModel: (.*?),\n")
            for script in js_scripts:
                # Check all inline scripts and search for our pattern
                if pattern.search(script.string):
                    data = pattern.search(script.string)
                    form_data = json.loads(data.groups()[0])
        else:
            raise Exception("Failed to extract login form data")
        return form_data
    except Exception as exc:
        return {"error": str(exc)}
