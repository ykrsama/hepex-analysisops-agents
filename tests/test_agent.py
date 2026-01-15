from typing import Any
import pytest
import httpx
from uuid import uuid4

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import Message, Part, Role, TextPart, Task

import json

# A2A validation helpers - adapted from https://github.com/a2aproject/a2a-inspector/blob/main/backend/validators.py

def validate_agent_card(card_data: dict[str, Any]) -> list[str]:
    """Validate the structure and fields of an agent card."""
    errors: list[str] = []

    # Use a frozenset for efficient checking and to indicate immutability.
    required_fields = frozenset(
        [
            'name',
            'description',
            'url',
            'version',
            'capabilities',
            'defaultInputModes',
            'defaultOutputModes',
            'skills',
        ]
    )

    # Check for the presence of all required fields
    for field in required_fields:
        if field not in card_data:
            errors.append(f"Required field is missing: '{field}'.")

    # Check if 'url' is an absolute URL (basic check)
    if 'url' in card_data and not (
        card_data['url'].startswith('http://')
        or card_data['url'].startswith('https://')
    ):
        errors.append(
            "Field 'url' must be an absolute URL starting with http:// or https://."
        )

    # Check if capabilities is a dictionary
    if 'capabilities' in card_data and not isinstance(
        card_data['capabilities'], dict
    ):
        errors.append("Field 'capabilities' must be an object.")

    # Check if defaultInputModes and defaultOutputModes are arrays of strings
    for field in ['defaultInputModes', 'defaultOutputModes']:
        if field in card_data:
            if not isinstance(card_data[field], list):
                errors.append(f"Field '{field}' must be an array of strings.")
            elif not all(isinstance(item, str) for item in card_data[field]):
                errors.append(f"All items in '{field}' must be strings.")

    # Check skills array
    if 'skills' in card_data:
        if not isinstance(card_data['skills'], list):
            errors.append(
                "Field 'skills' must be an array of AgentSkill objects."
            )
        elif not card_data['skills']:
            errors.append(
                "Field 'skills' array is empty. Agent must have at least one skill if it performs actions."
            )

    return errors


def _validate_task(data: dict[str, Any]) -> list[str]:
    errors = []
    if 'id' not in data:
        errors.append("Task object missing required field: 'id'.")
    if 'status' not in data or 'state' not in data.get('status', {}):
        errors.append("Task object missing required field: 'status.state'.")
    return errors


def _validate_status_update(data: dict[str, Any]) -> list[str]:
    errors = []
    if 'status' not in data or 'state' not in data.get('status', {}):
        errors.append(
            "StatusUpdate object missing required field: 'status.state'."
        )
    return errors


def _validate_artifact_update(data: dict[str, Any]) -> list[str]:
    errors = []
    if 'artifact' not in data:
        errors.append(
            "ArtifactUpdate object missing required field: 'artifact'."
        )
    elif (
        'parts' not in data.get('artifact', {})
        or not isinstance(data.get('artifact', {}).get('parts'), list)
        or not data.get('artifact', {}).get('parts')
    ):
        errors.append("Artifact object must have a non-empty 'parts' array.")
    return errors


def _validate_message(data: dict[str, Any]) -> list[str]:
    errors = []
    if (
        'parts' not in data
        or not isinstance(data.get('parts'), list)
        or not data.get('parts')
    ):
        errors.append("Message object must have a non-empty 'parts' array.")
    if 'role' not in data or data.get('role') != 'agent':
        errors.append("Message from agent must have 'role' set to 'agent'.")
    return errors


def validate_event(data: dict[str, Any]) -> list[str]:
    """Validate an incoming event from the agent based on its kind."""
    if 'kind' not in data:
        return ["Response from agent is missing required 'kind' field."]

    kind = data.get('kind')
    validators = {
        'task': _validate_task,
        'status-update': _validate_status_update,
        'artifact-update': _validate_artifact_update,
        'message': _validate_message,
    }

    validator = validators.get(str(kind))
    if validator:
        return validator(data)

    return [f"Unknown message kind received: '{kind}'."]


# A2A messaging helpers

async def send_text_message(text: str, url: str, context_id: str | None = None, streaming: bool = False):
    async with httpx.AsyncClient(timeout=120) as httpx_client:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=url)
        agent_card = await resolver.get_agent_card()
        config = ClientConfig(httpx_client=httpx_client, streaming=streaming)
        factory = ClientFactory(config)
        client = factory.create(agent_card)

        msg = Message(
            kind="message",
            role=Role.user,
            parts=[Part(TextPart(text=text))],
            message_id=uuid4().hex,
            context_id=context_id,
        )

        events = [event async for event in client.send_message(msg)]

    return events


# A2A conformance tests

