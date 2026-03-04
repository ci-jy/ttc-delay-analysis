import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import mini_dataset  # noqa: E402
from ttc_delay import pipeline  # noqa: E402


def _build(tmp_path_factory, name, writer):
    base = tmp_path_factory.mktemp(name)
    raw = writer(base / "raw")
    return pipeline.run(raw, ":memory:", base / "reports", base / "export"), base


@pytest.fixture(scope="session")
def mini_build(tmp_path_factory):
    return _build(tmp_path_factory, "mini", mini_dataset.write_mini)


@pytest.fixture(scope="session")
def mini(mini_build):
    return mini_build[0].con


@pytest.fixture(scope="session")
def ranking_con(tmp_path_factory):
    return _build(tmp_path_factory, "ranking", mini_dataset.write_ranking)[0].con
