import json
from a2a.server.tasks import TaskUpdater
from a2a.types import Message, TaskState, Part, TextPart
from a2a.utils import get_message_text, new_agent_text_message

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from tools.root_tools import inspect_root_schema_tool, load_kinematics_tool
from tools.physics_tools import calc_dilepton_mass_tool, calc_system_invariant_mass_tool
from tools.fitting_tools import fit_peak_tool


class WhiteAgent:
    def __init__(self):
        self.agent = Agent(
            name="hepex_white_agent",
            model="gemini-2.0-flash",
            description="General-purpose physics analysis agent using tools.",
            instruction=(
                "You are a physics analysis agent.\n"
                "- Use provided tools; do not do low-level ROOT I/O yourself.\n"
                "- If schema is unknown, inspect first.\n"
                "- Make decisions explicitly and do sanity checks.\n"
                "- Output a single JSON object in the task-required format.\n"
            ),
            tools=[
                inspect_root_schema_tool,
                load_kinematics_tool,
                calc_dilepton_mass_tool,
                calc_system_invariant_mass_tool,
                fit_peak_tool,
            ],
        )

        self.session_service = InMemorySessionService()
        self.app_name = "hepex_analysisops"
        self.runner = Runner(
            agent=self.agent,
            app_name=self.app_name,
            session_service=self.session_service,
        )
        

    async def run(self, message: Message, updater: TaskUpdater) -> None:
        input_text = get_message_text(message)

        await updater.update_status(
            TaskState.working,
            new_agent_text_message("Running analysis agent..."),
        )

        user_id = "a2a_user"
        # Use context_id as session_id to enable multi-turn conversations
        session_id = message.context_id or message.message_id

        # Create session if it doesn't exist
        try:
            await self.session_service.create_session(
                app_name=self.app_name,
                user_id=user_id,
                session_id=session_id,
            )
        except Exception:
            # session may already exist
            pass

        content = types.Content(role="user", parts=[types.Part(text=input_text)])

        final_text = None
        try:
            async for event in self.runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content,
            ):
                if event.is_final_response():
                    if event.content and event.content.parts:
                        # Extract text from all parts, filtering to text parts only
                        text_parts = []
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                text_parts.append(part.text)
                        final_text = "\n".join(text_parts) if text_parts else None
                    if not final_text:
                        final_text = event.error_message or "No final response text."
                    break

            if final_text is None:
                final_text = json.dumps(
                    {"status": "error", "error": "No final response from runner"},
                    ensure_ascii=False,
                )

            # Add artifact BEFORE marking task as completed
            # A2A closes the stream on terminal states, so artifacts must come first
            await updater.add_artifact(
                parts=[Part(root=TextPart(kind="text", text=final_text))],
                name="submission_trace",
            )
            await updater.update_status(TaskState.completed, new_agent_text_message("Done."))

        except Exception as e:
            err = {"status": "error", "error": f"{type(e).__name__}: {e}"}
            # Add artifact BEFORE marking task as failed
            await updater.add_artifact(
                parts=[Part(root=TextPart(kind="text", text=json.dumps(err, ensure_ascii=False)))],
                name="submission_trace",
            )
            await updater.update_status(TaskState.failed, new_agent_text_message(err["error"]))