def test_agent_card(agent):
    """Validate agent card structure and required fields."""
    response = httpx.get(f"{agent}/.well-known/agent-card.json")
    assert response.status_code == 200, "Agent card endpoint must return 200"

    card_data = response.json()
    errors = validate_agent_card(card_data)

    assert not errors, f"Agent card validation failed:\n" + "\n".join(errors)

@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [True, False])
async def test_message(agent, streaming):
    """Test that agent returns valid A2A message format."""
    events = await send_text_message("Hello", agent, streaming=streaming)

    all_errors = []
    for event in events:
        match event:
            case Message() as msg:
                errors = validate_event(msg.model_dump())
                all_errors.extend(errors)

            case (task, update):
                errors = validate_event(task.model_dump())
                all_errors.extend(errors)
                if update:
                    errors = validate_event(update.model_dump())
                    all_errors.extend(errors)

            case _:
                pytest.fail(f"Unexpected event type: {type(event)}")

    assert events, "Agent should respond with at least one event"
    assert not all_errors, f"Message validation failed:\n" + "\n".join(all_errors)

# Add your custom tests here


def _extract_text_from_parts(parts):
    """Helper to extract text from a list of Part objects."""
    texts = []
    for p in parts:
        root = getattr(p, "root", None)
        if root:
            if getattr(root, "kind", None) == "text":
                texts.append(root.text)
            elif hasattr(root, "text"):
                texts.append(root.text)
    return texts


def extract_response_and_status(outputs):
    """
    Accept both:
      - dict: {"response": "...", "status": "...", ...}
      - list/tuple of events: (Task, update) tuples, Task objects, Message objects

    Returns: (response_text, status, debug_str)
    """
    # Case A: dict
    if isinstance(outputs, dict):
        return outputs.get("response", ""), outputs.get("status", "completed"), json.dumps(outputs, ensure_ascii=False, default=str)

    # Case B: list/tuple stream-ish
    response_chunks = []
    status = None
    debug_str = repr(outputs)

    def process_task(task):
        nonlocal status
        # Try to read status
        try:
            status = task.status.state.value
        except Exception:
            pass

        # Extract from status.message (usually just "Done." or similar)
        # Skip these as they're not the actual content
        
        # Extract from artifacts - this is where actual responses are
        try:
            if task.artifacts:
                for artifact in task.artifacts:
                    response_chunks.extend(_extract_text_from_parts(artifact.parts))
        except Exception:
            pass
            
        # Also check history for agent messages with substantive content
        try:
            if task.history:
                for msg in task.history:
                    if msg.role.value == "agent" and msg.parts:
                        # Skip status messages like "Running analysis agent..."
                        for p in msg.parts:
                            root = getattr(p, "root", None)
                            if root and hasattr(root, "text"):
                                text = root.text
                                # Skip common status messages
                                if text not in ["Running analysis agent...", "Done."]:
                                    response_chunks.append(text)
        except Exception:
            pass

    if isinstance(outputs, (list, tuple)):
        for item in outputs:
            if item is None:
                continue
            if isinstance(item, Task):
                process_task(item)
            elif isinstance(item, tuple) and len(item) == 2:
                task, update = item
                if isinstance(task, Task):
                    process_task(task)
                # Check if update contains artifact data
                if update is not None:
                    try:
                        if hasattr(update, "artifact") and update.artifact:
                            response_chunks.extend(_extract_text_from_parts(update.artifact.parts))
                    except Exception:
                        pass
            elif isinstance(item, Message):
                if item.role.value == "agent" and item.parts:
                    texts = _extract_text_from_parts(item.parts)
                    for t in texts:
                        if t not in ["Running analysis agent...", "Done."]:
                            response_chunks.append(t)

    return "\n".join([c for c in response_chunks if c]), status or "unknown", debug_str

@pytest.mark.asyncio
async def test_agent_identity_and_tools_response(agent):
    prompt = (
        "Who are you? What tools do you have access to?\n"
        "Please answer in JSON with keys: name, description, tools (list of tool names)."
    )

    outputs = await send_text_message(
        text=prompt,
        url=agent,
        streaming=False,
    )

    resp, status, debug = extract_response_and_status(outputs)

    assert status in ("completed", "ok"), f"Task not completed. status={status}\noutputs={debug}"

    resp = (resp or "").strip()
    assert resp != "", f"Empty response. outputs={debug}"

    # JSON parse (soft)
    try:
        parsed = json.loads(resp)
    except Exception:
        parsed = None

    if isinstance(parsed, dict):
        assert "name" in parsed
        assert "tools" in parsed
        assert isinstance(parsed["tools"], list)
    else:
        lower = resp.lower()
        assert ("tool" in lower or "tools" in lower or "capab" in lower), (
            "Response didn't look like it mentioned tools/capabilities.\n"
            f"Response={resp}\noutputs={debug}"
        )