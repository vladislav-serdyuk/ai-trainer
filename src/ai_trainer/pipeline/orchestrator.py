# Copyright (C) 2026 AI Trainer contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Оркестратор: жизненный цикл сессии и диспетчер режимов (см. architecture.md §5.2)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ai_trainer.agent.agent import Agent
from ai_trainer.agent.client import LLMClient, LLMError, Message
from ai_trainer.config import Settings, get_settings
from ai_trainer.pipeline import format as fmt
from ai_trainer.pipeline.context import Button, Reply, inline
from ai_trainer.pipeline.states import (
    MENU_CB,
    mode_cb,
    scenario_cb,
)
from ai_trainer.rag.embeddings import Embedder
from ai_trainer.rag.rerank import Reranker
from ai_trainer.repository.enums import ContentType, MessageRole, Mode, SessionState
from ai_trainer.repository.models import Session, User
from ai_trainer.repository.repos.answers import CaseAnswerRepository
from ai_trainer.repository.repos.cases import CaseRepository
from ai_trainer.repository.repos.catalog import MistakeRepository, ScenarioRepository
from ai_trainer.repository.repos.messages import MessageRepository
from ai_trainer.repository.repos.sessions import SessionRepository
from ai_trainer.repository.repos.users import UserRepository
from ai_trainer.repository.session import session_scope
from ai_trainer.stt.transcribe import get_transcriber

logger = logging.getLogger(__name__)

_HISTORY_LIMIT = 6

_USER_LOCKS: dict[int, asyncio.Lock] = {}


def _user_lock(user_id: int) -> asyncio.Lock:
    """Сериализация входящих событий одного пользователя (гейт в оркестраторе)."""

    lock = _USER_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _USER_LOCKS[user_id] = lock
    return lock


