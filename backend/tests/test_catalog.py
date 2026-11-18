from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app import create_app
from backend.config import Settings, get_settings

TEST_DB_URL = get_settings().database_url


@pytest.fixture()
def app(_clean_database: None) -> object:
    settings = Settings()  # type: ignore[call-arg]
    return create_app(settings)


@pytest.fixture()
async def admin_client(app: object) -> AsyncClient:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "DefaultLoc")
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        await c.post("/auth/login", json={"username": "admin1", "password": "adminpass1"})
        yield c  # type: ignore[misc]


# --- A4: duplicate names case-insensitive with friendly error ---


@pytest.mark.anyio()
async def test_A4_location_duplicate_friendly(admin_client: AsyncClient) -> None:
    resp1 = await admin_client.post("/admin/locations", json={"name": "Cairo"})
    assert resp1.status_code == 201
    resp2 = await admin_client.post("/admin/locations", json={"name": "cairo"})
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"]["error"]["message"]


@pytest.mark.anyio()
async def test_A4_specialty_duplicate_friendly(admin_client: AsyncClient) -> None:
    resp1 = await admin_client.post("/admin/specialties", json={"name": "Cardiology"})
    assert resp1.status_code == 201
    resp2 = await admin_client.post("/admin/specialties", json={"name": "cardiology"})
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"]["error"]["message"]


# --- Delete shows cascade counts ---


@pytest.mark.anyio()
async def test_A5_delete_location_shows_cascade_count(admin_client: AsyncClient) -> None:
    loc_resp = await admin_client.post("/admin/locations", json={"name": "TestCity"})
    loc_id = loc_resp.json()["id"]
    await admin_client.post("/admin/clinics", json={"name": "Clinic A", "location_id": loc_id})
    await admin_client.post("/admin/clinics", json={"name": "Clinic B", "location_id": loc_id})

    del_resp = await admin_client.delete(f"/admin/locations/{loc_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["cascade"]["clinics"] == 2


@pytest.mark.anyio()
async def test_A5_delete_clinic_shows_cascade_count(admin_client: AsyncClient) -> None:
    loc_resp = await admin_client.post("/admin/locations", json={"name": "TestCity"})
    loc_id = loc_resp.json()["id"]
    clinic_resp = await admin_client.post("/admin/clinics", json={"name": "Clinic A", "location_id": loc_id})
    clinic_id = clinic_resp.json()["id"]
    spec_resp = await admin_client.post("/admin/specialties", json={"name": "Derm"})
    spec_id = spec_resp.json()["id"]
    await admin_client.put(f"/admin/clinics/{clinic_id}/specialties", json=[{"specialty_id": spec_id}])

    cs_list = (await admin_client.put(f"/admin/clinics/{clinic_id}/specialties", json=[{"specialty_id": spec_id}])).json()
    cs_id = cs_list[0]["id"]
    await admin_client.post("/admin/doctors", json={"name": "Dr X", "clinic_specialty_id": cs_id})

    del_resp = await admin_client.delete(f"/admin/clinics/{clinic_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["cascade"]["specialties"] == 1
    assert del_resp.json()["cascade"]["doctors"] == 1


# --- A5: delete blocked by visit history ---


@pytest.mark.anyio()
async def test_A5_delete_doctor_blocked_by_visit(
    admin_client: AsyncClient, db_engine: Engine
) -> None:
    loc_resp = await admin_client.post("/admin/locations", json={"name": "TestCity"})
    loc_id = loc_resp.json()["id"]
    clinic_resp = await admin_client.post("/admin/clinics", json={"name": "Clinic A", "location_id": loc_id})
    clinic_id = clinic_resp.json()["id"]
    spec_resp = await admin_client.post("/admin/specialties", json={"name": "Derm"})
    spec_id = spec_resp.json()["id"]
    await admin_client.put(f"/admin/clinics/{clinic_id}/specialties", json=[{"specialty_id": spec_id}])

    cs_list = (await admin_client.put(f"/admin/clinics/{clinic_id}/specialties", json=[{"specialty_id": spec_id}])).json()
    cs_id = cs_list[0]["id"]
    doc_resp = await admin_client.post("/admin/doctors", json={"name": "Dr X", "clinic_specialty_id": cs_id})
    doctor_id = doc_resp.json()["id"]

    with db_engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO slot (doctor_id, start_at) VALUES (:d, '2026-12-01 10:00:00+00')"
        ), {"d": doctor_id})
        acct_id = conn.execute(text("SELECT id FROM account LIMIT 1")).scalar_one()
        profile_id = conn.execute(
            text("SELECT id FROM profile WHERE account_id = :a"), {"a": acct_id}
        ).scalar_one()
        slot_id = conn.execute(text("SELECT id FROM slot LIMIT 1")).scalar_one()
        conn.execute(text(
            "INSERT INTO visit (profile_id, slot_id) VALUES (:p, :s)"
        ), {"p": profile_id, "s": slot_id})
        conn.commit()

    del_resp = await admin_client.delete(f"/admin/doctors/{doctor_id}")
    assert del_resp.status_code == 409
    assert del_resp.json()["detail"]["error"]["code"] == "has_history"


