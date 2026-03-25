"""Phase 4.4.2 — delete_applications_for_user (CSV path)."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd


def test_delete_applications_for_user_csv():
    import services.application_tracker as at

    with TemporaryDirectory() as td:
        csv_path = Path(td) / "apps.csv"
        df = pd.DataFrame(
            [
                {"id": "1", "user_id": "alice", "job_id": "j1", "company": "A"},
                {"id": "2", "user_id": "bob", "job_id": "j2", "company": "B"},
            ]
        )
        df = df.reindex(columns=at.TRACKER_COLUMNS, fill_value="")
        df.to_csv(csv_path, index=False)

        with patch.object(at, "APPLICATION_FILE", csv_path):
            with patch.object(at, "USE_DB", False):
                with patch.dict(os.environ, {"TRACKER_USE_DB": "0"}, clear=False):
                    n = at.delete_applications_for_user("alice")
        assert n == 1
        left = pd.read_csv(csv_path)
        assert len(left) == 1
        assert str(left.iloc[0]["user_id"]) == "bob"
