"""Small dependency-free validator for the OpenAPI schema subset used by this MVP.

Not a general JSON Schema implementation; full schema checks run with jsonschema.
"""
import re
from datetime import datetime


class Problem(Exception):
    def __init__(self, status, code, detail):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail

    def as_dict(self, instance="/"):
        return {"type": "about:blank", "title": self.code, "status": self.status,
                "detail": self.detail, "instance": instance, "code": self.code}


def validate(value, schema, spec, path="body"):
    if "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].split("/")[-1]]
    if value is None and schema.get("nullable"):
        return
    kind = schema.get("type")
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str), "integer": type(value) is int,
             "number": type(value) in (int, float), "boolean": type(value) is bool}
    if kind and not valid[kind]:
        raise Problem(422, "VALIDATION_ERROR", f"{path}: ожидается {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise Problem(422, "VALIDATION_ERROR", f"{path}: недопустимое значение")
    if kind == "object":
        props = schema.get("properties", {})
        if any(key not in value for key in schema.get("required", [])):
            raise Problem(422, "VALIDATION_ERROR", f"{path}: отсутствуют обязательные поля")
        if schema.get("additionalProperties") is False and set(value) - set(props):
            raise Problem(422, "VALIDATION_ERROR", f"{path}: неизвестные поля")
        for key in value:
            if key in props:
                validate(value[key], props[key], spec, path + "." + key)
    elif kind == "array":
        for i, item in enumerate(value):
            validate(item, schema["items"], spec, f"{path}[{i}]")
    elif kind == "string":
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")):
            raise Problem(422, "VALIDATION_ERROR", f"{path}: неверная длина")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise Problem(422, "VALIDATION_ERROR", f"{path}: неверный формат")
        if schema.get("format") in ("date-time", "date"):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if schema["format"] == "date-time" and parsed.tzinfo is None:
                    raise ValueError("timezone required")
            except ValueError as exc:
                raise Problem(422, "VALIDATION_ERROR", f"{path}: дата должна соответствовать ISO 8601") from exc
    elif kind in ("integer", "number"):
        if value < schema.get("minimum", -float("inf")) or value > schema.get("maximum", float("inf")):
            raise Problem(422, "VALIDATION_ERROR", f"{path}: значение вне диапазона")
