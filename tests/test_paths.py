import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = """
from procintel.answering import retrieve
from procintel.api import config
from procintel.ingestion import wb_client
from procintel.jobs import store
from procintel.learning import feedback
from procintel.prediction import predict
print(retrieve.DB_PATH, feedback.DB_PATH, store.DB_PATH, config.SAVED, predict.MODEL_PATH.parent, wb_client.CACHE_DIR, sep="\\n")
"""


def test_every_data_file_follows_the_data_dir_setting(tmp_path):
    env = {**os.environ, "PROCINTEL_DATA_DIR": str(tmp_path), "PYTHONPATH": str(ROOT / "src")}
    out = subprocess.run([sys.executable, "-c", CHECK], env=env, capture_output=True, text=True, check=True).stdout.split()
    assert out and all(Path(p).is_relative_to(tmp_path) for p in out), out


def test_no_module_builds_a_data_path_from_its_own_location():
    offenders = [p.name for p in (ROOT / "src" / "procintel").rglob("*.py")
                 if p.name != "paths.py" and "parents[" in p.read_text()]
    assert offenders == []
