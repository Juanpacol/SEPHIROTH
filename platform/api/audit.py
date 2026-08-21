"""PHI-access audit logging — a single helper called from each existing
read site that touches a patient's chart (patients.py, portal.py,
results.py). Deliberately not derived from the generic per-request
`request_logging` middleware in `api/main.py`: an ASGI middleware sees the
path and method but not which `patient_id` a handler resolved, so the
call has to happen inside the handler, right after it knows.

`add_phi_access` is the non-committing half, used by the workflow tick
(`platform/api/workflows/engine.py`) so a step's audit row shares the
step's own transaction instead of being split from it by an inline
commit -- see SPEC-009 §E. `log_phi_access` (the request-path entry
point, unchanged in behavior) delegates to it.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import PhiAccessLog, User


def add_phi_access(session: AsyncSession, user_id: str, patient_id: str, route: str, method: str) -> None:
    session.add(PhiAccessLog(user_id=user_id, patient_id=patient_id, route=route, method=method))


async def log_phi_access(session: AsyncSession, user: User, patient_id: str, route: str, method: str) -> None:
    add_phi_access(session, user.id, patient_id, route, method)
    await session.commit()