@pytest.mark.anyio()
async def test_A5_delete_clinic_blocked_by_visit(
    admin_client: AsyncClient, db_engine: Engine
) -> None:
    loc_resp = await admin_client.post("/admin/locations", json={"name": "TestCity"})
    loc_id = loc_resp.json()["id"]
    clinic_resp = await admin_client.post("/admin/clinics", json={"name": "Clinic A", "location_id": loc_id})
    clinic_id = clinic_resp.json()["id"]
    spec_resp = await admin_client.post("/admin/specialties", json={"name": "Derm"})
    spec_id = spec_resp.json()["id"]
    await admin_client.put(f"/admin/clinics/{clinic_id}/specialties", json=[{"specialty_id": spec_id}])

    cs_list = (await admin_client.put(f"/admin/clinics/{clinic_id}/specialties", json=[{"specialty_id": spec_id}])).json()
    cs_id = cs_list[0]["id"]
    doc_resp = await admin_client.post("/admin/doctors", json={"name": "Dr X", "clinic_specialty_id": cs_id})
    doctor_id = doc_resp.json()["id"]

    with db_engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO slot (doctor_id, start_at) VALUES (:d, '2026-12-01 10:00:00+00')"
        ), {"d": doctor_id})
        acct_id = conn.execute(text("SELECT id FROM account LIMIT 1")).scalar_one()
        profile_id = conn.execute(
            text("SELECT id FROM profile WHERE account_id = :a"), {"a": acct_id}
        ).scalar_one()
        slot_id = conn.execute(text("SELECT id FROM slot LIMIT 1")).scalar_one()
        conn.execute(text(
            "INSERT INTO visit (profile_id, slot_id) VALUES (:p, :s)"
        ), {"p": profile_id, "s": slot_id})
        conn.commit()

    del_resp = await admin_client.delete(f"/admin/clinics/{clinic_id}")
    assert del_resp.status_code == 409
    assert del_resp.json()["detail"]["error"]["code"] == "has_history"


# --- Doctor needs a clinic that has a linked specialty ---


@pytest.mark.anyio()
async def test_doctor_needs_clinic_specialty(admin_client: AsyncClient) -> None:
    resp = await admin_client.post(
        "/admin/doctors",
        json={"name": "Dr X", "clinic_specialty_id": 99999},
    )
    assert resp.status_code == 404


# --- Location blocked by profile ---


@pytest.mark.anyio()
async def test_A5_delete_location_blocked_by_profile(admin_client: AsyncClient) -> None:
    # create_admin gives the admin a profile in "DefaultLoc"
    result = await admin_client.get("/admin/locations")
    locations = result.json()
    default_loc = next((l for l in locations if l["name"] == "DefaultLoc"), None)
    assert default_loc is not None, "DefaultLoc should exist from admin setup"
    resp = await admin_client.delete(f"/admin/locations/{default_loc['id']}")
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "has_history"


# --- Specialty blocked by clinic_specialty ---


@pytest.mark.anyio()
async def test_A5_delete_specialty_blocked_by_clinic(admin_client: AsyncClient) -> None:
    loc_resp = await admin_client.post("/admin/locations", json={"name": "TestCity"})
    loc_id = loc_resp.json()["id"]
    clinic_resp = await admin_client.post("/admin/clinics", json={"name": "Clinic A", "location_id": loc_id})
    clinic_id = clinic_resp.json()["id"]
    spec_resp = await admin_client.post("/admin/specialties", json={"name": "Derm"})
    spec_id = spec_resp.json()["id"]
    await admin_client.put(f"/admin/clinics/{clinic_id}/specialties", json=[{"specialty_id": spec_id}])

    del_resp = await admin_client.delete(f"/admin/specialties/{spec_id}")
    assert del_resp.status_code == 409
    assert del_resp.json()["detail"]["error"]["code"] == "has_history"


async def _clinic_with_doctor(admin_client: AsyncClient) -> dict[str, int]:
    location_id = (await admin_client.post("/admin/locations", json={"name": "TestCity"})).json()["id"]
    clinic_id = (
        await admin_client.post("/admin/clinics", json={"name": "TestCity Clinic", "location_id": location_id})
    ).json()["id"]
    specialty_id = (await admin_client.post("/admin/specialties", json={"name": "Derm"})).json()["id"]
    links = await admin_client.put(f"/admin/clinics/{clinic_id}/specialties", json=[{"specialty_id": specialty_id}])
    doctor_id = (
        await admin_client.post("/admin/doctors", json={"name": "Dr X", "clinic_specialty_id": links.json()[0]["id"]})
    ).json()["id"]
    return {"locations": location_id, "clinics": clinic_id, "specialties": specialty_id, "doctors": doctor_id}


