import pytest


pytest.importorskip("testcontainers.postgres")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_and_read_diagnosis():
    from sqlalchemy import select
    from testcontainers.postgres import PostgresContainer

    from runbook_assistant.db import (
        Diagnosis,
        init_db,
        make_engine,
        make_session_factory,
        save_diagnosis,
    )

    # Pass credentials explicitly: testcontainers falls back to POSTGRES_*
    # env vars, and an empty POSTGRES_PASSWORD in the host shell would make the
    # container refuse to initialize.
    with PostgresContainer(
        "pgvector/pgvector:pg18", username="test", password="test", dbname="test"
    ) as pg:
        url = pg.get_connection_url().replace("psycopg2", "asyncpg")
        engine = make_engine(url)
        await init_db(engine)
        sf = make_session_factory(engine)
        did = await save_diagnosis(
            sf,
            question="why OOM?",
            answer="raise memory limit",
            service="checkout",
            duration_ms=1234,
            trace_id="abc123",
        )
        assert did
        async with sf() as s:
            row = (await s.execute(select(Diagnosis).where(Diagnosis.id == did))).scalar_one()
            assert row.service == "checkout" and row.duration_ms == 1234
        await engine.dispose()
