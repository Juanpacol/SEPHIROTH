"""PHI-access audit logging — a single helper called from each existing
read site that touches a patient's chart (patients.py, portal.py,
results.py). Deliberately not derived from the generic per-request
`request_logging` middleware in `api/main.py`: an ASGI middleware sees the
path and method but not which `patient_id` a handler resolved, so the
call has to happen inside the handler, right after it knows."""

from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import PhiAccessLog, User


async def log_phi_access(session: AsyncSession, user: User, patient_id: str, route: str, method: str) -> None:
    session.add(PhiAccessLog(user_id=user.id, patient_id=patient_id, route=route, method=method))
    await session.commit()
