"""Репозиторий сессий диалога."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_trainer.repository.enums import Mode, SessionState
from ai_trainer.repository.models import Session


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self, user_id: int) -> Session | None:
        result = await self._session.execute(
            select(Session).where(
                Session.user_id == user_id,
                Session.ended_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        *,
        scenario_code: str | None = None,
        mode: Mode | None = None,
        state: SessionState = SessionState.idle,
    ) -> Session:
        dialog = Session(
            user_id=user_id,
            scenario_code=scenario_code,
            mode=mode,
            state=state,
            case_ids=[],
            case_index=0,
        )
        self._session.add(dialog)
        await self._session.flush()
        return dialog

    async def set_state(self, dialog: Session, state: SessionState) -> Session:
        dialog.state = state
        dialog.last_activity_at = datetime.now(UTC)
        await self._session.flush()
        return dialog

    async def set_mode(self, dialog: Session, *, scenario_code: str, mode: Mode) -> Session:
        dialog.scenario_code = scenario_code
        dialog.mode = mode
        dialog.last_activity_at = datetime.now(UTC)
        await self._session.flush()
        return dialog

    async def set_cases(self, dialog: Session, case_ids: list[int]) -> Session:
        dialog.case_ids = case_ids
        dialog.case_index = 0
        await self._session.flush()
        return dialog

    async def advance_case(self, dialog: Session) -> Session:
        dialog.case_index += 1
        dialog.last_activity_at = datetime.now(UTC)
        await self._session.flush()
        return dialog

    async def touch(self, dialog: Session) -> None:
        dialog.last_activity_at = datetime.now(UTC)
        await self._session.flush()

    async def end(self, dialog: Session) -> Session:
        dialog.ended_at = datetime.now(UTC)
        dialog.state = SessionState.idle
        await self._session.flush()
        return dialog
