import json
import asyncio
import logging
from a2a.server.tasks import TaskUpdater
from a2a.types import Message, TaskState, Part, TextPart
from a2a.utils import get_message_text, new_agent_text_message

logger = logging.getLogger(__name__)

class WhiteAgent:
    def __init__(self):
        self.app_name = "hepex_analysisops"
        # Read system prompt from AGENTS.md
        try:
            with open("./AGENTS.md", "r") as f:
                self.system_prompt = f.read().strip()
        except Exception as e:
            logger.error(f"Failed to read ./AGENTS.md: {e}")
            self.system_prompt = "You are a physics analysis agent."

    async def run(self, message: Message, updater: TaskUpdater) -> None:
        input_payload = get_message_text(message)
        
        # 1. Log the received request
        try:
            req_json = json.loads(input_payload)
            logger.info("Received request")
            logger.debug(f"Request payload:\n{json.dumps(req_json, indent=2)}")
            prompt = req_json.get("prompt")
            if not prompt:
                logger.warning("Received request without 'prompt' field")
        except json.JSONDecodeError:
            logger.warning("Received non-JSON request")
            logger.debug(f"Raw input text:\n{input_payload}")

        await updater.update_status(
            TaskState.working,
            new_agent_text_message("Running analysis agent via OpenHarness..."),
        )

        final_text = None
        try:
            retry_delay = 2.0
            max_retries = 5
            
            for attempt in range(max_retries):
                try:
                    # Construct the command: oh --permission-mode --print --system-prompt "..." "task"
                    cmd = [
                        "oh",
                        "--permission-mode", "full_auto",
                        "--dangerously-skip-permissions",
                        "--system-prompt", self.system_prompt,
                        "--print", prompt 
                    ]

                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    stdout, stderr = await process.communicate()

                    # Write stdout and stderr to a file for debugging
                    with open("debug_oh_output.log", "a", encoding="utf-8") as f:
                        f.write(f"--- Attempt {attempt + 1} ---\n")
                        f.write(f"STDOUT:\n{stdout.decode(errors='replace')}\n")
                        f.write(f"STDERR:\n{stderr.decode(errors='replace')}\n")
                        f.write("="*40 + "\n")
                    
                    if process.returncode == 0:
                        final_text = stdout.decode().strip()
                        break
                    else:
                        err_str = stderr.decode().strip()
                        # Check for rate limits in CLI output if applicable
                        is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                        
                        if is_rate_limit and attempt < max_retries - 1:
                            logger.warning(f"WhiteAgent: Rate limit hit. Retrying {attempt+1}/{max_retries}...")
                            await asyncio.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, 30.0)
                            continue
                        
                        final_text = json.dumps(
                            {"status": "error", "error": f"OpenHarness failed with exit code {process.returncode}: {err_str}"},
                            ensure_ascii=False,
                        )
                        break
                        
                except Exception as e:
                    if attempt == max_retries - 1:
                        final_text = json.dumps(
                            {"status": "error", "error": f"Agent run failed: {type(e).__name__}: {e}"},
                            ensure_ascii=False,
                        )
                    await asyncio.sleep(retry_delay)
            
            logger.debug(f"Output from OpenHarness:\n{final_text}")
            
            if final_text is None:
                final_text = json.dumps(
                    {"status": "error", "error": "No final response from OpenHarness wrapper"},
                    ensure_ascii=False,
                )

            # Add artifact BEFORE marking task as completed
            await updater.add_artifact(
                parts=[Part(root=TextPart(kind="text", text=final_text))],
                name="submission_trace",
            )
            await updater.update_status(TaskState.completed, new_agent_text_message("Done."))

        except Exception as e:
            err = {"status": "error", "error": f"{type(e).__name__}: {e}"}
            await updater.add_artifact(
                parts=[Part(root=TextPart(kind="text", text=json.dumps(err, ensure_ascii=False)))],
                name="submission_trace",
            )
            await updater.update_status(TaskState.failed, new_agent_text_message(err["error"]))
