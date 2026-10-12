"""Bounded user-scoped persistence routes; mutations require Origin and CSRF."""

import hmac
import json
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from orchestrator.auth.routes import Boundary
from orchestrator.auth.sessions import (
    InvalidIdentity,
    PersistenceError,
    ProviderUnavailable,
    WorkspaceUnavailable,
)

router = APIRouter()
TextSource = Annotated[str, Field(strict=True, max_length=2000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class SavedError(StrictModel):
    code: Annotated[str, Field(max_length=100)]
    message: TextSource


class SavedResult(StrictModel):
    agent: Literal['rag', 'monitoring', 'infra', 'code']
    status: Literal['ok', 'error', 'timeout']
    answer: Annotated[str, Field(max_length=20000)] | None
    sources: Annotated[list[TextSource], Field(max_length=20)]
    error: SavedError | None


class SavedResponse(StrictModel):
    status: Literal['ok', 'partial', 'error']
    answer: Annotated[str, Field(max_length=20000)]
    sources: Annotated[list[TextSource], Field(max_length=20)]
    results: Annotated[list[SavedResult], Field(max_length=4)]


class SavedTurn(StrictModel):
    question: Annotated[str, Field(min_length=5, max_length=2000)]
    response: SavedResponse

    @field_validator('question')
    @classmethod
    def meaningful_question(cls,value):
        if len(value.strip())<5:
            raise ValueError('Question too short')
        return value


class SavedPayload(StrictModel):
    mode: Literal['demo']
    turns: Annotated[list[SavedTurn], Field(min_length=1, max_length=20)]


class Preferences(StrictModel):
    default_section: Literal['dashboard', 'projects', 'tools']
    reduced_motion: bool


class ProfileChange(StrictModel):
    display_name: Annotated[str, Field(max_length=120)]
    preferences: Preferences


class ProjectChange(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]


class SavedCreate(ProjectChange):
    project_id: UUID
    payload: SavedPayload


class SavedChange(ProjectChange):
    payload: SavedPayload


class Command(StrictModel):
    request_id: UUID
    operation: Literal['project.create', 'project.update', 'project.delete', 'saved.create', 'saved.update', 'saved.delete', 'profile.update']
    record_id: UUID | None = None
    expected_version: Annotated[int, Field(ge=0, le=9007199254740991)]
    changes: dict


def safe_error(status):
    return HTTPException(status, {401: 'Authentication required', 403: 'Request denied', 404: 'Record unavailable',
                                 409: 'Record changed or retry payload differs', 422: 'Invalid record fields',
                                 429: 'Workspace storage limit reached'}.get(status, 'Persistence unavailable'),
                         headers={'Cache-Control': 'no-store'})


def call(boundary, request, workspace_id, action, *args):
    settings, manager = boundary
    try:
        return manager.workspace_action(request.cookies.get(settings.cookie_name), str(workspace_id), action, *args)
    except InvalidIdentity:
        raise safe_error(401) from None
    except WorkspaceUnavailable:
        raise safe_error(404) from None
    except PersistenceError as exc:
        raise safe_error(exc.status) from None
    except (ValueError, psycopg.Error, ProviderUnavailable):
        raise safe_error(503) from None


@router.get('/api/workspaces/{workspace_id}/records/{kind}')
def list_records(workspace_id: UUID, kind: Literal['projects', 'saved_work'], request: Request, boundary: Boundary,
                 cursor: UUID | None = None, limit: Annotated[int, Query(ge=1, le=20)] = 20):
    return JSONResponse(call(boundary, request, workspace_id, 'list_records', kind, str(cursor) if cursor else None, limit), headers={'Cache-Control': 'no-store'})


@router.get('/api/workspaces/{workspace_id}/records/{kind}/{record_id}')
def read_record(workspace_id: UUID, kind: Literal['projects', 'saved_work'], record_id: UUID, request: Request, boundary: Boundary):
    return JSONResponse(call(boundary, request, workspace_id, 'read_record', kind, str(record_id)), headers={'Cache-Control': 'no-store'})


@router.post('/api/workspaces/{workspace_id}/mutations')
async def mutate(workspace_id: UUID, request: Request, boundary: Boundary):
    settings, manager = boundary
    cookie = request.cookies.get(settings.cookie_name)
    if request.headers.get('origin') != settings.app_origin.rstrip('/'):
        raise safe_error(403)
    try:
        expected = manager.csrf_token(cookie)
    except InvalidIdentity:
        raise safe_error(401) from None
    token = request.headers.get('x-csrf-token', '')
    if not token.isascii() or not hmac.compare_digest(token, expected):
        raise safe_error(403)
    raw = bytearray()
    async for part in request.stream():
        raw.extend(part)
        if len(raw) > 150000:
            raise safe_error(422)
    try:
        command = Command.model_validate_json(bytes(raw))
        operation = command.operation
        if operation.endswith('.delete'):
            if command.changes:
                raise ValueError()
            changes = {}
        else:
            model = ProfileChange if operation == 'profile.update' else SavedCreate if operation == 'saved.create' else SavedChange if operation == 'saved.update' else ProjectChange
            changes = model.model_validate_json(json.dumps(command.changes)).model_dump(mode='json')
        if operation.endswith('.create') != (command.expected_version == 0):
            raise ValueError()
        if operation != 'profile.update' and command.record_id is None:
            raise ValueError()
        if operation == 'profile.update' and command.record_id is not None:
            raise ValueError()
    except (ValidationError, ValueError):
        raise safe_error(422) from None
    result = await run_in_threadpool(call, boundary, request, workspace_id, 'mutate', str(command.request_id), operation,
                                    str(command.record_id) if command.record_id else None, command.expected_version, changes)
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})
