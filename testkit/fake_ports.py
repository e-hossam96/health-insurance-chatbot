from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from chatbot_ai.interface import Ports

PortRecord = dict[str, Any]  # Any: the Port Protocols return JSON-like dicts until 6b types them

CARD_LIMIT = 3


@dataclass(frozen=True)
class FakeLocation:
    id: int
    name: str


@dataclass(frozen=True)
class FakeSpecialty:
    id: int
    name: str


@dataclass(frozen=True)
class FakeClinic:
    id: int
    name: str
    location_id: int
    specialty_ids: tuple[int, ...]


@dataclass(frozen=True)
class FakeDoctor:
    id: int
    name: str
    clinic_id: int
    specialty_id: int


@dataclass(frozen=True)
class FakeSlot:
    id: int
    doctor_id: int
    start_at: datetime
    status: str = "available"


@dataclass(frozen=True)
class FakeVisit:
    id: int
    profile_id: int
    slot_id: int
    status: str


@dataclass(frozen=True)
class FakeComplaint:
    id: int
    visit_id: int
    description: str
    status: str = "open"
    replies: tuple[str, ...] = ()


@dataclass
class FakeCatalog:
    locations: list[FakeLocation] = field(default_factory=list)
    specialties: list[FakeSpecialty] = field(default_factory=list)
    clinics: list[FakeClinic] = field(default_factory=list)
    doctors: list[FakeDoctor] = field(default_factory=list)
    slots: list[FakeSlot] = field(default_factory=list)
    visits: list[FakeVisit] = field(default_factory=list)
    complaints: list[FakeComplaint] = field(default_factory=list)

    def doctor(self, doctor_id: int) -> FakeDoctor:
        return next(d for d in self.doctors if d.id == doctor_id)

    def clinic(self, clinic_id: int) -> FakeClinic:
        return next(c for c in self.clinics if c.id == clinic_id)

    def slot(self, slot_id: int) -> FakeSlot:
        return next(s for s in self.slots if s.id == slot_id)

    def location_name(self, location_id: int) -> str:
        return next(loc.name for loc in self.locations if loc.id == location_id)

    def specialty_name(self, specialty_id: int) -> str:
        return next(s.name for s in self.specialties if s.id == specialty_id)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def doctor_card(catalog: FakeCatalog, slot: FakeSlot) -> PortRecord:
    doctor = catalog.doctor(slot.doctor_id)
    clinic = catalog.clinic(doctor.clinic_id)
    return {
        "slot_id": slot.id,
        "doctor_name": doctor.name,
        "specialty": catalog.specialty_name(doctor.specialty_id),
        "clinic": clinic.name,
        "location": catalog.location_name(clinic.location_id),
        "start_at": _iso(slot.start_at),
    }


def visit_card(catalog: FakeCatalog, visit: FakeVisit) -> PortRecord:
    slot = catalog.slot(visit.slot_id)
    doctor = catalog.doctor(slot.doctor_id)
    return {
        "visit_id": visit.id,
        "start_at": _iso(slot.start_at),
        "doctor_name": doctor.name,
        "specialty": catalog.specialty_name(doctor.specialty_id),
        "clinic": catalog.clinic(doctor.clinic_id).name,
    }


class FakeSchedulingPort:
    def __init__(self, catalog: FakeCatalog, profile_id: int, profile_location_id: int, now: datetime) -> None:
        self._catalog = catalog
        self._profile_id = profile_id
        self._profile_location_id = profile_location_id
        self._now = now

    def _doctor_card(self, slot: FakeSlot) -> PortRecord:
        return doctor_card(self._catalog, slot)

    def _visit_card(self, visit: FakeVisit) -> PortRecord:
        return visit_card(self._catalog, visit)

    def _open_slots(self, doctor_id: int | None = None) -> list[FakeSlot]:
        return sorted(
            (
                s
                for s in self._catalog.slots
                if s.status == "available" and s.start_at > self._now and (doctor_id is None or s.doctor_id == doctor_id)
            ),
            key=lambda s: (s.start_at, s.id),
        )

    async def list_locations(self) -> list[PortRecord]:
        return [{"id": loc.id, "name": loc.name} for loc in self._catalog.locations]

    async def list_specialties(self) -> list[PortRecord]:
        return [{"id": s.id, "name": s.name} for s in self._catalog.specialties]

    async def search_clinics(self, location_id: int | None = None, specialty_id: int | None = None) -> list[PortRecord]:
        return [
            {"id": c.id, "name": c.name, "location": self._catalog.location_name(c.location_id), "specialty_ids": list(c.specialty_ids)}
            for c in self._catalog.clinics
            if (location_id is None or c.location_id == location_id)
            and (specialty_id is None or specialty_id in c.specialty_ids)
        ]

    async def search_doctors(
        self, clinic_id: int | None = None, location_id: int | None = None, specialty_id: int | None = None
    ) -> list[PortRecord]:
        return [
            {"id": d.id, "name": d.name, "clinic_id": d.clinic_id, "specialty": self._catalog.specialty_name(d.specialty_id)}
            for d in self._catalog.doctors
            if (clinic_id is None or d.clinic_id == clinic_id)
            and (location_id is None or self._catalog.clinic(d.clinic_id).location_id == location_id)
            and (specialty_id is None or d.specialty_id == specialty_id)
        ]

    async def get_availability(self, doctor_id: int, from_date: str | None = None, to_date: str | None = None) -> PortRecord:
        slots = [
            s
            for s in self._open_slots(doctor_id)
            if (from_date is None or _iso(s.start_at)[:10] >= from_date)
            and (to_date is None or _iso(s.start_at)[:10] <= to_date)
        ]
        return {"cards": [self._doctor_card(s) for s in slots[:CARD_LIMIT]], "slots": [_iso(s.start_at) for s in slots[:10]]}

    async def my_visits(self, status: str | None = None) -> list[PortRecord]:
        return [
            {**self._visit_card(v), "status": v.status}
            for v in self._catalog.visits
            if v.profile_id == self._profile_id and (status is None or v.status == status)
        ]

    async def recommend_doctors(self, specialty_id: int, location_id: int | None = None) -> PortRecord:
        wanted_location = location_id if location_id is not None else self._profile_location_id
        best: dict[int, FakeSlot] = {}
        for slot in self._open_slots():
            doctor = self._catalog.doctor(slot.doctor_id)
            if doctor.specialty_id == specialty_id and doctor.id not in best:
                best[doctor.id] = slot

        def rank(slot: FakeSlot) -> tuple[int, datetime, int]:
            clinic = self._catalog.clinic(self._catalog.doctor(slot.doctor_id).clinic_id)
            return (0 if clinic.location_id == wanted_location else 1, slot.start_at, slot.id)

        ranked = sorted(best.values(), key=rank)[:CARD_LIMIT]
        return {"cards": [self._doctor_card(s) for s in ranked]}

    async def propose_cancel(self, visit_id: int | None = None) -> PortRecord:
        own_scheduled = [
            v for v in self._catalog.visits if v.profile_id == self._profile_id and v.status == "scheduled"
        ]
        if visit_id is not None:
            own_scheduled = [v for v in own_scheduled if v.id == visit_id]
        return {"cards": [self._visit_card(v) for v in own_scheduled]}


