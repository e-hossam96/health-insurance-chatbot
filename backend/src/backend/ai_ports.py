from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Row, Select, case, exists, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import Clock
from backend.models import (
    Clinic,
    ClinicSpecialty,
    Complaint,
    ComplaintReply,
    Doctor,
    Location,
    Slot,
    SlotStatus,
    Specialty,
    Visit,
    VisitStatus,
)
from chatbot_ai.tools.models import (
    ClinicInfo,
    ComplaintInfo,
    DoctorCard,
    DoctorInfo,
    InvalidArgument,
    NamedRef,
    VisitCard,
    VisitInfo,
)
from chatbot_ai.tools.models import VisitStatus as VisitStatusName
from chatbot_ai.tools.ports import Ports


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _slot_card_query() -> Select[int, str, str, str, str, datetime]:
    return (
        select(Slot.id, Doctor.name, Specialty.name, Clinic.name, Location.name, Slot.start_at)
        .join(Doctor, Doctor.id == Slot.doctor_id)
        .join(ClinicSpecialty, ClinicSpecialty.id == Doctor.clinic_specialty_id)
        .join(Clinic, Clinic.id == ClinicSpecialty.clinic_id)
        .join(Specialty, Specialty.id == ClinicSpecialty.specialty_id)
        .join(Location, Location.id == Clinic.location_id)
    )


def _doctor_card(row: Row[int, str, str, str, str, datetime]) -> DoctorCard:
    slot_id, doctor, specialty, clinic, location, start_at = row
    return DoctorCard(slot_id=slot_id, doctor_name=doctor, specialty=specialty, clinic=clinic, location=location, start_at=iso_utc(start_at))


def _visit_query() -> Select[int, datetime, str, str, str, VisitStatus]:
    return (
        select(Visit.id, Slot.start_at, Doctor.name, Specialty.name, Clinic.name, Visit.status)
        .join(Slot, Slot.id == Visit.slot_id)
        .join(Doctor, Doctor.id == Slot.doctor_id)
        .join(ClinicSpecialty, ClinicSpecialty.id == Doctor.clinic_specialty_id)
        .join(Clinic, Clinic.id == ClinicSpecialty.clinic_id)
        .join(Specialty, Specialty.id == ClinicSpecialty.specialty_id)
    )


def _visit_card(row: Row[int, datetime, str, str, str, VisitStatus]) -> VisitCard:
    visit_id, start_at, doctor, specialty, clinic, _ = row
    return VisitCard(visit_id=visit_id, start_at=iso_utc(start_at), doctor_name=doctor, specialty=specialty, clinic=clinic)


