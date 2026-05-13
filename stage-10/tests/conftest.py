"""pytest conftest — load .env, bridge API_KEY → OPENAI_API_KEY."""
import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

HERE = Path(__file__).parent
ROOT = HERE.parent

load_dotenv(ROOT / ".env")

# DeepEval (and openai SDK) read OPENAI_API_KEY; our .env uses API_KEY.
if not os.environ.get("OPENAI_API_KEY") and os.environ.get("API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.environ["API_KEY"]

os.environ.setdefault("JUDGE_MODEL", "gpt-4o-mini")


@pytest.fixture(scope="session")
def golden_dataset() -> list[dict]:
    with open(HERE / "golden_dataset.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return HERE / "fixtures"


@pytest.fixture(scope="session")
def judge_model() -> str:
    return os.environ["JUDGE_MODEL"]
