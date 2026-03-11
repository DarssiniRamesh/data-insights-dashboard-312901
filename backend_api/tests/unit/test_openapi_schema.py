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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_swagger_ui_uses_forwarded_prefix_for_openapi_url(async_client):
    """
    NFR-DOC-PROXY-SWAGGER:
    When /docs is accessed behind a proxy mount prefix (e.g. /proxy/3001),
    the returned Swagger UI HTML must reference the OpenAPI schema under the
    same prefix (e.g. /proxy/3001/openapi.json) and must NOT reference root
    /openapi.json which 404s in preview.
    """
    resp = await async_client.get("/docs", headers={"X-Forwarded-Prefix": "/proxy/3001"})
    assert resp.status_code == 200
    html = resp.text

    # Must contain the proxied openapi URL
    assert "/proxy/3001/openapi.json" in html

    # And must not fall back to requesting the root schema
    assert '"/openapi.json"' not in html
