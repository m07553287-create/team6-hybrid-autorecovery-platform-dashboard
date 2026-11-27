def test_serve_static_only_when_set(tmp_path, monkeypatch, r):
    (tmp_path / "pub").mkdir()
    (tmp_path / "pub" / "index.html").write_text("<h1>hi</h1>")
    from wiki.tests.conftest import make_client
    with make_client(r) as c:
        assert c.get("/").status_code == 404
    monkeypatch.setenv("SERVE_STATIC", str(tmp_path / "pub"))
    with make_client(r) as c:
        assert "hi" in c.get("/").text
        assert c.get("/api/health").json() == {"ok": True}
