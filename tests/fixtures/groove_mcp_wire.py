from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel


async def discover_client_wire_schemas(mcp: Any) -> dict[str, dict[str, object]]:
    from fastmcp import Client as FastMCPClient

    async with FastMCPClient(mcp) as client:
        listed = await client.list_tools()
    result: dict[str, dict[str, object]] = {}
    for tool in listed:
        schema = getattr(tool, "inputSchema", None)
        if schema is None:
            schema = getattr(tool, "input_schema", None)
        if not isinstance(schema, dict):
            raise AssertionError(f"client wire tool {tool.name} has no input schema")
        result[tool.name] = schema
    return result


def generated_server_schema(tool: object) -> dict[str, object]:
    parameters = getattr(tool, "parameters", None)
    if isinstance(parameters, dict):
        return parameters
    schema_method = getattr(tool, "schema", None)
    if callable(schema_method):
        schema = schema_method()
        if isinstance(schema, dict):
            return schema
    raise AssertionError("FastMCP FunctionTool exposes neither parameters nor schema()")


def normalize_wire_schema(schema: Mapping[str, object]) -> dict[str, object]:
    presentation = {"title", "$schema", "$id", "description"}

    def clean(value: object) -> object:
        if isinstance(value, dict):
            result = {
                key: clean(item)
                for key, item in value.items()
                if key not in presentation and key != "const"
            }
            if "const" in value:
                result["enum"] = [clean(value["const"])]
            return result
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    normalized = clean(dict(schema))
    assert isinstance(normalized, dict)
    return normalized


def assert_client_schema_constraints(schema: Mapping[str, object], model: type[BaseModel]) -> None:
    actual = normalize_wire_schema(schema)
    declared = normalize_wire_schema(model.model_json_schema())
    assert actual["additionalProperties"] is False
    assert set(actual["required"]) == set(declared["required"])
    for field_name, declared_field in declared["properties"].items():
        actual_field = actual["properties"][field_name]
        for key in (
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
            "enum",
            "pattern",
        ):
            declared_value = declared_field.get(key)
            actual_value = actual_field.get(key)
            if declared_value is None:
                declared_value = next(
                    (
                        branch.get(key)
                        for branch in declared_field.get("anyOf", [])
                        if isinstance(branch, dict) and key in branch
                    ),
                    None,
                )
            if actual_value is None:
                actual_value = next(
                    (
                        branch.get(key)
                        for branch in actual_field.get("anyOf", [])
                        if isinstance(branch, dict) and key in branch
                    ),
                    None,
                )
            if declared_value is not None:
                assert actual_value == declared_value, (field_name, key)


def schema_constraint(schema: Mapping[str, object], field_name: str, key: str) -> object:
    field = schema["properties"][field_name]
    if key in field:
        return field[key]
    for branch in field.get("anyOf", []):
        if isinstance(branch, dict) and key in branch:
            return branch[key]
    raise AssertionError(f"{field_name} has no {key} constraint")