class SqlSchedulingPort:
    def __init__(self, db: AsyncSession, profile_id: int, profile_location_id: int, clock: Clock) -> None:
        self._db = db
        self._profile_id = profile_id
        self._profile_location_id = profile_location_id
        self._clock = clock

    async def _require(self, model: type[Location | Specialty | Clinic | Doctor], key: int | None, label: str) -> None:
        if key is not None and await self._db.get(model, key) is None:
            raise InvalidArgument(f"unknown {label} {key}")

    async def list_locations(self) -> list[NamedRef]:
        rows = await self._db.execute(select(Location.id, Location.name).order_by(Location.name))
        return [NamedRef(id=i, name=n) for i, n in rows.all()]

    async def list_specialties(self) -> list[NamedRef]:
        rows = await self._db.execute(select(Specialty.id, Specialty.name).order_by(Specialty.name))
        return [NamedRef(id=i, name=n) for i, n in rows.all()]

    async def search_clinics(self, location_id: int | None, specialty_id: int | None) -> list[ClinicInfo]:
        await self._require(Location, location_id, "location_id")
        await self._require(Specialty, specialty_id, "specialty_id")
        query = select(Clinic.id, Clinic.name, Location.id, Location.name).join(Location, Location.id == Clinic.location_id)
        if location_id is not None:
            query = query.where(Clinic.location_id == location_id)
        if specialty_id is not None:
            query = query.where(
                exists().where(ClinicSpecialty.clinic_id == Clinic.id, ClinicSpecialty.specialty_id == specialty_id)
            )
        clinics = (await self._db.execute(query.order_by(Clinic.name, Clinic.id))).all()
        names = await self._db.execute(
            select(ClinicSpecialty.clinic_id, Specialty.name)
            .join(Specialty, Specialty.id == ClinicSpecialty.specialty_id)
            .where(ClinicSpecialty.clinic_id.in_([c[0] for c in clinics]))
            .order_by(Specialty.name)
        )
        by_clinic: dict[int, list[str]] = {}
        for clinic_id, name in names.all():
            by_clinic.setdefault(clinic_id, []).append(name)
        return [
            ClinicInfo(id=cid, name=cname, location_id=lid, location=lname, specialties=by_clinic.get(cid, []))
            for cid, cname, lid, lname in clinics
        ]

    async def search_doctors(self, clinic_id: int | None, location_id: int | None, specialty_id: int | None) -> list[DoctorInfo]:
        await self._require(Clinic, clinic_id, "clinic_id")
        await self._require(Location, location_id, "location_id")
        await self._require(Specialty, specialty_id, "specialty_id")
        query = (
            select(Doctor.id, Doctor.name, Specialty.id, Specialty.name, Clinic.id, Clinic.name, Location.name)
            .join(ClinicSpecialty, ClinicSpecialty.id == Doctor.clinic_specialty_id)
            .join(Clinic, Clinic.id == ClinicSpecialty.clinic_id)
            .join(Specialty, Specialty.id == ClinicSpecialty.specialty_id)
            .join(Location, Location.id == Clinic.location_id)
        )
        if clinic_id is not None:
            query = query.where(Clinic.id == clinic_id)
        if location_id is not None:
            query = query.where(Clinic.location_id == location_id)
        if specialty_id is not None:
            query = query.where(Specialty.id == specialty_id)
        rows = await self._db.execute(query.order_by(Doctor.name, Doctor.id))
        return [
            DoctorInfo(id=d, name=dn, specialty_id=s, specialty=sn, clinic_id=c, clinic=cn, location=ln)
            for d, dn, s, sn, c, cn, ln in rows.all()
        ]

    async def available_slots(self, doctor_id: int, from_date: date | None, to_date: date | None, limit: int) -> list[DoctorCard]:
        await self._require(Doctor, doctor_id, "doctor_id")
        query = _slot_card_query().where(
            Slot.doctor_id == doctor_id, Slot.status == SlotStatus.available, Slot.start_at > self._clock.now()
        )
        if from_date is not None:
            query = query.where(Slot.start_at >= _day_start(from_date))
        if to_date is not None:
            query = query.where(Slot.start_at < _day_start(to_date) + timedelta(days=1))
        rows = await self._db.execute(query.order_by(Slot.start_at, Slot.id).limit(limit))
        return [_doctor_card(r) for r in rows.all()]

    async def recommend_doctors(self, specialty_id: int, location_id: int | None, limit: int) -> list[DoctorCard]:
        await self._require(Specialty, specialty_id, "specialty_id")
        await self._require(Location, location_id, "location_id")
        wanted_location = location_id if location_id is not None else self._profile_location_id
        earliest_per_doctor = (
            select(Slot.id.label("slot_id"), Slot.start_at.label("start_at"), Clinic.location_id.label("location_id"))
            .join(Doctor, Doctor.id == Slot.doctor_id)
            .join(ClinicSpecialty, ClinicSpecialty.id == Doctor.clinic_specialty_id)
            .join(Clinic, Clinic.id == ClinicSpecialty.clinic_id)
            .where(
                ClinicSpecialty.specialty_id == specialty_id,
                Slot.status == SlotStatus.available,
                Slot.start_at > self._clock.now(),
            )
            .order_by(Doctor.id, Slot.start_at, Slot.id)
            .ext(distinct_on(Doctor.id))
            .subquery()
        )
        ranked = (
            _slot_card_query()
            .join(earliest_per_doctor, earliest_per_doctor.c.slot_id == Slot.id)
            .order_by(
                case((earliest_per_doctor.c.location_id == wanted_location, 0), else_=1),
                earliest_per_doctor.c.start_at,
                Slot.id,
            )
            .limit(limit)
        )
        return [_doctor_card(r) for r in (await self._db.execute(ranked)).all()]

    async def my_visits(self, status: VisitStatusName | None) -> list[VisitInfo]:
        query = _visit_query().where(Visit.profile_id == self._profile_id)
        if status is not None:
            query = query.where(Visit.status == VisitStatus(status))
        rows = await self._db.execute(query.order_by(Slot.start_at, Visit.id))
        return [VisitInfo(**_visit_card(r).model_dump(), status=r[5].value) for r in rows.all()]

    async def scheduled_visits(self, visit_id: int | None) -> list[VisitCard]:
        query = _visit_query().where(Visit.profile_id == self._profile_id, Visit.status == VisitStatus.scheduled)
        if visit_id is not None:
            query = query.where(Visit.id == visit_id)
        rows = await self._db.execute(query.order_by(Slot.start_at, Visit.id))
        return [_visit_card(r) for r in rows.all()]


class SqlComplaintsPort:
    def __init__(self, db: AsyncSession, profile_id: int) -> None:
        self._db = db
        self._profile_id = profile_id

    async def my_complaints(self) -> list[ComplaintInfo]:
        complaints = (
            await self._db.execute(
                select(Complaint.id, Complaint.visit_id, Complaint.description, Complaint.status)
                .join(Visit, Visit.id == Complaint.visit_id)
                .where(Visit.profile_id == self._profile_id)
                .order_by(Complaint.id)
            )
        ).all()
        replies = await self._db.execute(
            select(ComplaintReply.complaint_id, ComplaintReply.body)
            .where(ComplaintReply.complaint_id.in_([c[0] for c in complaints]))
            .order_by(ComplaintReply.id)
        )
        by_complaint: dict[int, list[str]] = {}
        for complaint_id, body in replies.all():
            by_complaint.setdefault(complaint_id, []).append(body)
        return [
            ComplaintInfo(id=cid, visit_id=vid, description=desc, status=status.value, replies=by_complaint.get(cid, []))
            for cid, vid, desc, status in complaints
        ]

    async def eligible_visits(self) -> list[VisitCard]:
        query = _visit_query().where(
            Visit.profile_id == self._profile_id,
            Visit.status == VisitStatus.completed,
            ~exists().where(Complaint.visit_id == Visit.id),
        )
        rows = await self._db.execute(query.order_by(Slot.start_at.desc(), Visit.id))
        return [_visit_card(r) for r in rows.all()]


def make_ports(db: AsyncSession, profile_id: int, profile_location_id: int, clock: Clock) -> Ports:
    return Ports(
        scheduling=SqlSchedulingPort(db, profile_id, profile_location_id, clock),
        complaints=SqlComplaintsPort(db, profile_id),
    )
