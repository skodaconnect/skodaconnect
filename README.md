![Version](https://img.shields.io/github/v/release/skodaconnect/skodaconnect?include_prereleases)
![PyPi](https://img.shields.io/pypi/v/skodaconnect?label=latest%20pypi)
![Downloads PyPi](https://img.shields.io/pypi/dm/skodaconnect)

# Skoda Connect
**UNOFFICIAL** library for communicating with Skoda Connect.
Based on the Android MySkoda application and it features.

The library is reverse engineered by intercepting HTTP requests from
MySkoda app, there is no official API. Use at your own risk.
If the Skoda API changes, this library may stop working without warning.

## Information

Retrieve statistics about your Skoda from the Skoda Connect online service.
* Support for Skoda Connect services
* Support for SmartLink
* All (native) Skoda cars supported though features differ.
* If your car doesn't work with the official MySkoda app this won't work either.

Please contribute by supplying improvements/bugfixes and raise issues.

## Breaking changes

- **From version 2.0** and onwards the code has been rewritten from scratch.
The class structure and methods have changed and features might be missing.
Focus has been on rewriting the code to be PEP compliant and easier to maintain.

## Thanks to

- [RobinostLund](https://github.com/robinostlund/volkswagencarnet)
    For initial project for Volkswagen Carnet which this was based on initially.
- [Farfar](https://github.com/Farfar)
    For PHEV/BEV development.
- [tanelvakker](https://github.com/tanelvakker)
    For help with fixing correct SPIN handling.
- [wieshka](https://github.com/wieshka)
    For help with Skoda Enyaq iV development.
- WebSpider and GAEvakYD on the Discord for their help with login form handling.

## Other related repositories

- [HomeAssistant Component](https://github.com/lendy007/homeassistant-skodaconnect)
    Home Assistant custom component

## Installation

```sh
[venv-python3] user@localhost:~
$ pip install skodaconnect
```

### Example

For an extensive example, please use the code found in example/example.py.
Documentation can be found at: https://...

## Further help or contributions
For questions, further help or contributions you can join the Discord server at https://discord.gg/826X9jEtCh
