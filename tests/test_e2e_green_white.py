"""
End-to-End Integration Test: Green Agent (Judge) ↔ White Agent (Solver)

This test script tests the FULL benchmark evaluation flow:
1. Starts a green agent server (from hepex-analysisops-benchmark)
2. Uses the white agent server running on port 9009
3. Sends an EvalRequest to the green agent with zpeak_fit task
4. Green agent downloads data, sends task to white agent
5. White agent processes task and returns result
6. Green agent evaluates response using rubric and returns score

Prerequisites:
- White agent server MUST be running on port 9009 before running this test
  cd /home/ranriver/Projects/hepex-analysisops-agents/src && python server.py --port 9009

Usage:
    pytest tests/test_e2e_green_white.py -v -s
    
    # Or run as standalone script:
    python tests/test_e2e_green_white.py
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import yaml

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

WHITE_AGENT_PORT = 9009
GREEN_AGENT_PORT = 9010  # Use different port to avoid conflicts
BENCHMARK_DIR = Path(__file__).parent.parent.parent / "hepex-analysisops-benchmark"
DATA_DIR = Path(__file__).parent.parent.parent / "data"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

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
    """
    Start a green agent server configured to call the white agent.
    Creates a zpeak_fit task spec that uses mode: call_white.
    """
    if not BENCHMARK_DIR.exists():
        pytest.skip(f"Benchmark directory not found: {BENCHMARK_DIR}")
    
    # Setup temporary directories
    tmpdir = tmp_path_factory.mktemp("e2e_green_server")
    data_dir = tmpdir / "atlas_cache"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy data files to temp data directory if they exist
    source_data = DATA_DIR / "2025e-13tev-beta" / "data" / "2muons"
    if source_data.exists():
        dest_data = data_dir / "2025e-13tev-beta" / "data" / "2muons"
        dest_data.mkdir(parents=True, exist_ok=True)
        for root_file in source_data.glob("*.root"):
            import shutil
            shutil.copy(root_file, dest_data / root_file.name)
    
    # Create task spec directory with call_white mode
    spec_dir = tmpdir / "specs" / "zpeak_fit"
    spec_dir.mkdir(parents=True, exist_ok=True)
    
    # Task spec configured to call white agent
    task_spec = {
        "id": "t001_zpeak_fit",
        "type": "zpeak_fit",
        "mode": "call_white",  # This is the key - actually call white agent
        "needs_data": True,
        "release": "2025e-13tev-beta",
        "dataset": "data",
        "skim": "2muons",
        "protocol": "https",
        "max_files": 1,
        "cache": True,
        "reuse_existing": True,
        "rubric_path": "rubric.yaml",
        "eval_ref_path": "eval_ref.yaml",
        "white_prompt_path": "white_prompt.md",
        "description": "Build m_mumu and fit around Z peak.",
        "constraints": {
            "time_limit_sec": 600,
            "memory_gb": 8,
            "allow_network": False,
        },
    }
    (spec_dir / "task_spec.yaml").write_text(yaml.dump(task_spec))
    
    # Copy rubric from benchmark specs
    benchmark_spec = BENCHMARK_DIR / "specs" / "zpeak_fit"
    if (benchmark_spec / "rubric.yaml").exists():
        import shutil
        shutil.copy(benchmark_spec / "rubric.yaml", spec_dir / "rubric.yaml")
        shutil.copy(benchmark_spec / "eval_ref.yaml", spec_dir / "eval_ref.yaml")
        shutil.copy(benchmark_spec / "white_prompt.md", spec_dir / "white_prompt.md")
        if (benchmark_spec / "judge_prompt.md").exists():
            shutil.copy(benchmark_spec / "judge_prompt.md", spec_dir / "judge_prompt.md")
    else:
        # Fallback: create minimal rubric
        rubric = {
            "version": 1,
            "total": 100,
            "gates": [
                {
                    "id": "trace_present",
                    "type": "required_fields",
                    "required_fields": ["status", "fit_result", "fit_method"],
                    "fail_total_score": 0,
                },
                {
                    "id": "mu_sanity",
                    "type": "numeric_in_range",
                    "value_path": "fit_result.mu",
                    "lo": 70,
                    "hi": 110,
                    "fail_total_score": 0,
                },
            ],
            "rule_checks": [
                {
                    "id": "mu_closeness",
                    "type": "target_soft",
                    "points": 40,
                    "value_path": "fit_result.mu",
                    "target_path": "fit_expectations.mu_target",
                    "tolerance_path": "fit_expectations.mu_tolerance",
                    "soft_factor": 3.0,
                },
                {
                    "id": "sigma_range",
                    "type": "numeric_in_range",
                    "points": 20,
                    "value_path": "fit_result.sigma",
                    "range_path": "fit_expectations.sigma_range",
                    "out_of_range_points": 5,
                },
                {
                    "id": "method_metadata",
                    "type": "required_keys_in_dict",
                    "points": 20,
                    "dict_path": "fit_method",
                    "required_keys_path": "fit_expectations.method_required_fields",
                    "missing_penalty_per_key": 5,
                },
            ],
        }
        (spec_dir / "rubric.yaml").write_text(yaml.dump(rubric))
        
        eval_ref = {
            "version": 1,
            "fit_expectations": {
                "mu_target": 91.1876,
                "mu_tolerance": 2.0,
                "sigma_range": [1.0, 6.0],
                "min_p_value": 0.01,
                "method_required_fields": ["model", "fit_range", "binned_or_unbinned"],
            },
        }
        (spec_dir / "eval_ref.yaml").write_text(yaml.dump(eval_ref))
        
        white_prompt = """You are a physics analysis agent. Solve the task: **Z→μμ mass-peak fit**.

