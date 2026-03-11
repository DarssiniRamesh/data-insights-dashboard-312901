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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_swagger_ui_derives_proxy_prefix_from_request_path_when_headers_missing(async_client):
    """
    NFR-DOC-PROXY-SWAGGER-NO-FWD-HEADERS:
    In some preview/proxy setups, X-Forwarded-Prefix may be missing.
    When the externally visible docs URL is `/proxy/3001/docs`, Swagger UI must still
    fetch the schema from `/proxy/3001/openapi.json`.

    We simulate this by using the proxy-prefixed docs route directly without forwarded headers.
    """
    resp = await async_client.get("/proxy/3001/docs")
    assert resp.status_code == 200
    html = resp.text

    assert "/proxy/3001/openapi.json" in html
    assert '"/openapi.json"' not in html
