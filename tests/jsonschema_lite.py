"""A small JSON Schema checker (stdlib only) for the subset the `schemas/` files use: type, enum, const, required,
properties, items, minimum, pattern, local `$ref`, oneOf and allOf. `errors` returns the list of problems (empty =
valid); an unknown keyword is a problem, so a schema never silently checks less than it says."""
import re

KNOWN = {"$schema", "$id", "$defs", "$ref", "title", "description", "type", "enum", "const", "required",
         "properties", "items", "minimum", "pattern", "oneOf", "allOf"}


TYPES = {"string": str, "object": dict, "array": list}


def _is(value, name):
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, TYPES[name])


def _resolve(ref, root):
    node = root
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def errors(value, schema, root, path="$"):
    out = []
    for key in schema:
        if key not in KNOWN:
            out.append("%s: unknown keyword %s" % (path, key))
    if "$ref" in schema:
        out += errors(value, _resolve(schema["$ref"], root), root, path)
    for sub in schema.get("allOf", ()):
        out += errors(value, sub, root, path)
    if "oneOf" in schema:
        ok = [s for s in schema["oneOf"] if not errors(value, s, root, path)]
        if len(ok) != 1:
            out.append("%s: matches %d of the oneOf alternatives" % (path, len(ok)))
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is(value, n) for n in names):
            return out + ["%s: %r is not of type %s" % (path, value, "/".join(names))]
    if "enum" in schema and value not in schema["enum"]:
        out.append("%s: %r is not one of %r" % (path, value, schema["enum"]))
    if "const" in schema and (value != schema["const"] or type(value) is not type(schema["const"])):
        out.append("%s: %r is not %r" % (path, value, schema["const"]))
    if "minimum" in schema and _is(value, "number") and value < schema["minimum"]:
        out.append("%s: %r is below %r" % (path, value, schema["minimum"]))
    if "pattern" in schema and isinstance(value, str) and not re.search(schema["pattern"], value):
        out.append("%s: %r does not match %s" % (path, value, schema["pattern"]))
    if isinstance(value, dict):
        for name in schema.get("required", ()):
            if name not in value:
                out.append("%s: missing %s" % (path, name))
        for name, sub in schema.get("properties", {}).items():
            if name in value:
                out += errors(value[name], sub, root, path + "." + name)
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            out += errors(item, schema["items"], root, "%s[%d]" % (path, index))
    return out
