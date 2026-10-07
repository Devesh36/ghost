"""Composition of persistence, repository state, and optional model providers."""
from pathlib import Path
from bootstrap.providers import load_provider
from core.domain.types import Session, Event, EventType
from infrastructure.database.repository import Database
from infrastructure.repository.git import state


def session_for(db: Database, repo: Path) -> Session:
    session = db.latest_session()
    if session is None or session.ended_at:
        git_state = state(repo, include_diff=False)
        session = Session(repository_path=str(repo), starting_commit=git_state["head"], branch=git_state["branch"])
        db.start(session)
        db.add_event(Event(session_id=session.id, event_type=EventType.GIT_STATE,
                           metadata={"status": git_state["status"][:4000], "head": git_state["head"]}))
    return session


def model_provider(repo: Path | None = None):
    try:
        return load_provider(repo)
    except ValueError:
        return None
