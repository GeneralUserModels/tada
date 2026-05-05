"""Verify and refine a generated moment: review for errors, fix issues, improve quality."""

from __future__ import annotations

from pathlib import Path

from agent.agent import Agent
from agent.tools.read import ReadTool
from agent.tools.write import WriteTool
from agent.tools.edit import EditTool
from agent.tools.terminal import TerminalTool


_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
REFINE_SYSTEM_PROMPT = (_PROMPTS / "verify_refine_system.txt").read_text()
REFINE_USER_TEMPLATE = (_PROMPTS / "verify_refine_user.txt").read_text()


def verify_and_refine(
    output_dir: str,
    logs_dir: str,
    model: str,
    api_key: str | None = None,
) -> bool:
    """Review a generated moment for errors and quality, fix issues.

    Returns True if index.html still exists after review (kept or improved).
    Returns False if the agent deleted it (quality too low).
    """
    output_path = Path(output_dir)
    if not (output_path / "index.html").exists():
        return False

    print(f"  [verify] reviewing {output_dir}")

    tools = [ReadTool(), WriteTool(), EditTool(), TerminalTool()]
    agent = Agent(
        model=model,
        system_prompt=REFINE_SYSTEM_PROMPT,
        tools=tools,
        max_rounds=30,
        web_search=True,
        api_key=api_key
    )

    message = REFINE_USER_TEMPLATE.format(output_dir=output_dir)
    agent.run([{"role": "user", "content": message}])

    exists = (output_path / "index.html").exists()
    print(f"  [verify] done — {'kept' if exists else 'deleted'}")
    return exists
