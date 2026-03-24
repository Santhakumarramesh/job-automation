"""Resume path fallback (deterministic master PDF selection)."""

from pathlib import Path


def test_pick_fallback_prefers_env(tmp_path, monkeypatch):
    from services.resume_naming import pick_fallback_resume_pdf

    explicit = tmp_path / "from_env.pdf"
    explicit.write_bytes(b"%PDF-1.4")
    other = tmp_path / "Master_Resumes" / "master.pdf"
    other.parent.mkdir()
    other.write_bytes(b"%PDF-1.4")

    monkeypatch.setenv("MASTER_RESUME_PDF", str(explicit))
    monkeypatch.delenv("DEFAULT_RESUME_PDF", raising=False)
    assert pick_fallback_resume_pdf(tmp_path) == explicit


def test_pick_fallback_prefers_name_hint_in_master_dir(tmp_path, monkeypatch):
    from services.resume_naming import pick_fallback_resume_pdf

    monkeypatch.delenv("MASTER_RESUME_PDF", raising=False)
    monkeypatch.delenv("DEFAULT_RESUME_PDF", raising=False)
    md = tmp_path / "Master_Resumes"
    md.mkdir()
    (md / "zzz_other.pdf").write_bytes(b"%PDF-1.4")
    (md / "aaa_master.pdf").write_bytes(b"%PDF-1.4")

    got = pick_fallback_resume_pdf(tmp_path)
    assert got is not None
    assert "master" in got.name.lower()


def test_pick_fallback_lexicographic_when_no_hint(tmp_path, monkeypatch):
    from services.resume_naming import pick_fallback_resume_pdf

    monkeypatch.delenv("MASTER_RESUME_PDF", raising=False)
    monkeypatch.delenv("DEFAULT_RESUME_PDF", raising=False)
    md = tmp_path / "Master_Resumes"
    md.mkdir()
    (md / "zebra.pdf").write_bytes(b"%PDF-1.4")
    (md / "apple.pdf").write_bytes(b"%PDF-1.4")

    assert pick_fallback_resume_pdf(tmp_path) == md / "apple.pdf"


def test_ensure_resume_uses_fallback(tmp_path, monkeypatch):
    from services import resume_naming as rn

    monkeypatch.delenv("MASTER_RESUME_PDF", raising=False)
    monkeypatch.delenv("DEFAULT_RESUME_PDF", raising=False)
    md = tmp_path / "Master_Resumes"
    md.mkdir()
    (md / "master.pdf").write_bytes(b"%PDF-1.4")

    job = {"company": "Acme", "title": "Engineer", "position": "Engineer"}
    out = rn.ensure_resume_exists_for_job(job, output_dir=str(tmp_path / "out"), candidate_name="Test User")
    assert out
    assert Path(out).exists()
    assert Path(out).name.endswith(".pdf")