class FakeComplaintsPort:
    def __init__(self, catalog: FakeCatalog, profile_id: int) -> None:
        self._catalog = catalog
        self._profile_id = profile_id

    def _own_visit_ids(self) -> set[int]:
        return {v.id for v in self._catalog.visits if v.profile_id == self._profile_id}

    async def my_complaints(self) -> list[PortRecord]:
        own = self._own_visit_ids()
        return [
            {"id": c.id, "visit_id": c.visit_id, "description": c.description, "status": c.status, "replies": list(c.replies)}
            for c in self._catalog.complaints
            if c.visit_id in own
        ]

    async def eligible_visits(self) -> PortRecord:
        complained = {c.visit_id for c in self._catalog.complaints}
        eligible = [
            v
            for v in self._catalog.visits
            if v.profile_id == self._profile_id and v.status == "completed" and v.id not in complained
        ]
        return {"cards": [visit_card(self._catalog, v) for v in eligible]}


def fake_ports(catalog: FakeCatalog, profile_id: int, profile_location_id: int, now: datetime) -> Ports:
    return Ports(
        scheduling=FakeSchedulingPort(catalog, profile_id, profile_location_id, now),
        complaints=FakeComplaintsPort(catalog, profile_id),
    )


def sample_catalog() -> FakeCatalog:
    cairo, giza = FakeLocation(1, "Cairo"), FakeLocation(2, "Giza")
    derm, cardio = FakeSpecialty(1, "Dermatology"), FakeSpecialty(2, "Cardiology")
    clinics = [FakeClinic(1, "Cairo Clinic", 1, (1, 2)), FakeClinic(2, "Nile Medical", 2, (1,))]
    doctors = [
        FakeDoctor(1, "Dr. Sara Nabil", 1, 1),
        FakeDoctor(2, "Dr. Omar Hassan", 2, 1),
        FakeDoctor(3, "Dr. Lina Fares", 1, 1),
        FakeDoctor(4, "Dr. Karim Adel", 1, 2),
    ]
    slots = [
        FakeSlot(1, 1, datetime(2026, 12, 15, 10, tzinfo=UTC)),
        FakeSlot(2, 2, datetime(2026, 12, 14, 9, tzinfo=UTC)),
        FakeSlot(3, 3, datetime(2026, 12, 16, 11, tzinfo=UTC)),
        FakeSlot(4, 1, datetime(2026, 11, 20, 10, tzinfo=UTC)),
        FakeSlot(5, 3, datetime(2026, 12, 15, 9, tzinfo=UTC), status="booked"),
        FakeSlot(6, 4, datetime(2026, 12, 17, 13, tzinfo=UTC)),
        FakeSlot(7, 1, datetime(2026, 11, 2, 10, tzinfo=UTC), status="booked"),
        FakeSlot(8, 2, datetime(2026, 12, 20, 10, tzinfo=UTC), status="booked"),
    ]
    visits = [
        FakeVisit(1, profile_id=10, slot_id=5, status="scheduled"),
        FakeVisit(2, profile_id=10, slot_id=7, status="completed"),
        FakeVisit(3, profile_id=11, slot_id=8, status="scheduled"),
    ]
    return FakeCatalog(
        locations=[cairo, giza], specialties=[derm, cardio], clinics=clinics, doctors=doctors, slots=slots, visits=visits
    )
