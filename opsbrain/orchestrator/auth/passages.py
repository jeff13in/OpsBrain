"""Read-only, tenant-scoped retrieved passages. No path or URL resolution."""
import re
import time
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from orchestrator.auth.routes import Boundary
from orchestrator.auth.sessions import (
    InvalidIdentity,
    ProviderUnavailable,
    WorkspaceUnavailable,
)

SOURCE_ID = re.compile(r"^src_[a-f0-9]{64}$")


class Passage(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source_id: Annotated[str, Field(pattern=r'^src_[a-f0-9]{64}$')]
    available: bool
    provenance: Literal['retrieved']
    passage: Annotated[str, Field(min_length=1, max_length=8000)] | None = None
    revision: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    observed_at: Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')] | None = None


class PassageRepository(Protocol):
    def lookup(self, user_id: str, workspace_id: str, investigation_id: str, source_id: str):
        """Return the CURRENT approved retrieval record, or None; never accept paths."""


@dataclass(frozen=True)
class RetrievedPassage:
    user_id: str
    workspace_id: str
    investigation_id: str
    source_id: str
    passage: str
    expires_at: int
    approved: bool = False
    revision: str | None = None
    observed_at: str | None = None


class PassageResolver:
    def __init__(self, repository: PassageRepository, *, clock=time.time):
        self.repository = repository
        self.clock = clock

    def resolve(self, user_id, workspace_id, investigation_id, source_id):
        # Validate identifiers before touching the repository. No label, path or URL
        # can select a file, network target, or another tenant's retrieval.
        if not isinstance(source_id, str) or not SOURCE_ID.fullmatch(source_id):
            raise ValueError('Invalid source identifier')
        for value in (user_id, workspace_id, investigation_id):
            if str(UUID(value)) != value:
                raise ValueError('Invalid scope identifier')
        row = self.repository.lookup(user_id, workspace_id, investigation_id, source_id)
        unavailable = Passage(source_id=source_id, available=False, provenance='retrieved')
        if row is None:
            return unavailable
        if not isinstance(row, RetrievedPassage):
            raise TypeError('Invalid passage record')
        if (row.user_id, row.workspace_id, row.investigation_id, row.source_id) != (
            user_id, workspace_id, investigation_id, source_id
        ):
            return unavailable
        if row.approved is not True or type(row.expires_at) is not int or row.expires_at <= self.clock():
            return unavailable
        if not isinstance(row.passage, str) or not row.passage.strip():
            raise ValueError('Invalid passage')
        if row.observed_at is not None:
            from datetime import datetime
            datetime.strptime(row.observed_at, '%Y-%m-%dT%H:%M:%SZ')
        return Passage(source_id=source_id, available=True, provenance='retrieved',
                       passage=row.passage, revision=row.revision, observed_at=row.observed_at)


def get_passage_resolver():
    # Deliberate deployment gate: no shared RAG DB, local manifest or memory
    # fallback. Install a tenant-aware adapter only after hosted isolation proof.
    raise HTTPException(503, 'Passage access unavailable')


router = APIRouter()


@router.get('/api/workspaces/{workspace_id}/investigations/{investigation_id}/sources/{source_id}')
def passage(workspace_id: UUID, investigation_id: UUID, source_id: str,
            request: Request, boundary: Boundary):
    if not SOURCE_ID.fullmatch(source_id) or request.query_params:
        raise HTTPException(422, 'Invalid passage request')
    settings, manager = boundary
    def resolve(access, user_id, approved_workspace):
        # Auth and locked session checks run BEFORE this deployment gate/repository.
        return get_passage_resolver().resolve(user_id, approved_workspace, str(investigation_id), source_id)
    try:
        result = manager.authorized_action(request.cookies.get(settings.cookie_name), str(workspace_id), resolve)
    except InvalidIdentity:
        raise HTTPException(401, 'Authentication required') from None
    except WorkspaceUnavailable:
        raise HTTPException(404, 'Passage unavailable') from None
    except (TypeError, ValueError, ProviderUnavailable):
        raise HTTPException(503, 'Passage access unavailable') from None
    return JSONResponse(result.model_dump(), headers={'Cache-Control': 'no-store'})
