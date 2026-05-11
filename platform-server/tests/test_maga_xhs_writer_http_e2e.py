"""End-to-end smoke: MAGA /generation/start calls the real maga-worker /invoke skeleton over HTTP."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.content_agent import router
from app.core.database import get_db
from app.models.base import Base
from app.models.content_agent import ContentAgentStageCall, ExecutorRegistry
from app.models.maga_core import MAGA_CORE_TABLE_NAMES

MAGA_WORKER_WORKSPACE = Path("/Users/luxifa/.hermes/profiles/maga-worker/workspace")
PYTHON = Path("/Users/luxifa/maga/.venv/bin/python")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(port: int, process: subprocess.Popen, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise RuntimeError(f"maga-worker server exited early\nstdout={stdout}\nstderr={stderr}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("maga-worker server did not become ready")


@pytest.fixture
def maga_worker_server():
    port = _free_port()
    env = os.environ.copy()
    env["MAGA_WORKER_EXECUTOR_TOKEN"] = "test-token"
    process = subprocess.Popen(
        [
            str(PYTHON),
            "-m",
            "uvicorn",
            "tools.maga_executor_server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(MAGA_WORKER_WORKSPACE),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_health(port, process)
        yield f"http://127.0.0.1:{port}/invoke"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest_asyncio.fixture
async def maga_http_e2e_client(maga_worker_server):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="hermes_maga_worker",
                executor_type="hermes_profile",
                invoke_url=maga_worker_server,
                config_json={"executor_token": "test-token"},
                supported_capabilities_json=[
                    {"capability": "xhs.interpret_brief", "schema_version": "1"},
                    {"capability": "xhs.run_ae_analysis", "schema_version": "1"},
                    {"capability": "xhs.generate_draft", "schema_version": "1"},
                    {"capability": "xhs.run_ae_review", "schema_version": "1"},
                    {"capability": "xhs.rewrite_draft", "schema_version": "1"},
                ],
            )
        )
        await session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/content-agent")

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_generation_start_calls_maga_worker_invoke_skeleton_over_http(maga_http_e2e_client):
    client, session_factory = maga_http_e2e_client

    response = await client.post(
        "/api/v1/content-agent/generation/start",
        json={
            "product_topic": "美素佳儿源悦",
            "target_audience": "新手妈妈",
            "style": "情绪共情",
            "executor_code": "hermes_maga_worker",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert "美素佳儿源悦" in data["title"]
    assert "新手妈妈" in data["body"]

    async with session_factory() as session:
        result = await session.execute(select(ContentAgentStageCall).order_by(ContentAgentStageCall.sequence_no))
        stages = list(result.scalars())

    assert [stage.capability for stage in stages] == [
        "xhs.interpret_brief",
        "xhs.run_ae_analysis",
        "xhs.generate_draft",
        "xhs.run_ae_review",
    ]
    assert all(stage.status == "succeeded" for stage in stages)
    assert all((stage.stats_json or {}).get("executor") == "maga-worker" for stage in stages)
    assert all((stage.stats_json or {}).get("module") == "xhs-writer" for stage in stages)
