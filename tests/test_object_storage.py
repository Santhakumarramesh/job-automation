"""Phase 3.4 object storage helpers (no real AWS calls)."""

import json
from unittest.mock import MagicMock, patch


def test_merge_manifest_json_empty_then_fragment():
    from services.object_storage import merge_manifest_json

    frag = {"resume": {"bucket": "b", "key": "artifacts/u/j/resume.pdf"}}
    s = merge_manifest_json(None, frag)
    d = json.loads(s)
    assert d["s3"]["resume"]["bucket"] == "b"
    assert d["s3"]["resume"]["key"] == "artifacts/u/j/resume.pdf"


def test_merge_manifest_json_preserves_top_level():
    from services.object_storage import merge_manifest_json

    existing = json.dumps({"run_id": "r1", "s3": {}})
    frag = {"cover_letter": {"bucket": "b", "key": "k"}}
    s = merge_manifest_json(existing, frag)
    d = json.loads(s)
    assert d["run_id"] == "r1"
    assert d["s3"]["cover_letter"]["key"] == "k"


def test_upload_artifacts_from_state_noop_without_bucket():
    from services.object_storage import upload_artifacts_from_state

    frag = upload_artifacts_from_state(
        {
            "user_id": "u1",
            "job_id": "j1",
            "final_pdf_path": "/nope/not-a-real-file.pdf",
        }
    )
    assert frag == {}


def test_presign_artifact_manifest_nested_s3_block():
    import services.object_storage as obs
    from services.object_storage import presign_artifact_manifest

    manifest = {"s3": {"resume": {"bucket": "myb", "key": "myk"}}}
    mock_cli = MagicMock()
    mock_cli.generate_presigned_url.return_value = "https://example.com/signed"
    with patch.object(obs, "_s3_client", return_value=mock_cli):
        out = presign_artifact_manifest(manifest, expires_seconds=120)
        assert out["resume"] == "https://example.com/signed"
        mock_cli.generate_presigned_url.assert_called_once()
        _, kwargs = mock_cli.generate_presigned_url.call_args
        assert kwargs["ExpiresIn"] == 120


def test_presign_expires_clamped():
    import services.object_storage as obs
    from services.object_storage import presign_artifact_manifest

    manifest = {"resume": {"bucket": "b", "key": "k"}}
    mock_cli = MagicMock()
    mock_cli.generate_presigned_url.return_value = "u"
    with patch.object(obs, "_s3_client", return_value=mock_cli):
        presign_artifact_manifest(manifest, expires_seconds=999999)
        _, kwargs = mock_cli.generate_presigned_url.call_args
        assert kwargs["ExpiresIn"] == 604800