def _book_slot_for_admin(db_engine: Engine, doctor_id: int) -> None:
    with db_engine.connect() as conn:
        slot_id = conn.execute(
            text("INSERT INTO slot (doctor_id, start_at) VALUES (:d, '2026-12-01 10:00:00+00') RETURNING id"),
            {"d": doctor_id},
        ).scalar_one()
        profile_id = conn.execute(text("SELECT id FROM profile LIMIT 1")).scalar_one()
        conn.execute(text("INSERT INTO visit (profile_id, slot_id) VALUES (:p, :s)"), {"p": profile_id, "s": slot_id})
        conn.commit()


@pytest.mark.anyio()
async def test_A4_duplicate_location_and_specialty_use_name_taken(admin_client: AsyncClient) -> None:
    await admin_client.post("/admin/locations", json={"name": "Cairo"})
    await admin_client.post("/admin/specialties", json={"name": "Cardiology"})

    location = await admin_client.post("/admin/locations", json={"name": "CAIRO"})
    specialty = await admin_client.post("/admin/specialties", json={"name": "CARDIOLOGY"})

    assert location.json()["detail"]["error"]["code"] == "name_taken"
    assert specialty.json()["detail"]["error"]["code"] == "name_taken"


@pytest.mark.anyio()
async def test_catalog_lists_carry_clinic_counts_specialties_and_doctor_names(admin_client: AsyncClient) -> None:
    ids = await _clinic_with_doctor(admin_client)

    locations = {row["name"]: row for row in (await admin_client.get("/admin/locations")).json()}
    clinic = next(row for row in (await admin_client.get("/admin/clinics")).json() if row["id"] == ids["clinics"])
    doctor = next(row for row in (await admin_client.get("/admin/doctors")).json() if row["id"] == ids["doctors"])

    assert locations["TestCity"]["clinic_count"] == 1
    assert locations["DefaultLoc"]["clinic_count"] == 0
    assert clinic["location_name"] == "TestCity"
    assert clinic["specialties"] == [
        {"id": ids["specialties"], "name": "Derm", "clinic_specialty_id": doctor["clinic_specialty_id"]}
    ]
    assert (doctor["clinic_id"], doctor["clinic_name"]) == (ids["clinics"], "TestCity Clinic")
    assert (doctor["specialty_id"], doctor["specialty_name"]) == (ids["specialties"], "Derm")


@pytest.mark.anyio()
async def test_A5_cascade_preview_matches_what_delete_removes(admin_client: AsyncClient, db_engine: Engine) -> None:
    ids = await _clinic_with_doctor(admin_client)
    with db_engine.connect() as conn:
        for hour in (9, 10, 11):
            conn.execute(
                text("INSERT INTO slot (doctor_id, start_at) VALUES (:d, :t)"),
                {"d": ids["doctors"], "t": f"2026-12-01 {hour}:00:00+00"},
            )
        conn.commit()

    location_preview = (await admin_client.get(f"/admin/locations/{ids['locations']}/cascade")).json()
    clinic_preview = (await admin_client.get(f"/admin/clinics/{ids['clinics']}/cascade")).json()
    doctor_preview = (await admin_client.get(f"/admin/doctors/{ids['doctors']}/cascade")).json()
    specialty_preview = (await admin_client.get(f"/admin/specialties/{ids['specialties']}/cascade")).json()
    deleted = (await admin_client.delete(f"/admin/locations/{ids['locations']}")).json()

    assert location_preview == {"cascade": {"clinics": 1, "doctors": 1, "slots": 3}, "blocked": None}
    assert clinic_preview == {"cascade": {"specialties": 1, "doctors": 1, "slots": 3}, "blocked": None}
    assert doctor_preview == {"cascade": {"slots": 3}, "blocked": None}
    assert specialty_preview == {"cascade": {}, "blocked": "Can't delete: 1 clinic(s) offer this specialty."}
    assert deleted == {"deleted": True, "cascade": location_preview["cascade"]}
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM slot")).scalar_one() == 0


@pytest.mark.anyio()
async def test_A5_cascade_preview_names_the_visit_history_block(admin_client: AsyncClient, db_engine: Engine) -> None:
    ids = await _clinic_with_doctor(admin_client)
    _book_slot_for_admin(db_engine, ids["doctors"])

    for kind in ("locations", "clinics", "doctors"):
        preview = (await admin_client.get(f"/admin/{kind}/{ids[kind]}/cascade")).json()
        assert preview["blocked"] == "Can't delete: it has visit history.", kind


@pytest.mark.anyio()
async def test_A5_location_with_visits_from_members_elsewhere_is_blocked_not_500(
    admin_client: AsyncClient, db_engine: Engine
) -> None:
    ids = await _clinic_with_doctor(admin_client)
    _book_slot_for_admin(db_engine, ids["doctors"])

    resp = await admin_client.delete(f"/admin/locations/{ids['locations']}")

    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == {"code": "has_history", "message": "Can't delete: it has visit history."}
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM clinic")).scalar_one() == 1


@pytest.mark.anyio()
async def test_A5_cascade_preview_of_missing_id_is_404(admin_client: AsyncClient) -> None:
    for kind in ("locations", "specialties", "clinics", "doctors"):
        assert (await admin_client.get(f"/admin/{kind}/999999/cascade")).status_code == 404
