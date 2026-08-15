"""
Example: full multi-agent consultation through the Gemini API + MCP tools.

Run from the repo root (requires GEMINI_API_KEY set in .env):

    PYTHONPATH=.:platform .venv/bin/python examples/agents_example.py
"""

import asyncio

from core.config import settings
from intelligence.agents.workflow import run_consultation
from intelligence.llm import get_llm_client


async def main() -> None:
    client = get_llm_client()

    if not await client.health():
        raise SystemExit(
            f"Gemini not reachable or model '{settings.gemini_model}' unavailable. "
            "Check GEMINI_API_KEY and quota."
        )

    print(f"Running consultation on {settings.gemini_model}...\n")

    state = await run_consultation(
        client,
        query=(
            "Patient reports increased shortness of breath. Any medication "
            "safety concerns, and what does the evidence recommend for her "
            "heart failure management?"
        ),
        patient_id="P002",
        context={
            "medications": ["warfarin", "furosemide", "digoxin", "aspirin"],
            "lab_results": {"bnp": "450 pg/mL", "ef": "35%", "inr": "2.4", "potassium": "3.4 mEq/L"},
        },
    )

    print("Agents involved:", ", ".join(sorted(state["agent_outputs"])))
    print("\nTool calls:")
    for call in state["tool_calls"]:
        print(f"  {call['agent']} -> {call['name']}({call['arguments']})")
    print("\n=== Final answer ===\n")
    print(state["final_answer"])


if __name__ == "__main__":
    asyncio.run(main())
