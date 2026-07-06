"""
Example: call the MCP tool servers directly (no LLM required).

Run from the repo root:

    PYTHONPATH=.:platform .venv/bin/python examples/tools_example.py
"""

import asyncio

from intelligence.mcp import get_registry


async def main() -> None:
    registry = get_registry()
    await registry.load()

    print("Discovered tools:")
    for schema in registry.ollama_tools():
        print(f"  - {schema['function']['name']}")

    print("\n--- Clinical NLP ---")
    out = await registry.execute(
        "extract_medical_entities",
        {"text": "Patient with diabetes and hypertension on metformin, presenting with chest pain."},
    )
    for entity in out["entities"]:
        print(f"  {entity['text']} ({entity['entity_type']})")

    print("\n--- Drug safety ---")
    out = await registry.execute(
        "check_drug_interactions", {"medications": ["warfarin", "aspirin", "metformin"]}
    )
    for interaction in out["interactions"]:
        print(f"  {' + '.join(interaction['pair'])}: {interaction['severity']} — {interaction['effect']}")

    print("\n--- Evidence retrieval (cited) ---")
    out = await registry.execute(
        "search_clinical_guidelines", {"query": "blood pressure target hypertension treatment"}
    )
    for result in out["results"]:
        print(f"  [{result['citation']}] score={result['score']}")


if __name__ == "__main__":
    asyncio.run(main())
