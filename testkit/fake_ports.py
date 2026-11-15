from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from chatbot_ai.tools.models import (
    ClinicInfo,
    ComplaintInfo,
    DoctorCard,
    DoctorInfo,
    InvalidArgument,
    NamedRef,
    VisitCard,
    VisitInfo,
    VisitStatus,
)
from chatbot_ai.tools.ports import Ports


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
    status: VisitStatus


@dataclass(frozen=True)
class FakeComplaint:
    id: int
    visit_id: int
    description: str
    replies: tuple[str, ...] = ()


@dataclass
class FakeCatalog:
    locations: list[NamedRef] = field(default_factory=list)
    specialties: list[NamedRef] = field(default_factory=list)
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

    def check(self, *, location_id: int | None = None, specialty_id: int | None = None, clinic_id: int | None = None, doctor_id: int | None = None) -> None:
        if location_id is not None and all(loc.id != location_id for loc in self.locations):
            raise InvalidArgument(f"unknown location_id {location_id}")
        if specialty_id is not None and all(s.id != specialty_id for s in self.specialties):
            raise InvalidArgument(f"unknown specialty_id {specialty_id}")
        if clinic_id is not None and all(c.id != clinic_id for c in self.clinics):
            raise InvalidArgument(f"unknown clinic_id {clinic_id}")
        if doctor_id is not None and all(d.id != doctor_id for d in self.doctors):
            raise InvalidArgument(f"unknown doctor_id {doctor_id}")


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def doctor_card(catalog: FakeCatalog, slot: FakeSlot) -> DoctorCard:
    doctor = catalog.doctor(slot.doctor_id)
    clinic = catalog.clinic(doctor.clinic_id)
    return DoctorCard(
        slot_id=slot.id,
        doctor_name=doctor.name,
        specialty=catalog.specialty_name(doctor.specialty_id),
        clinic=clinic.name,
        location=catalog.location_name(clinic.location_id),
        start_at=_iso(slot.start_at),
    )


def visit_card(catalog: FakeCatalog, visit: FakeVisit) -> VisitCard:
    slot = catalog.slot(visit.slot_id)
    doctor = catalog.doctor(slot.doctor_id)
    return VisitCard(
        visit_id=visit.id,
        start_at=_iso(slot.start_at),
        doctor_name=doctor.name,
        specialty=catalog.specialty_name(doctor.specialty_id),
        clinic=catalog.clinic(doctor.clinic_id).name,
    )


class FakeSchedulingPort:
    def __init__(self, catalog: FakeCatalog, profile_id: int, profile_location_id: int, now: datetime) -> None:
        self.catalog = catalog
        self._profile_id = profile_id
        self._profile_location_id = profile_location_id
        self._now = now
        self.calls: list[str] = []

    def _open_slots(self) -> list[FakeSlot]:
        return sorted(
            (s for s in self.catalog.slots if s.status == "available" and s.start_at > self._now),
            key=lambda s: (s.start_at, s.id),
        )

    async def list_locations(self) -> list[NamedRef]:
        self.calls.append("list_locations")
        return list(self.catalog.locations)

    async def list_specialties(self) -> list[NamedRef]:
        self.calls.append("list_specialties")
        return list(self.catalog.specialties)

    async def search_clinics(self, location_id: int | None, specialty_id: int | None) -> list[ClinicInfo]:
        self.calls.append("search_clinics")
        self.catalog.check(location_id=location_id, specialty_id=specialty_id)
        return [
            ClinicInfo(
                id=c.id,
                name=c.name,
                location_id=c.location_id,
                location=self.catalog.location_name(c.location_id),
                specialties=[self.catalog.specialty_name(s) for s in c.specialty_ids],
            )
            for c in self.catalog.clinics
            if (location_id is None or c.location_id == location_id) and (specialty_id is None or specialty_id in c.specialty_ids)
        ]

    async def search_doctors(self, clinic_id: int | None, location_id: int | None, specialty_id: int | None) -> list[DoctorInfo]:
        self.calls.append("search_doctors")
        self.catalog.check(location_id=location_id, specialty_id=specialty_id, clinic_id=clinic_id)
        result: list[DoctorInfo] = []
        for d in self.catalog.doctors:
            clinic = self.catalog.clinic(d.clinic_id)
            if (clinic_id is None or d.clinic_id == clinic_id) and (location_id is None or clinic.location_id == location_id) and (
                specialty_id is None or d.specialty_id == specialty_id
            ):
                result.append(
                    DoctorInfo(
                        id=d.id,
                        name=d.name,
                        specialty_id=d.specialty_id,
                        specialty=self.catalog.specialty_name(d.specialty_id),
                        clinic_id=clinic.id,
                        clinic=clinic.name,
                        location=self.catalog.location_name(clinic.location_id),
                    )
                )
        return result

    async def available_slots(self, doctor_id: int, from_date: date | None, to_date: date | None, limit: int) -> list[DoctorCard]:
        self.calls.append("available_slots")
        self.catalog.check(doctor_id=doctor_id)
        slots = [
            s
            for s in self._open_slots()
            if s.doctor_id == doctor_id
            and (from_date is None or s.start_at.date() >= from_date)
            and (to_date is None or s.start_at.date() <= to_date)
        ]
        return [doctor_card(self.catalog, s) for s in slots[:limit]]

    async def recommend_doctors(self, specialty_id: int, location_id: int | None, limit: int) -> list[DoctorCard]:
        self.calls.append("recommend_doctors")
        self.catalog.check(specialty_id=specialty_id, location_id=location_id)
        wanted = location_id if location_id is not None else self._profile_location_id
        earliest: dict[int, FakeSlot] = {}
        for slot in self._open_slots():
            if self.catalog.doctor(slot.doctor_id).specialty_id == specialty_id:
                earliest.setdefault(slot.doctor_id, slot)

        def rank(slot: FakeSlot) -> tuple[int, datetime, int]:
            clinic = self.catalog.clinic(self.catalog.doctor(slot.doctor_id).clinic_id)
            return (0 if clinic.location_id == wanted else 1, slot.start_at, slot.id)

        return [doctor_card(self.catalog, s) for s in sorted(earliest.values(), key=rank)[:limit]]

    async def my_visits(self, status: VisitStatus | None) -> list[VisitInfo]:
        self.calls.append("my_visits")
        return [
            VisitInfo(**visit_card(self.catalog, v).model_dump(), status=v.status)
            for v in self.catalog.visits
            if v.profile_id == self._profile_id and (status is None or v.status == status)
        ]

    async def scheduled_visits(self, visit_id: int | None) -> list[VisitCard]:
        self.calls.append("scheduled_visits")
        return [
            visit_card(self.catalog, v)
            for v in self.catalog.visits
            if v.profile_id == self._profile_id and v.status == "scheduled" and (visit_id is None or v.id == visit_id)
        ]


