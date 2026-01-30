import pytest


@pytest.mark.unit
def test_openapi_schema_can_be_generated(app):
    """
    NFR-DOC-OPENAPI: OpenAPI schema should be generatable for documentation/tooling.
    """
    schema = app.openapi()
    assert isinstance(schema, dict)
    assert schema.get("openapi")
    assert schema.get("paths") is not None
    assert "/" in schema["paths"]
    assert "get" in schema["paths"]["/"]
