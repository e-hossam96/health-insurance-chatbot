from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai_ports import make_ports
from backend.config import Settings
from backend.database import create_engine
from chatbot_ai.tools.models import InvalidArgument
from chatbot_ai.tools.ports import ComplaintsPort, Ports, SchedulingPort

TEST_DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot")
NOW = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


@dataclass(frozen=True)
class Seed:
    cairo: int
    giza: int
    derm: int
    cardio: int
    sara: int
    omar: int
    lina: int
    karim: int
    me: int
    other: int
    slots: dict[str, int]
    visits: dict[str, int]


def _insert(conn: Connection, sql: str, **params: object) -> int:
    value: int = conn.execute(text(sql + " RETURNING id"), params).scalar_one()
    return value


def _seed(engine: Engine) -> Seed:
    with engine.begin() as conn:
        cairo = _insert(conn, "INSERT INTO location (name) VALUES ('Cairo')")
        giza = _insert(conn, "INSERT INTO location (name) VALUES ('Giza')")
        derm = _insert(conn, "INSERT INTO specialty (name) VALUES ('Dermatology')")
        cardio = _insert(conn, "INSERT INTO specialty (name) VALUES ('Cardiology')")
        cairo_clinic = _insert(conn, "INSERT INTO clinic (name, location_id) VALUES ('Cairo Clinic', :l)", l=cairo)
        nile = _insert(conn, "INSERT INTO clinic (name, location_id) VALUES ('Nile Medical', :l)", l=giza)
        cs_cairo_derm = _insert(conn, "INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s)", c=cairo_clinic, s=derm)
        cs_cairo_cardio = _insert(conn, "INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s)", c=cairo_clinic, s=cardio)
        cs_nile_derm = _insert(conn, "INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s)", c=nile, s=derm)
        sara = _insert(conn, "INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr. Sara Nabil', :cs)", cs=cs_cairo_derm)
        lina = _insert(conn, "INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr. Lina Fares', :cs)", cs=cs_cairo_derm)
        omar = _insert(conn, "INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr. Omar Hassan', :cs)", cs=cs_nile_derm)
        karim = _insert(conn, "INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr. Karim Adel', :cs)", cs=cs_cairo_cardio)

        def slot(doctor: int, start: str, status: str = "available") -> int:
            return _insert(conn, "INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, :t, :st)", d=doctor, t=start, st=status)

        slots = {
            "sara_past": slot(sara, "2026-11-20 10:00:00+00"),
            "sara_dec15": slot(sara, "2026-12-15 10:00:00+00"),
            "sara_dec18": slot(sara, "2026-12-18 10:00:00+00"),
            "sara_booked": slot(sara, "2026-12-03 10:00:00+00", "booked"),
            "lina_dec16": slot(lina, "2026-12-16 11:00:00+00"),
            "omar_dec14": slot(omar, "2026-12-14 09:00:00+00"),
            "karim_dec17": slot(karim, "2026-12-17 13:00:00+00"),
            "lina_nov2": slot(lina, "2026-11-02 10:00:00+00", "booked"),
            "lina_nov5": slot(lina, "2026-11-05 10:00:00+00", "booked"),
            "omar_dec20": slot(omar, "2026-12-20 10:00:00+00", "booked"),
        }
        accounts = [
            _insert(conn, "INSERT INTO account (username, password_hash, role) VALUES (:u, 'x', 'user')", u=name)
            for name in ("me", "other")
        ]
        me = _insert(conn, "INSERT INTO profile (account_id, name, location_id) VALUES (:a, 'Mona', :l)", a=accounts[0], l=cairo)
        other = _insert(conn, "INSERT INTO profile (account_id, name, location_id) VALUES (:a, 'Ola', :l)", a=accounts[1], l=giza)

        def visit(profile: int, slot_key: str, status: str) -> int:
            return _insert(conn, "INSERT INTO visit (profile_id, slot_id, status) VALUES (:p, :s, :st)", p=profile, s=slots[slot_key], st=status)

        visits = {
            "mine_scheduled": visit(me, "sara_booked", "scheduled"),
            "mine_completed": visit(me, "lina_nov2", "completed"),
            "mine_completed_with_complaint": visit(me, "lina_nov5", "completed"),
            "others_scheduled": visit(other, "omar_dec20", "scheduled"),
        }
        complaint = _insert(
            conn, "INSERT INTO complaint (visit_id, description) VALUES (:v, 'Long wait')", v=visits["mine_completed_with_complaint"]
        )
        _insert(conn, "INSERT INTO complaint_reply (complaint_id, admin_account_id, body) VALUES (:c, :a, 'Sorry about that')", c=complaint, a=accounts[1])
    return Seed(cairo, giza, derm, cardio, sara, omar, lina, karim, me, other, slots, visits)


