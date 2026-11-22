"""`server_urls` am Kopplungscode: Adresse für den QR-Code (QA 22.11.2026)."""

from tests.auth.conftest import API, AppFactory, client_for, setup_admin


async def test_server_urls_from_request(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        plain = (await admin.post(f"{API}/devices/pairing-codes", json={})).json()
        assert plain["server_urls"] == ["http://schiesshub.test"]
        assert plain["pair_path"]
        proxied = await admin.post(
            f"{API}/devices/pairing-codes",
            json={},
            headers={"X-Forwarded-Host": "192.168.178.20", "X-Forwarded-Proto": "https"},
        )
        assert proxied.json()["server_urls"] == ["https://192.168.178.20"]


async def test_server_urls_from_setting(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        app.state.settings = app.state.settings.model_copy(
            update={"public_base_url": "https://schiesshub.local/, https://192.168.178.20"}
        )
        await setup_admin(admin)
        created = (await admin.post(f"{API}/devices/pairing-codes", json={})).json()
        assert created["server_urls"] == ["https://schiesshub.local", "https://192.168.178.20"]
