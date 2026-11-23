"""`GET /terms` ist für jedes gekoppelte Gerät lesbar, auch ohne angemeldete Person."""

from tests.auth.conftest import (
    API,
    AppFactory,
    client_for,
    pair_new_device,
    role_id,
    setup_admin,
)


async def test_terms_for_every_paired_device(make_app: AppFactory) -> None:
    async with make_app(enforced=True) as app:
        admin = client_for(app)
        await setup_admin(admin)
        display_role = await role_id(admin, "Anzeige")
        tv = await pair_new_device(app, admin, name="Halle 2", default_role_id=display_role)
        unlogged = await pair_new_device(app, admin, name="Ohne Rolle")
        stranger = client_for(app)

        expected = (await admin.get(f"{API}/terms")).json()
        assert expected["default"]["schuetzenstand"] == "Schützenstand"
        for device in (tv, unlogged):
            response = await device.get(f"{API}/terms")
            assert response.status_code == 200, response.text
            assert response.json() == expected
        assert (await stranger.get(f"{API}/terms")).status_code == 401
