"""Tests for job/step helpers and resume state machine."""
import pytest

from sable.platform.jobs import (
    create_job,
    add_step,
    start_step,
    complete_step,
    fail_step,
    get_resumable_steps,
    resume_job,
)
from sable.platform.errors import SableError, MAX_RETRIES_EXCEEDED


def test_create_job(org_conn):
    job_id = create_job(org_conn, "testorg", "playbook")
    row = org_conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    assert row["status"] == "pending"
    assert row["job_type"] == "playbook"


def test_add_and_complete_step(org_conn):
    job_id = create_job(org_conn, "testorg", "playbook")
    step_id = add_step(org_conn, job_id, "fetch_data", step_order=0)
    start_step(org_conn, step_id)
    complete_step(org_conn, step_id, output={"result": "ok"})
    row = org_conn.execute("SELECT status FROM job_steps WHERE step_id=?", (step_id,)).fetchone()
    assert row["status"] == "completed"


def test_fail_step_increments_retries(org_conn):
    job_id = create_job(org_conn, "testorg", "playbook")
    step_id = add_step(org_conn, job_id, "risky_step", step_order=0)
    fail_step(org_conn, step_id, error="timeout")
    row = org_conn.execute("SELECT retries, error FROM job_steps WHERE step_id=?", (step_id,)).fetchone()
    assert row["retries"] == 1
    assert row["error"] == "timeout"
    fail_step(org_conn, step_id)
    row = org_conn.execute("SELECT retries FROM job_steps WHERE step_id=?", (step_id,)).fetchone()
    assert row["retries"] == 2


def test_resume_skip_completed(org_conn):
    job_id = create_job(org_conn, "testorg", "playbook")
    step_id = add_step(org_conn, job_id, "done_step", step_order=0)
    complete_step(org_conn, step_id)
    actions = resume_job(org_conn, job_id)
    assert actions[0]["action"] == "skip"


def test_resume_retry_failed(org_conn):
    job_id = create_job(org_conn, "testorg", "playbook")
    step_id = add_step(org_conn, job_id, "fail_step", step_order=0)
    fail_step(org_conn, step_id)
    actions = resume_job(org_conn, job_id, max_retries=2)
    assert actions[0]["action"] == "retry"
    row = org_conn.execute("SELECT status FROM job_steps WHERE step_id=?", (step_id,)).fetchone()
    assert row["status"] == "pending"


def test_resume_max_retries_exceeded(org_conn):
    job_id = create_job(org_conn, "testorg", "playbook")
    step_id = add_step(org_conn, job_id, "exhausted_step", step_order=0)
    fail_step(org_conn, step_id)
    fail_step(org_conn, step_id)  # retries = 2
    with pytest.raises(SableError) as exc:
        resume_job(org_conn, job_id, max_retries=2)
    assert exc.value.code == MAX_RETRIES_EXCEEDED


def test_resume_wait_awaiting_input(org_conn):
    job_id = create_job(org_conn, "testorg", "playbook")
    step_id = add_step(org_conn, job_id, "waiting_step", step_order=0)
    org_conn.execute(
        "UPDATE job_steps SET status='awaiting_input' WHERE step_id=?", (step_id,)
    )
    org_conn.commit()
    actions = resume_job(org_conn, job_id)
    assert actions[0]["action"] == "wait"


def test_resume_run_pending(org_conn):
    job_id = create_job(org_conn, "testorg", "playbook")
    step_id = add_step(org_conn, job_id, "pending_step", step_order=0)
    actions = resume_job(org_conn, job_id)
    assert actions[0]["action"] == "run"
    row = org_conn.execute("SELECT status FROM job_steps WHERE step_id=?", (step_id,)).fetchone()
    assert row["status"] == "running"


def test_resume_steps_ordered(org_conn):
    job_id = create_job(org_conn, "testorg", "playbook")
    s2 = add_step(org_conn, job_id, "second", step_order=1)
    s1 = add_step(org_conn, job_id, "first", step_order=0)
    complete_step(org_conn, s1)
    complete_step(org_conn, s2)
    actions = resume_job(org_conn, job_id)
    assert actions[0]["step_name"] == "first"
    assert actions[1]["step_name"] == "second"
