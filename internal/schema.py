import json
from dataclasses import dataclass
from functools import lru_cache

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


@dataclass(slots=True, frozen=True)
class ToolSchemaValidationFailure(Exception):
    message: str
    instance_path: str
    schema_path: str

    def to_payload(self) -> dict[str, str]:
        return {
            "message": self.message,
            "instancePath": self.instance_path,
            "schemaPath": self.schema_path,
        }


@dataclass(slots=True, frozen=True)
class ToolSchemaDefinitionFailure(Exception):
    message: str


@lru_cache(maxsize=256)
def _build_validator(serialized_schema: str) -> Draft202012Validator:
    schema = json.loads(serialized_schema)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class ToolArgumentsSchemaValidator:
    def validate(self, schema: dict, arguments: dict) -> None:
        serialized_schema = json.dumps(schema, sort_keys=True, separators=(",", ":"))
        try:
            validator = _build_validator(serialized_schema)
        except SchemaError as exc:
            raise ToolSchemaDefinitionFailure(message=exc.message) from exc

        try:
            validator.validate(arguments)
        except ValidationError as exc:
            raise ToolSchemaValidationFailure(
                message=exc.message,
                instance_path=self._format_path(exc.absolute_path),
                schema_path=self._format_path(exc.absolute_schema_path),
            ) from exc

    def _format_path(self, path_parts) -> str:
        return "/" + "/".join(str(part) for part in path_parts)