class FakeComplaintsPort:
    def __init__(self, catalog: FakeCatalog, profile_id: int) -> None:
        self.catalog = catalog
        self._profile_id = profile_id
        self.calls: list[str] = []

    async def my_complaints(self) -> list[ComplaintInfo]:
        self.calls.append("my_complaints")
        own = {v.id for v in self.catalog.visits if v.profile_id == self._profile_id}
        return [
            ComplaintInfo(id=c.id, visit_id=c.visit_id, description=c.description, status="open", replies=list(c.replies))
            for c in self.catalog.complaints
            if c.visit_id in own
        ]

    async def eligible_visits(self) -> list[VisitCard]:
        self.calls.append("eligible_visits")
        complained = {c.visit_id for c in self.catalog.complaints}
        return [
            visit_card(self.catalog, v)
            for v in self.catalog.visits
            if v.profile_id == self._profile_id and v.status == "completed" and v.id not in complained
        ]


@dataclass
class FakeKnowledgePort:
    ready_ids: list[int] = field(default_factory=list)

    async def ready_document_ids(self) -> list[int]:
        return list(self.ready_ids)


@dataclass(frozen=True)
class FakePorts:
    scheduling: FakeSchedulingPort
    complaints: FakeComplaintsPort
    knowledge: FakeKnowledgePort

    def as_ports(self) -> Ports:
        return Ports(scheduling=self.scheduling, complaints=self.complaints, knowledge=self.knowledge)


def fake_ports(catalog: FakeCatalog, profile_id: int, profile_location_id: int, now: datetime) -> Ports:
    return make_fake_ports(catalog, profile_id, profile_location_id, now).as_ports()


def make_fake_ports(catalog: FakeCatalog, profile_id: int, profile_location_id: int, now: datetime) -> FakePorts:
    return FakePorts(
        scheduling=FakeSchedulingPort(catalog, profile_id, profile_location_id, now),
        complaints=FakeComplaintsPort(catalog, profile_id),
        knowledge=FakeKnowledgePort(),
    )


def sample_catalog() -> FakeCatalog:
    return FakeCatalog(
        locations=[NamedRef(id=1, name="Cairo"), NamedRef(id=2, name="Giza")],
        specialties=[NamedRef(id=1, name="Dermatology"), NamedRef(id=2, name="Cardiology")],
        clinics=[FakeClinic(1, "Cairo Clinic", 1, (1, 2)), FakeClinic(2, "Nile Medical", 2, (1,))],
        doctors=[
            FakeDoctor(1, "Dr. Sara Nabil", 1, 1),
            FakeDoctor(2, "Dr. Omar Hassan", 2, 1),
            FakeDoctor(3, "Dr. Lina Fares", 1, 1),
            FakeDoctor(4, "Dr. Karim Adel", 1, 2),
        ],
        slots=[
            FakeSlot(1, 1, datetime(2026, 12, 15, 10, tzinfo=UTC)),
            FakeSlot(2, 2, datetime(2026, 12, 14, 9, tzinfo=UTC)),
            FakeSlot(3, 3, datetime(2026, 12, 16, 11, tzinfo=UTC)),
            FakeSlot(4, 1, datetime(2026, 11, 20, 10, tzinfo=UTC)),
            FakeSlot(5, 3, datetime(2026, 12, 15, 9, tzinfo=UTC), status="booked"),
            FakeSlot(6, 4, datetime(2026, 12, 17, 13, tzinfo=UTC)),
            FakeSlot(7, 1, datetime(2026, 11, 2, 10, tzinfo=UTC), status="booked"),
            FakeSlot(8, 2, datetime(2026, 12, 20, 10, tzinfo=UTC), status="booked"),
        ],
        visits=[
            FakeVisit(1, profile_id=10, slot_id=5, status="scheduled"),
            FakeVisit(2, profile_id=10, slot_id=7, status="completed"),
            FakeVisit(3, profile_id=11, slot_id=8, status="scheduled"),
        ],
    )
