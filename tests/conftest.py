import os
import shutil
import tempfile
import pytest
from src.aura_memory.db import AuraMemoryDB

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="aura_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def temp_db(temp_dir):
    db_path = os.path.join(temp_dir, "test_aura.db")
    return AuraMemoryDB(db_path=db_path)
