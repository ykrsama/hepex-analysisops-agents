"""
End-to-End Integration Test: Green Agent (Judge) ↔ White Agent (Solver) for H→bb.

This test mirrors tests/test_e2e_green_white.py but uses the HBB benchmark spec.

Prerequisites:
- White agent server MUST be running on port 9009 before running this test.

Usage:
    pytest tests/test_e2e_green_white_hbb.py -v -s

    # Or run as standalone script:
    python tests/test_e2e_green_white_hbb.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import yaml

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest, SendStreamingMessageRequest


WHITE_AGENT_PORT = 9009
GREEN_AGENT_PORT = 9011
BENCHMARK_DIR = Path(__file__).parent.parent.parent / "hepex-analysisops-benchmark"
DATA_DIR = Path(__file__).parent.parent.parent / "data"
TASK_NAME = "hbb"
TASK_ID = "t003_hbb"
SKIM = "2bjets"
RELEASE = "2025e-13tev-beta"
DATASET = "data"


@pytest.fixture(scope="module")
def white_agent_url():
    """Check that white agent is running and return its URL."""
    url = f"http://127.0.0.1:{WHITE_AGENT_PORT}"

    try:
        response = httpx.get(f"{url}/.well-known/agent-card.json", timeout=5)
        if response.status_code != 200:
            pytest.skip(f"White agent at {url} returned status {response.status_code}")
    except Exception as e:
        pytest.skip(f"White agent not running at {url}: {e}. Start it with: cd src && python server.py --port 9009")

    return url


@pytest.fixture(scope="module")
def green_server_with_white_agent(tmp_path_factory, white_agent_url):
    """Start a green agent server configured to call the white agent for the HBB task."""
    if not BENCHMARK_DIR.exists():
        pytest.skip(f"Benchmark directory not found: {BENCHMARK_DIR}")

    benchmark_spec = BENCHMARK_DIR / "specs" / TASK_NAME
    if not benchmark_spec.exists():
        pytest.skip(f"Benchmark spec not found: {benchmark_spec}")

    tmpdir = tmp_path_factory.mktemp("e2e_green_server_hbb")
    data_dir = tmpdir / "atlas_cache"
    data_dir.mkdir(parents=True, exist_ok=True)

    source_data = DATA_DIR / RELEASE / DATASET / SKIM
    if source_data.exists():
        dest_data = data_dir / RELEASE / DATASET / SKIM
        dest_data.mkdir(parents=True, exist_ok=True)
        for root_file in source_data.glob("*.root"):
            shutil.copy(root_file, dest_data / root_file.name)

    spec_dir = tmpdir / "specs" / TASK_NAME
    spec_dir.mkdir(parents=True, exist_ok=True)

    for spec_file in ["task_spec.yaml", "rubric.yaml", "eval_ref.yaml", "white_prompt.md", "judge_prompt.md"]:
        src = benchmark_spec / spec_file
        if src.exists():
            shutil.copy(src, spec_dir / spec_file)

    task_spec = yaml.safe_load((spec_dir / "task_spec.yaml").read_text())
    task_spec["mode"] = "call_white"
    (spec_dir / "task_spec.yaml").write_text(yaml.dump(task_spec, sort_keys=False))

    env = os.environ.copy()
    env["HEPEX_DATA_DIR"] = str(data_dir)
    env["PYTHONPATH"] = str(BENCHMARK_DIR / "src")

    host = "127.0.0.1"
    port = GREEN_AGENT_PORT
    cmd = [
        sys.executable,
        str(BENCHMARK_DIR / "src" / "server.py"),
        "--host", host,
        "--port", str(port),
    ]

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(BENCHMARK_DIR),
    )

    base_url = f"http://{host}:{port}"
    ready = False
    for _ in range(50):
        try:
            with httpx.Client(timeout=1.0) as client:
                resp = client.get(f"{base_url}/.well-known/agent-card.json")
                if resp.status_code == 200:
                    ready = True
                    break
        except Exception:
            pass
        time.sleep(0.1)

    if not ready:
        proc.kill()
        stdout, stderr = proc.communicate()
        print("Green server stdout:", stdout.decode())
        print("Green server stderr:", stderr.decode())
        raise RuntimeError("Green agent server failed to start")

    yield {
        "base_url": base_url,
        "data_dir": data_dir,
        "spec_dir": spec_dir,
        "white_agent_url": white_agent_url,
    }

    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.asyncio
async def test_e2e_green_calls_white_for_hbb(green_server_with_white_agent):
    """Full E2E test for the HBB benchmark task."""
    server_info = green_server_with_white_agent
    green_url = server_info["base_url"]
    white_url = server_info["white_agent_url"]
    data_dir = server_info["data_dir"]
    spec_dir = server_info["spec_dir"]

    print(f"\n{'=' * 60}")
    print("E2E Test: Green Agent → White Agent → Evaluation (HBB)")
    print(f"{'=' * 60}")
    print(f"Green agent: {green_url}")
    print(f"White agent: {white_url}")
    print(f"Spec dir: {spec_dir}")
    print(f"Data dir: {data_dir}")
    print(f"{'=' * 60}\n")

    eval_request = {
        "participants": {
            "white_agent": white_url,
        },
        "config": {
            "data_dir": str(data_dir),
            "task_dirs": [str(spec_dir)],
        },
    }

    print("Sending EvalRequest to green agent...")
    print(f"EvalRequest: {json.dumps(eval_request, indent=2)}")

    send_message_payload = {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": json.dumps(eval_request)}],
            "messageId": uuid4().hex,
        }
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)) as httpx_client:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=green_url)
        agent_card = await resolver.get_agent_card()

        print(f"Connected to green agent: {agent_card.name}")

        client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)
        request = SendStreamingMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(**send_message_payload),
        )

        print("Sending message to green agent (this may take a while)...")
        last_event = None
        async for event in client.send_message_streaming(request):
            last_event = event
            event_json = event.model_dump(mode="json", exclude_none=True)
            result = event_json.get("root", {}).get("result", {})
            kind = result.get("kind", "")
            if kind == "status-update":
                state = result.get("status", {}).get("state", "")
                print(f"  [stream] task state: {state}")
            elif kind in ("task", "message"):
                print(f"  [stream] received final {kind}")

    assert last_event is not None, "No events received from green agent stream"
    resp_json = last_event.model_dump(mode="json", exclude_none=True)
    print("\nGreen agent response received!")
    print(f"Response type: {type(response)}")
    print(f"Top-level response keys: {list(resp_json.keys())}")

    runs_root = data_dir / "runs"
    assert runs_root.exists(), f"runs/ directory not created at {runs_root}"

    run_dirs = [p for p in runs_root.iterdir() if p.is_dir()]
    assert len(run_dirs) >= 1, f"No run directories found in {runs_root}"

    run_dir = sorted(run_dirs)[-1]
    task_dir = run_dir / TASK_ID

    print(f"\nRun directory: {run_dir}")
    print(f"Task directory: {task_dir}")

    expected_files = ["meta.json", "submission_trace.json", "judge_input.json", "judge_output.json"]
    for fname in expected_files:
        fpath = task_dir / fname
        assert fpath.exists(), f"Missing expected file: {fname}"
        print(f"  ✓ {fname} exists")

    submission_trace = json.loads((task_dir / "submission_trace.json").read_text())
    judge_output = json.loads((task_dir / "judge_output.json").read_text())

    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")

    print("\nSubmission from white agent:")
    print(f"  Status: {submission_trace.get('status')}")
    if submission_trace.get("fit_result"):
        fit = submission_trace["fit_result"]
        print(f"  Fit center: {fit.get('center')}")
        print(f"  Fit sigma: {fit.get('sigma')}")
        print(f"  Significance: {fit.get('significance')}")
    if submission_trace.get("comments"):
        print(f"  Comments: {submission_trace.get('comments')[:100]}...")

    print("\nEvaluation by green agent:")
    print(f"  Status: {judge_output.get('status')}")
    if "final" in judge_output:
        final = judge_output["final"]
        print(f"  Score: {final.get('total_score')}/{final.get('max_score')}")
        print(f"  Normalized: {final.get('normalized_score', 0):.3f}")

    if judge_output.get("issues"):
        print(f"\n  Issues ({len(judge_output['issues'])}):")
        for issue in judge_output["issues"][:5]:
            print(f"    - [{issue.get('severity', '?')}] {issue.get('message', issue)}")

    print(f"\n{'=' * 60}")

    assert submission_trace.get("status") in ("ok", "error", "success"), (
        f"Unexpected submission status: {submission_trace.get('status')}"
    )

    if submission_trace.get("status") in ("ok", "success"):
        assert "final" in judge_output, "Judge output missing 'final' scores"
        assert judge_output["final"]["total_score"] >= 0, "Score should be non-negative"

        cuts = submission_trace.get("cuts")
        if cuts is not None:
            cut_ids = {cut.get("cut_id") for cut in cuts if isinstance(cut, dict)}
            assert {"met_trigger", "met_150", "zero_lep", "dphi_bb", "dphi_met_bb"}.issubset(cut_ids)

        fit = submission_trace.get("fit_result", {})
        center = fit.get("center")
        if center is not None:
            assert 110.0 <= center <= 140.0, f"Fitted center={center} is outside expected HBB range"


@pytest.mark.asyncio
async def test_e2e_verify_hbb_grading_structure(green_server_with_white_agent):
    """Verify the HBB grading structure from the green agent output."""
    server_info = green_server_with_white_agent
    data_dir = server_info["data_dir"]

    await asyncio.sleep(0.5)

    runs_root = data_dir / "runs"
    if not runs_root.exists():
        pytest.skip("No previous run found - run test_e2e_green_calls_white_for_hbb first")

    run_dirs = [p for p in runs_root.iterdir() if p.is_dir()]
    if not run_dirs:
        pytest.skip("No run directories found")

    run_dir = sorted(run_dirs)[-1]
    task_dir = run_dir / TASK_ID

    if not (task_dir / "judge_output.json").exists():
        pytest.skip("judge_output.json not found")

    judge_output = json.loads((task_dir / "judge_output.json").read_text())

    assert "status" in judge_output, "Missing 'status' in judge_output"
    assert "final" in judge_output, "Missing 'final' in judge_output"

    final = judge_output["final"]
    assert "total_score" in final, "Missing 'total_score' in final"
    assert "max_score" in final, "Missing 'max_score' in final"
    assert "normalized_score" in final, "Missing 'normalized_score' in final"

    expected_normalized = final["total_score"] / max(1e-9, final["max_score"])
    assert abs(final["normalized_score"] - expected_normalized) < 0.001, (
        f"Normalized score mismatch: {final['normalized_score']} vs {expected_normalized}"
    )

    print("\nGrading structure verified:")
    print(f"  Total: {final['total_score']}/{final['max_score']}")
    print(f"  Normalized: {final['normalized_score']:.3f}")


async def run_e2e_test_standalone():
    """Run the HBB E2E test as a standalone script (no pytest)."""
    print("=" * 60)
    print("E2E Integration Test: Green Agent ↔ White Agent (HBB)")
    print("=" * 60)

    white_url = f"http://127.0.0.1:{WHITE_AGENT_PORT}"
    try:
        httpx.get(f"{white_url}/.well-known/agent-card.json", timeout=5)
        print(f"✓ White agent running at {white_url}")
    except Exception:
        print(f"✗ White agent NOT running at {white_url}")
        print("  Start it with: cd src && python server.py --port 9009")
        return False

    if not BENCHMARK_DIR.exists():
        print(f"✗ Benchmark directory not found: {BENCHMARK_DIR}")
        return False

    benchmark_spec = BENCHMARK_DIR / "specs" / TASK_NAME
    if not benchmark_spec.exists():
        print(f"✗ Benchmark spec not found: {benchmark_spec}")
        return False

    print(f"✓ Benchmark directory found: {BENCHMARK_DIR}")

    tmpdir = Path(tempfile.mkdtemp(prefix="e2e_test_hbb_"))
    data_dir = tmpdir / "atlas_cache"
    data_dir.mkdir(parents=True, exist_ok=True)

    try:
        source_data = DATA_DIR / RELEASE / DATASET / SKIM
        if source_data.exists():
            dest_data = data_dir / RELEASE / DATASET / SKIM
            dest_data.mkdir(parents=True, exist_ok=True)
            for root_file in list(source_data.glob("*.root"))[:3]:
                shutil.copy(root_file, dest_data / root_file.name)
            print(f"✓ Copied data files to {dest_data}")
        else:
            print(f"! Data source not found: {source_data}")
            print("  Will rely on green agent to download data")

        spec_dir = tmpdir / "specs" / TASK_NAME
        spec_dir.mkdir(parents=True, exist_ok=True)
        for spec_file in ["task_spec.yaml", "rubric.yaml", "eval_ref.yaml", "white_prompt.md", "judge_prompt.md"]:
            src = benchmark_spec / spec_file
            if src.exists():
                shutil.copy(src, spec_dir / spec_file)

        task_spec = yaml.safe_load((spec_dir / "task_spec.yaml").read_text())
        task_spec["mode"] = "call_white"
        (spec_dir / "task_spec.yaml").write_text(yaml.dump(task_spec, sort_keys=False))
        print("✓ Created spec directory with call_white mode")

        env = os.environ.copy()
        env["HEPEX_DATA_DIR"] = str(data_dir)
        env["PYTHONPATH"] = str(BENCHMARK_DIR / "src")

        cmd = [
            sys.executable,
            str(BENCHMARK_DIR / "src" / "server.py"),
            "--host", "127.0.0.1",
            "--port", str(GREEN_AGENT_PORT),
        ]

        print(f"\nStarting green agent on port {GREEN_AGENT_PORT}...")
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(BENCHMARK_DIR),
        )

        green_url = f"http://127.0.0.1:{GREEN_AGENT_PORT}"
        ready = False
        for _ in range(50):
            try:
                resp = httpx.get(f"{green_url}/.well-known/agent-card.json", timeout=1)
                if resp.status_code == 200:
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.1)

        if not ready:
            proc.kill()
            stdout, stderr = proc.communicate()
            print("Green agent failed to start!")
            print("stdout:", stdout.decode())
            print("stderr:", stderr.decode())
            return False

        print(f"✓ Green agent running at {green_url}")

        eval_request = {
            "participants": {"white_agent": white_url},
            "config": {
                "data_dir": str(data_dir),
                "task_dirs": [str(spec_dir)],
            },
        }

        print("\nSending EvalRequest to green agent...")
        print(f"  White agent: {white_url}")
        print(f"  Task: {TASK_NAME} (call_white mode)")

        send_message_payload = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": json.dumps(eval_request)}],
                "messageId": uuid4().hex,
            }
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)) as httpx_client:
            resolver = A2ACardResolver(httpx_client=httpx_client, base_url=green_url)
            agent_card = await resolver.get_agent_card()

            client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)
            request = SendStreamingMessageRequest(
                id=str(uuid4()),
                params=MessageSendParams(**send_message_payload),
            )

            print("\nWaiting for green agent to process...")
            print("  (Green downloads data → sends to white → evaluates response)")
            async for event in client.send_message_streaming(request):
                event_json = event.model_dump(mode="json", exclude_none=True)
                result = event_json.get("root", {}).get("result", {})
                kind = result.get("kind", "")
                if kind == "status-update":
                    state = result.get("status", {}).get("state", "")
                    print(f"  [stream] task state: {state}")
                elif kind in ("task", "message"):
                    print(f"  [stream] received final {kind}")

        print("\n✓ Green agent completed!")

        runs_root = data_dir / "runs"
        if runs_root.exists():
            run_dirs = [p for p in runs_root.iterdir() if p.is_dir()]
            if run_dirs:
                run_dir = sorted(run_dirs)[-1]
                task_dir = run_dir / TASK_ID

                if (task_dir / "judge_output.json").exists():
                    judge_output = json.loads((task_dir / "judge_output.json").read_text())
                    submission = json.loads((task_dir / "submission_trace.json").read_text())

                    print("\n" + "=" * 60)
                    print("RESULTS")
                    print("=" * 60)
                    print(f"White agent status: {submission.get('status')}")
                    if submission.get("fit_result"):
                        fit = submission["fit_result"]
                        print(f"  center = {fit.get('center')}")
                        print(f"  sigma = {fit.get('sigma')}")
                        print(f"  significance = {fit.get('significance')}")

                    print("\nGreen agent evaluation:")
                    print(f"  Status: {judge_output.get('status')}")
                    if "final" in judge_output:
                        final = judge_output["final"]
                        print(f"  Score: {final['total_score']}/{final['max_score']}")
                        print(f"  Normalized: {final['normalized_score']:.3f}")

                    print("=" * 60)
                    return True

        print("! Could not find results")
        return False

    finally:
        if "proc" in locals():
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

        print(f"\nTemp dir: {tmpdir} (not cleaned up for inspection)")


if __name__ == "__main__":
    success = asyncio.run(run_e2e_test_standalone())
    sys.exit(0 if success else 1)