Goal
- Build the di-muon invariant mass spectrum (m_mumu) from the provided ROOT files.
- Fit around the Z resonance and report the fitted peak position (mu) and width (sigma).

Data & environment
- You will receive a list of local ROOT file paths.
- Use at most {{MAX_FILES}} files.

Output format (SUBMISSION_TRACE JSON)
Return a JSON object with:

{
  "task_id": "{{TASK_ID}}",
  "status": "ok" | "error",
  "fit_result": {
    "mu": number,
    "sigma": number,
    "gof": {
      "p_value": number,
      "chi2_ndof": number
    }
  },
  "fit_method": {
    "model": string,
    "fit_range": [number, number],
    "binned_or_unbinned": "binned" | "unbinned",
    "optimizer": string,
    "initial_params": object,
    "uncertainties_method": string
  },
  "comments": string
}

Guidance
- Briefly justify the fit model and fit range.
- If you cannot complete, set status="error" and explain in "comments".
- Output JSON only.
"""
        (spec_dir / "white_prompt.md").write_text(white_prompt)
    
    # Setup environment
    env = os.environ.copy()
    env["HEPEX_DATA_DIR"] = str(data_dir)
    env["PYTHONPATH"] = str(BENCHMARK_DIR / "src")
    
    # Start green agent server
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
    
    # Wait for server to be ready
    base_url = f"http://{host}:{port}"
    max_retries = 50
    ready = False
    
    for _ in range(max_retries):
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
    
    # Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()


# --------------------------------------------------------------------------
# Test cases
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_green_calls_white_for_zpeak(green_server_with_white_agent):
    """
    Full E2E test: Green agent receives EvalRequest, calls white agent for zpeak_fit,
    white agent processes the task, green agent evaluates and returns score.
    """
    server_info = green_server_with_white_agent
    green_url = server_info["base_url"]
    white_url = server_info["white_agent_url"]
    data_dir = server_info["data_dir"]
    spec_dir = server_info["spec_dir"]
    
    print(f"\n{'='*60}")
    print(f"E2E Test: Green Agent → White Agent → Evaluation")
    print(f"{'='*60}")
    print(f"Green agent: {green_url}")
    print(f"White agent: {white_url}")
    print(f"Spec dir: {spec_dir}")
    print(f"Data dir: {data_dir}")
    print(f"{'='*60}\n")
    
    # Build EvalRequest with white agent as participant
    eval_request = {
        "participants": {
            "white_agent": white_url,  # Key: tell green agent where white agent is
        },
        "config": {
            "data_dir": str(data_dir),
            "task_dirs": [str(spec_dir)],
        },
    }
    
    print(f"Sending EvalRequest to green agent...")
    print(f"EvalRequest: {json.dumps(eval_request, indent=2)}")
    
    # Send request to green agent
    send_message_payload = {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": json.dumps(eval_request)}],
            "messageId": uuid4().hex,
        }
    }
    
    async with httpx.AsyncClient(timeout=300.0) as httpx_client:  # Long timeout for full flow
        # Resolve green agent card
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=green_url)
        agent_card = await resolver.get_agent_card()
        
        print(f"Connected to green agent: {agent_card.name}")
        
        # Create client and send request
        client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)
        request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(**send_message_payload),
        )
        
        print(f"Sending message to green agent (this may take a while)...")
        response = await client.send_message(request)
    
    # Parse response
    resp_json = response.model_dump(mode="json", exclude_none=True)
    print(f"\nGreen agent response received!")
    print(f"Response type: {type(response)}")

    # Verify artifacts were created
    runs_root = data_dir / "runs"
    assert runs_root.exists(), f"runs/ directory not created at {runs_root}"
    
    run_dirs = [p for p in runs_root.iterdir() if p.is_dir()]
    assert len(run_dirs) >= 1, f"No run directories found in {runs_root}"
    
    # Get the latest run
    run_dir = sorted(run_dirs)[-1]
    task_dir = run_dir / "t001_zpeak_fit"
    
    print(f"\nRun directory: {run_dir}")
    print(f"Task directory: {task_dir}")
    
    # Verify all expected files exist
    expected_files = ["meta.json", "submission_trace.json", "judge_input.json", "judge_output.json"]
    for fname in expected_files:
        fpath = task_dir / fname
        assert fpath.exists(), f"Missing expected file: {fname}"
        print(f"  ✓ {fname} exists")
    
    # Load and analyze the results
    submission_trace = json.loads((task_dir / "submission_trace.json").read_text())
    judge_output = json.loads((task_dir / "judge_output.json").read_text())
    
    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    
    # Submission trace (from white agent)
    print(f"\nSubmission from white agent:")
    print(f"  Status: {submission_trace.get('status')}")
    if submission_trace.get("fit_result"):
        fit = submission_trace["fit_result"]
        print(f"  Fit mu: {fit.get('mu')}")
        print(f"  Fit sigma: {fit.get('sigma')}")
    if submission_trace.get("comments"):
        print(f"  Comments: {submission_trace.get('comments')[:100]}...")
    
    # Judge output (from green agent evaluation)
    print(f"\nEvaluation by green agent:")
    print(f"  Status: {judge_output.get('status')}")
    if "final" in judge_output:
        final = judge_output["final"]
        print(f"  Score: {final.get('total_score')}/{final.get('max_score')}")
        print(f"  Normalized: {final.get('normalized_score', 0):.3f}")
    
    if judge_output.get("issues"):
        print(f"\n  Issues ({len(judge_output['issues'])}):")
        for issue in judge_output["issues"][:5]:  # Show first 5
            print(f"    - [{issue.get('severity', '?')}] {issue.get('message', issue)}")
    
    print(f"\n{'='*60}")
    
    # Assertions
    assert submission_trace.get("status") in ("ok", "error"), \
        f"Unexpected submission status: {submission_trace.get('status')}"
    
    if submission_trace.get("status") == "ok":
        # White agent succeeded - check evaluation
        assert "final" in judge_output, "Judge output missing 'final' scores"
        assert judge_output["final"]["total_score"] >= 0, "Score should be non-negative"
        
        # Check fit results are reasonable
        fit = submission_trace.get("fit_result", {})
        mu = fit.get("mu")
        if mu is not None:
            assert 70 < mu < 110, f"Fitted mu={mu} is outside reasonable range"


@pytest.mark.asyncio
async def test_e2e_verify_grading_structure(green_server_with_white_agent):
    """
    Verify that the grading structure from green agent matches expected format.
    """
    server_info = green_server_with_white_agent
    data_dir = server_info["data_dir"]
    
    # Wait a moment for files to be written
    await asyncio.sleep(0.5)
    
    runs_root = data_dir / "runs"
    if not runs_root.exists():
        pytest.skip("No previous run found - run test_e2e_green_calls_white_for_zpeak first")
    
    run_dirs = [p for p in runs_root.iterdir() if p.is_dir()]
    if not run_dirs:
        pytest.skip("No run directories found")
    
    run_dir = sorted(run_dirs)[-1]
    task_dir = run_dir / "t001_zpeak_fit"
    
    if not (task_dir / "judge_output.json").exists():
        pytest.skip("judge_output.json not found")
    
    judge_output = json.loads((task_dir / "judge_output.json").read_text())
    
    # Verify expected structure
    assert "status" in judge_output, "Missing 'status' in judge_output"
    assert "final" in judge_output, "Missing 'final' in judge_output"
    
    final = judge_output["final"]
    assert "total_score" in final, "Missing 'total_score' in final"
    assert "max_score" in final, "Missing 'max_score' in final"
    assert "normalized_score" in final, "Missing 'normalized_score' in final"
    
    # Verify normalized score is calculated correctly
    expected_normalized = final["total_score"] / max(1e-9, final["max_score"])
    assert abs(final["normalized_score"] - expected_normalized) < 0.001, \
        f"Normalized score mismatch: {final['normalized_score']} vs {expected_normalized}"
    
    print(f"\nGrading structure verified:")
    print(f"  Total: {final['total_score']}/{final['max_score']}")
    print(f"  Normalized: {final['normalized_score']:.3f}")


# --------------------------------------------------------------------------
# Standalone runner
# --------------------------------------------------------------------------

async def run_e2e_test_standalone():
    """Run the E2E test as a standalone script (no pytest)."""
    import shutil
    import tempfile
    
    print("=" * 60)
    print("E2E Integration Test: Green Agent ↔ White Agent")
    print("=" * 60)
    
    # Check white agent is running
    white_url = f"http://127.0.0.1:{WHITE_AGENT_PORT}"
    try:
        resp = httpx.get(f"{white_url}/.well-known/agent-card.json", timeout=5)
        print(f"✓ White agent running at {white_url}")
    except Exception as e:
        print(f"✗ White agent NOT running at {white_url}")
        print(f"  Start it with: cd src && python server.py --port 9009")
        return False
    
    if not BENCHMARK_DIR.exists():
        print(f"✗ Benchmark directory not found: {BENCHMARK_DIR}")
        return False
    
    print(f"✓ Benchmark directory found: {BENCHMARK_DIR}")
    
    # Create temp directory
    tmpdir = Path(tempfile.mkdtemp(prefix="e2e_test_"))
    data_dir = tmpdir / "data"
    data_dir.mkdir()
    
    try:
        # Copy data files
        source_data = DATA_DIR / "2025e-13tev-beta" / "data" / "2muons"
        if source_data.exists():
            dest_data = data_dir / "2025e-13tev-beta" / "data" / "2muons"
            dest_data.mkdir(parents=True, exist_ok=True)
            for root_file in list(source_data.glob("*.root"))[:1]:  # Just one file
                shutil.copy(root_file, dest_data / root_file.name)
            print(f"✓ Copied data files to {dest_data}")
        else:
            print(f"! Data source not found: {source_data}")
            print("  Will rely on green agent to download data")
        
        # Create spec directory
        spec_dir = tmpdir / "specs" / "zpeak_fit"
        spec_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy specs from benchmark
        benchmark_spec = BENCHMARK_DIR / "specs" / "zpeak_fit"
        for spec_file in ["task_spec.yaml", "rubric.yaml", "eval_ref.yaml", "white_prompt.md"]:
            if (benchmark_spec / spec_file).exists():
                shutil.copy(benchmark_spec / spec_file, spec_dir / spec_file)
        
        # Patch task_spec to use call_white mode
        task_spec = yaml.safe_load((spec_dir / "task_spec.yaml").read_text())
        task_spec["mode"] = "call_white"
        task_spec["max_files"] = 1
        (spec_dir / "task_spec.yaml").write_text(yaml.dump(task_spec))
        print(f"✓ Created spec directory with call_white mode")
        
        # Start green agent
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
        
        # Wait for green agent
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
        
        # Send EvalRequest
        eval_request = {
            "participants": {"white_agent": white_url},
            "config": {
                "data_dir": str(data_dir),
                "task_dirs": [str(spec_dir)],
            },
        }
        
        print(f"\nSending EvalRequest to green agent...")
        print(f"  White agent: {white_url}")
        print(f"  Task: zpeak_fit (call_white mode)")
        
        send_message_payload = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": json.dumps(eval_request)}],
                "messageId": uuid4().hex,
            }
        }
        
        async with httpx.AsyncClient(timeout=300.0) as httpx_client:
            resolver = A2ACardResolver(httpx_client=httpx_client, base_url=green_url)
            agent_card = await resolver.get_agent_card()
            
            client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)
            request = SendMessageRequest(
                id=str(uuid4()),
                params=MessageSendParams(**send_message_payload),
            )
            
            print("\nWaiting for green agent to process...")
            print("  (Green downloads data → sends to white → evaluates response)")
            response = await client.send_message(request)
        
        print("\n✓ Green agent completed!")
        
        # Check results
        runs_root = data_dir / "runs"
        if runs_root.exists():
            run_dirs = list(runs_root.iterdir())
            if run_dirs:
                run_dir = sorted(run_dirs)[-1]
                task_dir = run_dir / "t001_zpeak_fit"
                
                if (task_dir / "judge_output.json").exists():
                    judge_output = json.loads((task_dir / "judge_output.json").read_text())
                    submission = json.loads((task_dir / "submission_trace.json").read_text())
                    
                    print("\n" + "=" * 60)
                    print("RESULTS")
                    print("=" * 60)
                    print(f"White agent status: {submission.get('status')}")
                    if submission.get("fit_result"):
                        fit = submission["fit_result"]
                        print(f"  mu = {fit.get('mu')}")
                        print(f"  sigma = {fit.get('sigma')}")
                    
                    print(f"\nGreen agent evaluation:")
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
        # Cleanup
        if 'proc' in locals():
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        
        # Optionally cleanup temp dir
        # shutil.rmtree(tmpdir)
        print(f"\nTemp dir: {tmpdir} (not cleaned up for inspection)")


if __name__ == "__main__":
    success = asyncio.run(run_e2e_test_standalone())
    sys.exit(0 if success else 1)
