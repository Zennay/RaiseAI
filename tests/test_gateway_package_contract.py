"""Fail-closed contract for the Raise gateway's dependency-free test entrypoint.

This check is intentionally separate from gateway runtime and deployment lanes.
Run: python3 -m unittest discover -s tests -p 'test_gateway_package_contract.py'
"""
import json
import pathlib
import re
import unittest

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "gateway" / "package.json"


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate package.json key: {key}")
        result[key] = value
    return result


def check_package(raw):
    config = json.loads(raw, object_pairs_hook=unique_keys)
    if not isinstance(config, dict):
        raise ValueError("package root must be an object")
    if config.get("private") is not True or config.get("type") != "module":
        raise ValueError("gateway must stay private and ESM")
    engines = config.get("engines")
    if not isinstance(engines, dict) or engines.get("node") != ">=22":
        raise ValueError("gateway requires Node 22 or newer")
    scripts = config.get("scripts")
    if not isinstance(scripts, dict):
        raise ValueError("scripts must be an object")
    if scripts.get("test") != "node --test":
        raise ValueError("tests must use Node's built-in test runner")
    if scripts.get("start") != "node src/server.mjs":
        raise ValueError("gateway start entrypoint changed")
    if any(key in scripts for key in ("pretest", "posttest", "prestart", "poststart")):
        raise ValueError("lifecycle hooks can bypass the expected command")
    for name in ("dependencies", "devDependencies", "optionalDependencies"):
        value = config.get(name, {})
        if not isinstance(value, dict):
            raise ValueError(f"{name} must be an object")
    return config


class GatewayPackageContractTests(unittest.TestCase):
    def test_repository_package(self):
        check_package(PACKAGE.read_text(encoding="utf-8"))

    def test_valid_fixture(self):
        check_package('{"private":true,"type":"module","engines":{"node":">=22"},'
                      '"scripts":{"test":"node --test","start":"node src/server.mjs"}}')

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValueError):
            check_package('{"private":true,"private":false}')

    def test_weaker_node_floor_rejected(self):
        fixture = PACKAGE.read_text(encoding="utf-8").replace('">=22"', '">=20"')
        with self.assertRaisesRegex(ValueError, "Node 22"):
            check_package(fixture)

    def test_test_runner_override_rejected(self):
        fixture = PACKAGE.read_text(encoding="utf-8").replace(
            '"node --test"', '"echo tests passed"')
        with self.assertRaisesRegex(ValueError, "test runner"):
            check_package(fixture)

    def test_lifecycle_hook_rejected(self):
        fixture = json.loads(PACKAGE.read_text(encoding="utf-8"))
        fixture["scripts"]["pretest"] = "echo bypass"
        with self.assertRaisesRegex(ValueError, "lifecycle"):
            check_package(json.dumps(fixture))


if __name__ == "__main__":
    unittest.main()