@pytest.fixture()
def seed(_clean_database: None, db_engine: Engine) -> Seed:
    return _seed(db_engine)


@pytest.fixture()
async def session() -> AsyncIterator[AsyncSession]:
    engine, factory = create_engine(Settings(database_url=TEST_DB_URL))  # type: ignore[call-arg]
    async with factory() as db:
        yield db
    await engine.dispose()


def _ports(session: AsyncSession, seed: Seed, profile: int | None = None) -> Ports:
    acting = profile if profile is not None else seed.me
    home = seed.cairo if acting == seed.me else seed.giza
    return make_ports(session, acting, home, FixedClock())


@pytest.mark.anyio()
async def test_sql_ports_satisfy_the_protocols(session: AsyncSession, seed: Seed) -> None:
    ports = _ports(session, seed)
    assert isinstance(ports.scheduling, SchedulingPort)
    assert isinstance(ports.complaints, ComplaintsPort)


@pytest.mark.anyio()
async def test_C7_only_available_future_slots_are_offered(session: AsyncSession, seed: Seed) -> None:
    cards = await _ports(session, seed).scheduling.available_slots(seed.sara, None, None, 10)
    assert [c.slot_id for c in cards] == [seed.slots["sara_dec15"], seed.slots["sara_dec18"]]
    assert cards[0].model_dump() == {
        "slot_id": seed.slots["sara_dec15"],
        "doctor_name": "Dr. Sara Nabil",
        "specialty": "Dermatology",
        "clinic": "Cairo Clinic",
        "location": "Cairo",
        "start_at": "2026-12-15T10:00:00Z",
    }


@pytest.mark.anyio()
async def test_C7_availability_window_and_limit(session: AsyncSession, seed: Seed) -> None:
    scheduling = _ports(session, seed).scheduling
    window = await scheduling.available_slots(seed.sara, date(2026, 12, 16), date(2026, 12, 18), 10)
    assert [c.slot_id for c in window] == [seed.slots["sara_dec18"]]
    assert len(await scheduling.available_slots(seed.sara, None, None, 1)) == 1


@pytest.mark.anyio()
async def test_D5_recommendations_rank_by_profile_location_then_earliest_slot(session: AsyncSession, seed: Seed) -> None:
    scheduling = _ports(session, seed).scheduling
    ranked = await scheduling.recommend_doctors(seed.derm, None, 3)
    assert [(c.doctor_name, c.start_at) for c in ranked] == [
        ("Dr. Sara Nabil", "2026-12-15T10:00:00Z"),
        ("Dr. Lina Fares", "2026-12-16T11:00:00Z"),
        ("Dr. Omar Hassan", "2026-12-14T09:00:00Z"),
    ]
    in_giza = await scheduling.recommend_doctors(seed.derm, seed.giza, 3)
    assert in_giza[0].doctor_name == "Dr. Omar Hassan"
    assert [c.doctor_name for c in await scheduling.recommend_doctors(seed.derm, None, 2)] == ["Dr. Sara Nabil", "Dr. Lina Fares"]
    assert [c.doctor_name for c in await scheduling.recommend_doctors(seed.cardio, None, 3)] == ["Dr. Karim Adel"]


@pytest.mark.anyio()
async def test_D5_ranking_is_deterministic(session: AsyncSession, seed: Seed) -> None:
    scheduling = _ports(session, seed).scheduling
    first = await scheduling.recommend_doctors(seed.derm, None, 3)
    assert all([await scheduling.recommend_doctors(seed.derm, None, 3) == first for _ in range(3)])


@pytest.mark.anyio()
async def test_B6_visits_are_bound_to_the_acting_profile(session: AsyncSession, seed: Seed) -> None:
    mine = await _ports(session, seed).scheduling.my_visits(None)
    assert {v.visit_id for v in mine} == {seed.visits["mine_scheduled"], seed.visits["mine_completed"], seed.visits["mine_completed_with_complaint"]}
    assert [v.status for v in await _ports(session, seed).scheduling.my_visits("scheduled")] == ["scheduled"]
    theirs = await _ports(session, seed, seed.other).scheduling.my_visits(None)
    assert [v.visit_id for v in theirs] == [seed.visits["others_scheduled"]]


@pytest.mark.anyio()
async def test_D8_cancel_proposals_are_own_scheduled_visits_only(session: AsyncSession, seed: Seed) -> None:
    scheduling = _ports(session, seed).scheduling
    assert [v.visit_id for v in await scheduling.scheduled_visits(None)] == [seed.visits["mine_scheduled"]]
    assert await scheduling.scheduled_visits(seed.visits["others_scheduled"]) == []
    assert await scheduling.scheduled_visits(seed.visits["mine_completed"]) == []


