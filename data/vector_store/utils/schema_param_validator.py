"""
Simple parameter name validator for command schemas.

Checks that:
- All required parameters from schema are present in params.
- All keys in params are present in schema['properties'].
- No extra keys in params.
- Does NOT check types/values (only names and presence).

Usage:
    schema = MyCommand.get_schema()
    params = { ... }
    validate_params_against_schema(params, schema)

Raises ValueError with a clear message if validation fails.
"""

def validate_params_against_schema(params: dict, schema: dict):
    """
    Validates that params match the schema by parameter names only.
    - All required parameters from schema are present in params.
    - All keys in params are present in schema['properties'].
    - No extra keys in params.
    - Does NOT check types/values.
    Raises ValueError with a clear message if validation fails.
    """
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    allowed = set(properties.keys())
    given = set(params.keys())

    missing = required - given
    extra = given - allowed

    if missing:
        raise ValueError(f"Missing required parameter(s): {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"Unknown parameter(s): {', '.join(sorted(extra))}")
    # All good
    return True
