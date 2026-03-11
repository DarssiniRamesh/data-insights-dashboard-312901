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
async def test_swagger_ui_uses_relative_openapi_url_under_forwarded_prefix(async_client):
    """
    NFR-DOC-PROXY-SWAGGER (recommended approach):
    Swagger UI should use a *relative* OpenAPI URL (`./openapi.json`) so it resolves
    correctly when the docs are served under a preview proxy prefix like `/proxy/3001/docs`.

    This ensures the rendered HTML does not embed `url: '/openapi.json'`.
    """
    resp = await async_client.get("/docs", headers={"X-Forwarded-Prefix": "/proxy/3001"})
    assert resp.status_code == 200
    html = resp.text

    # Relative OpenAPI URL should be present
    assert "url: './openapi.json'" in html

    # Must not reference root schema path
    assert "url: '/openapi.json'" not in html


@pytest.mark.unit
@pytest.mark.asyncio
async def test_swagger_ui_uses_relative_openapi_url_when_accessed_via_proxy_prefixed_path(async_client):
    """
    NFR-DOC-PROXY-SWAGGER-NO-FWD-HEADERS:
    Even if forwarded headers are missing, when the externally visible docs URL is
    `/proxy/3001/docs`, Swagger UI should still use the same relative OpenAPI URL
    (`./openapi.json`) which will resolve to `/proxy/3001/openapi.json` in the browser.
    """
    resp = await async_client.get("/proxy/3001/docs")
    assert resp.status_code == 200
    html = resp.text

    assert "url: './openapi.json'" in html
    assert "url: '/openapi.json'" not in html


@pytest.mark.unit
@pytest.mark.asyncio
async def test_swagger_ui_uses_relative_openapi_url_when_proxy_strips_prefix(async_client):
    """
    NFR-DOC-PROXY-SWAGGER-X-FORWARDED-URI:
    If a proxy strips the mount prefix before forwarding to the app (so the app sees `/docs`)
    but provides the original external path in X-Forwarded-Uri, Swagger should still be
    configured to use a relative schema URL (`./openapi.json`) so the browser resolves it
    relative to the docs page URL.
    """
    resp = await async_client.get("/docs", headers={"X-Forwarded-Uri": "/proxy/3001/docs"})
    assert resp.status_code == 200
    html = resp.text

    assert "url: './openapi.json'" in html
    assert "url: '/openapi.json'" not in html