@pytest.mark.anyio()
async def test_E1_E2_complaint_candidates_are_own_completed_visits_without_a_complaint(session: AsyncSession, seed: Seed) -> None:
    complaints = _ports(session, seed).complaints
    eligible = await complaints.eligible_visits()
    assert [v.visit_id for v in eligible] == [seed.visits["mine_completed"]]
    assert eligible[0].start_at == "2026-11-02T10:00:00Z"
    assert await _ports(session, seed, seed.other).complaints.eligible_visits() == []


@pytest.mark.anyio()
async def test_my_complaints_include_admin_replies_for_the_acting_profile_only(session: AsyncSession, seed: Seed) -> None:
    mine = await _ports(session, seed).complaints.my_complaints()
    assert [(c.description, c.status, c.replies) for c in mine] == [("Long wait", "open", ["Sorry about that"])]
    assert await _ports(session, seed, seed.other).complaints.my_complaints() == []


@pytest.mark.anyio()
async def test_I5_catalog_searches_filter_and_unknown_ids_are_rejected(session: AsyncSession, seed: Seed) -> None:
    scheduling = _ports(session, seed).scheduling
    assert [c.name for c in await scheduling.search_clinics(None, seed.cardio)] == ["Cairo Clinic"]
    clinic = (await scheduling.search_clinics(seed.cairo, None))[0]
    assert clinic.specialties == ["Cardiology", "Dermatology"]
    assert [d.name for d in await scheduling.search_doctors(None, seed.giza, None)] == ["Dr. Omar Hassan"]
    assert [d.name for d in await scheduling.search_doctors(None, None, seed.cardio)] == ["Dr. Karim Adel"]
    assert [loc.name for loc in await scheduling.list_locations()] == ["Cairo", "Giza"]
    for call in (
        scheduling.recommend_doctors(99999, None, 3),
        scheduling.search_clinics(99999, None),
        scheduling.search_doctors(99999, None, None),
        scheduling.available_slots(99999, None, None, 3),
    ):
        with pytest.raises(InvalidArgument, match="99999"):
            await call


@pytest.mark.anyio()
async def test_C7_a_slot_starting_exactly_now_is_not_offered(session: AsyncSession, seed: Seed, db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        at_now = _insert(conn, "INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, :t, 'available')", d=seed.karim, t=NOW.isoformat())
    scheduling = _ports(session, seed).scheduling
    assert at_now not in [c.slot_id for c in await scheduling.available_slots(seed.karim, None, None, 10)]
    assert [c.start_at for c in await scheduling.recommend_doctors(seed.cardio, None, 3)] == ["2026-12-17T13:00:00Z"]


@pytest.mark.anyio()
async def test_D5_ties_on_location_and_time_break_by_slot_id(session: AsyncSession, seed: Seed, db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        cs = conn.execute(
            text("SELECT d.clinic_specialty_id FROM doctor d WHERE d.id = :d"), {"d": seed.karim}
        ).scalar_one()
        late = _insert(conn, "INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr. Zed Late', :cs)", cs=cs)
        early = _insert(conn, "INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr. Amy Early', :cs)", cs=cs)
        later_slot = _insert(conn, "INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-10 09:00:00+00', 'available')", d=early)
        earlier_slot = _insert(conn, "INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-10 09:00:00+00', 'available')", d=late)
    assert earlier_slot > later_slot
    ranked = await _ports(session, seed).scheduling.recommend_doctors(seed.cardio, None, 3)
    assert [c.slot_id for c in ranked[:2]] == [later_slot, earlier_slot]
    assert [c.doctor_name for c in ranked] == ["Dr. Amy Early", "Dr. Zed Late", "Dr. Karim Adel"]


@pytest.mark.anyio()
async def test_G8_only_ready_documents_are_reported_searchable(session: AsyncSession, seed: Seed, db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        admin = _insert(conn, "INSERT INTO account (username, password_hash, role) VALUES ('kbadmin', 'x', 'admin')")
        ids = {
            status: _insert(
                conn,
                "INSERT INTO kb_document (filename, file_type, file_size_bytes, storage_path, content_hash, status, uploaded_by) "
                "VALUES (:n, 'txt', 1, :p, :h, :s, :a)",
                n=f"{status}.txt", p=f"/data/kb/{status}.txt", h=status, s=status, a=admin,
            )
            for status in ("uploaded", "processing", "ready", "failed")
        }
    assert await _ports(session, seed).knowledge.ready_document_ids() == [ids["ready"]]