class Orchestrator:
    def __init__(
        self,
        *,
        llm: LLMClient | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        search_provider: Any = None,
        transcriber: Any = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._llm = llm
        self._embedder = embedder
        self._reranker = reranker
        self._search_provider = search_provider
        self._transcriber = transcriber

    # -- helpers -----------------------------------------------------------

    def _agent(self, session: AsyncSession) -> Agent:
        return Agent(
            session,
            llm=self._llm,
            embedder=self._embedder,
            reranker=self._reranker,
            search_provider=self._search_provider,
            settings=self._settings,
        )

    async def _menu_reply(self, session: AsyncSession, user: User) -> Reply:
        session_repo = SessionRepository(session)
        active = await session_repo.get_active(user.id)
        if active is not None:
            await session_repo.end(active)

        scenarios = await ScenarioRepository(session).list_all()
        if not scenarios:
            return Reply("База знаний ещё не наполнена — нет сценариев.")
        buttons = [Button(s.title, scenario_cb(s.code)) for s in scenarios]
        return Reply(fmt.menu_text(), inline(*buttons))

    @staticmethod
    def _history(messages: list[Any]) -> list[Message]:
        result: list[Message] = []
        for message in messages:
            if message.role in (MessageRole.user, MessageRole.assistant):
                result.append({"role": message.role.value, "content": message.content})
        return result[-_HISTORY_LIMIT:]

    async def _ensure_session(self, session_repo: SessionRepository, user_id: int) -> Session:
        active = await session_repo.get_active(user_id)
        if active is None:
            active = await session_repo.create(user_id, state=SessionState.choose_scenario)
        return active

    # -- entrypoints -------------------------------------------------------

    async def handle_start(self, user_id: int) -> Reply:
        async with _user_lock(user_id):
            async with session_scope() as session:
                users = UserRepository(session)
                user = await users.get_or_create(user_id)
                return await self._menu_reply(session, user)

    async def handle_consent(self, user_id: int) -> Reply:
        async with _user_lock(user_id):
            async with session_scope() as session:
                users = UserRepository(session)
                user = await users.get_or_create(user_id)
                if user.consent_at is None:
                    await users.set_consent(user)
                return await self._menu_reply(session, user)

    async def handle_menu(self, user_id: int) -> Reply:
        async with _user_lock(user_id):
            async with session_scope() as session:
                users = UserRepository(session)
                user = await users.get_or_create(user_id)
                return await self._menu_reply(session, user)

    async def handle_help(self, user_id: int) -> Reply:
        async with _user_lock(user_id):
            return Reply(fmt.help_text())

    async def handle_scenario(self, user_id: int, scenario_code: str) -> Reply:
        async with _user_lock(user_id):
            async with session_scope() as session:
                users = UserRepository(session)
                user = await users.get_or_create(user_id)

                scenario = await ScenarioRepository(session).get(scenario_code)
                if scenario is None:
                    return await self._menu_reply(session, user)

                session_repo = SessionRepository(session)
                active = await self._ensure_session(session_repo, user.id)
                active.scenario_code = scenario.code
                await session_repo.set_state(active, SessionState.choose_mode)

                buttons = [
                    Button("Справочник", mode_cb(Mode.informational.value)),
                    Button("Тренажёр", mode_cb(Mode.trainer.value)),
                ]
                return Reply(fmt.scenario_text(scenario), inline(*buttons))

    async def handle_mode(self, user_id: int, mode_value: str) -> Reply:
        try:
            mode = Mode(mode_value)
        except ValueError:
            mode = Mode.informational

        async with _user_lock(user_id):
            async with session_scope() as session:
                users = UserRepository(session)
                user = await users.get_or_create(user_id)

                session_repo = SessionRepository(session)
                active = await self._ensure_session(session_repo, user.id)
                scenario_code = active.scenario_code
                if scenario_code is None:
                    return await self._menu_reply(session, user)

                scenario = await ScenarioRepository(session).get(scenario_code)
                title = scenario.title if scenario else None
                await session_repo.set_mode(active, scenario_code=scenario_code, mode=mode)

                if mode is Mode.informational:
                    await session_repo.set_state(active, SessionState.qa_loop)
                    return Reply(fmt.info_mode_text(title))

                return await self._start_trainer(session, active, title)

    async def handle_stop(self, user_id: int) -> Reply:
        async with _user_lock(user_id):
            async with session_scope() as session:
                users = UserRepository(session)
                user = await users.get_or_create(user_id)
                return await self._menu_reply(session, user)

    async def handle_delete(self, user_id: int) -> Reply:
        async with _user_lock(user_id):
            async with session_scope() as session:
                users = UserRepository(session)
                user = await users.get_or_create(user_id)
                await users.purge(user)
                return Reply(
                    "Твои данные удалены. Если захочешь продолжить — "
                    "нажми /start и согласись заново."
                )

    async def handle_voice(self, user_id: int, audio: bytes) -> Reply:
        async with _user_lock(user_id):
            transcriber = self._transcriber or get_transcriber()
            try:
                text = await asyncio.to_thread(transcriber.transcribe, audio)
            except Exception:
                logger.exception("STT failed")
                return Reply("Не получилось распознать голос. Напиши текстом.")
            text = text.strip()
            if not text:
                return Reply("Не расслышал. Повтори, пожалуйста, или напиши текстом.")
            return await self._handle_text(user_id, text, content_type=ContentType.voice)

    async def handle_text(
        self, user_id: int, text: str, *, content_type: ContentType = ContentType.text
    ) -> Reply:
        async with _user_lock(user_id):
            return await self._handle_text(user_id, text, content_type=content_type)

    async def _handle_text(
        self, user_id: int, text: str, *, content_type: ContentType = ContentType.text
    ) -> Reply:
        async with session_scope() as session:
            users = UserRepository(session)
            user = await users.get_or_create(user_id)

            session_repo = SessionRepository(session)
            active = await session_repo.get_active(user.id)
            if active is None:
                reply = await self._menu_reply(session, user)
                reply.text = "Сначала выбери сценарий.\n\n" + reply.text
                return reply

            if active.state is SessionState.qa_loop:
                return await self._qa(session, active, text, content_type)
            if active.state is SessionState.case_loop:
                return await self._case(session, active, text, content_type)

            reply = await self._menu_reply(session, user)
            reply.text = "Выбери сценарий и режим.\n\n" + reply.text
            return reply

    # -- trainer -----------------------------------------------------------

    async def _start_trainer(
        self, session: AsyncSession, active: Session, title: str | None
    ) -> Reply:
        assert active.scenario_code is not None
        cases = await CaseRepository(session).list_by_scenario(active.scenario_code)
        if not cases:
            await SessionRepository(session).end(active)
            return Reply(
                "Для этого сценария ещё нет кейсов. Выбери другой.",
                inline(Button("Меню", MENU_CB)),
            )

        maximum = self._settings.trainer_cases_max
        count = min(maximum, len(cases))
        selected = cases[:count]

        session_repo = SessionRepository(session)
        await session_repo.set_cases(active, [c.id for c in selected])
        await session_repo.set_state(active, SessionState.case_loop)

        first = selected[0]
        intro = fmt.trainer_mode_text(title, count)
        return Reply(
            f"{intro}\n\n{fmt.case_prompt_text(first, 0, count)}",
            inline(Button("Меню", MENU_CB)),
        )

    async def _case(
        self, session: AsyncSession, active: Session, text: str, content_type: ContentType
    ) -> Reply:
        session_repo = SessionRepository(session)
        case_repo = CaseRepository(session)
        message_repo = MessageRepository(session)
        answer_repo = CaseAnswerRepository(session)

        total = len(active.case_ids)
        index = active.case_index
        if index >= total:
            return await self._finish(session, active)

        case = await case_repo.get_by_id(active.case_ids[index])
        if case is None:
            await session_repo.end(active)
            return Reply(fmt.unknown_state_text())

        scenario = await ScenarioRepository(session).get(active.scenario_code or "")
        title = scenario.title if scenario else None

        history = self._history(await message_repo.list_by_session(active.id))
        try:
            evaluation = await self._agent(session).evaluate_answer(
                case,
                text,
                scenario_title=title,
                scenario_code=active.scenario_code,
                history=history,
            )
        except LLMError:
            logger.exception("LLM evaluation failed")
            return Reply(fmt.error_text(), inline(Button("Меню", MENU_CB)))

        mistake_objs = await MistakeRepository(session).get_codes(evaluation.detected_mistakes)
        mistake_descs = [m.description for m in mistake_objs]
        feedback = fmt.feedback_text(
            evaluation, case, index, total, mistake_descriptions=mistake_descs
        )
        await answer_repo.add(
            session_id=active.id,
            case_id=case.id,
            user_answer=text,
            verdict=evaluation.verdict,
            score=evaluation.score,
            what_to_improve=evaluation.what_to_improve,
            example_answer=evaluation.example_answer,
            detected_mistakes=evaluation.detected_mistakes,
            citations=[c.model_dump() for c in evaluation.citations],
        )
        await message_repo.add(
            active.id, role=MessageRole.user, content=text, content_type=content_type
        )
        await message_repo.add(
            active.id,
            role=MessageRole.assistant,
            content=feedback,
            citations=[c.model_dump() for c in evaluation.citations],
        )
        await session_repo.advance_case(active)

        next_index = active.case_index
        if next_index < total:
            next_case = await case_repo.get_by_id(active.case_ids[next_index])
            if next_case is not None:
                return Reply(
                    f"{feedback}\n\n{fmt.case_prompt_text(next_case, next_index, total)}",
                    inline(Button("Меню", MENU_CB)),
                )
        finish = await self._finish(session, active)
        finish.text = f"{feedback}\n\n{finish.text}"
        return finish

    async def _finish(self, session: AsyncSession, active: Session) -> Reply:
        answer_repo = CaseAnswerRepository(session)
        message_repo = MessageRepository(session)
        scenario = await ScenarioRepository(session).get(active.scenario_code or "")
        title = scenario.title if scenario else None

        answers = await answer_repo.list_by_session(active.id)
        history = self._history(await message_repo.list_by_session(active.id))
        try:
            summary = await self._agent(session).summarize(
                answers, scenario_title=title, history=history
            )
        except LLMError:
            logger.exception("LLM summary failed")
            summary = "Отличная тренировка! Посмотри разборы выше и попробуй ещё раз."

        await SessionRepository(session).end(active)
        return Reply(fmt.summary_text(summary, answers), inline(Button("Меню", MENU_CB)))

    # -- informational -----------------------------------------------------

    async def _qa(
        self, session: AsyncSession, active: Session, text: str, content_type: ContentType
    ) -> Reply:
        message_repo = MessageRepository(session)
        scenario = await ScenarioRepository(session).get(active.scenario_code or "")
        title = scenario.title if scenario else None

        history = self._history(await message_repo.list_by_session(active.id))
        try:
            answer = await self._agent(session).answer_info(
                text,
                scenario_title=title,
                scenario_code=active.scenario_code,
                history=history,
            )
        except LLMError:
            logger.exception("LLM info answer failed")
            await message_repo.add(
                active.id, role=MessageRole.user, content=text, content_type=content_type
            )
            return Reply(fmt.error_text(), inline(Button("Меню", MENU_CB)))

        citations = [c.model_dump() for c in answer.citations]
        await message_repo.add(
            active.id, role=MessageRole.user, content=text, content_type=content_type
        )
        await message_repo.add(
            active.id, role=MessageRole.assistant, content=answer.answer, citations=citations
        )
        await SessionRepository(session).touch(active)
        return Reply(fmt.info_reply_text(answer), inline(Button("Меню", MENU_CB)))
