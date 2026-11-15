from __future__ import annotations

from functools import cache
from importlib.resources import files

from chatbot_ai.intents import AgentName
from chatbot_ai.interface import ProfileInfo

SHARED_BLOCKS = ("shared_persona", "shared_rules")


@cache
def load_prompt(name: str) -> str:
    return (files("chatbot_ai") / "prompts" / f"{name}.md").read_text(encoding="utf-8").strip()


def profile_block(profile: ProfileInfo) -> str:
    return load_prompt("shared_profile").format(
        display_name=profile.display_name,
        location_name=profile.location_name or "not set",
        location_id=profile.location_id,
    )


def agent_system_prompt(agent: AgentName, profile: ProfileInfo) -> str:
    blocks = [load_prompt(name) for name in SHARED_BLOCKS]
    blocks.append(profile_block(profile))
    blocks.append(load_prompt(agent.value))
    return "\n\n".join(blocks)
