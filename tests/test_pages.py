def test_home_and_assets_can_be_loaded(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "商品工作台" in response.text
    assert "script-src 'self'" in response.headers["content-security-policy"]
    for asset, content_type in (("app.js", "javascript"), ("products.js", "javascript"), ("app.css", "text/css"), ("favicon.svg", "image/svg+xml")):
        response = client.get("/static/" + asset)
        assert response.status_code == 200
        assert content_type in response.headers["content-type"]


def test_unknown_resources_are_not_served_as_the_homepage(client):
    assert client.get("/api/not-real").status_code == 404
    assert client.get("/static/not-real.js").status_code == 404
    assert client.get("/static/../config.py").status_code == 404
