# Object storage (S3) — Phase 3.4

Optional uploads for generated PDFs (Celery pipeline) and **presigned download URLs** on the tracker API.

## Install

```bash
pip install .[s3]
```

Uses the default AWS credential chain (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, IAM role, etc.).

## Environment

| Variable | Purpose |
|----------|---------|
| `ARTIFACTS_S3_BUCKET` | Enable uploads when set (bucket name). |
| `ARTIFACTS_S3_PREFIX` | Key prefix (default `artifacts`). |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | S3 client region (default `us-east-1`). |
| `ARTIFACTS_PRESIGN_EXPIRES` | Presigned URL lifetime in seconds (default `3600`, max `604800`). |
| `ARTIFACTS_S3_SSE` | Optional `AES256` for server-side encryption on `upload_file`. |

## Behavior

1. **Celery `run_job`** — After `save_documents`, if `ARTIFACTS_S3_BUCKET` is set and `boto3` is installed, resume and cover letter files are uploaded to  
   `{prefix}/{user_id}/{job_id}/resume.pdf` (and `cover_letter.pdf`).  
   Keys are stored under `artifacts_manifest` as JSON:  
   `{"s3": {"resume": {"bucket","key"}, "cover_letter": {...}}, ...}`.

2. **API** — `GET /api/applications/by-job/{job_id}?signed_urls=true` (and the admin variant) adds an `artifacts.signed_urls` map when the manifest contains `s3` entries and signing succeeds.

## SQLite / Postgres

`artifacts_manifest` is a text/JSON column on tracker rows (same as Phase 3.2.3). Large manifests may truncate at the DB cell limit (see `tracker_db._cell`).

## GCS / MinIO

Native GCS is not implemented. For **S3-compatible** APIs (MinIO, etc.), configure the AWS SDK endpoint (e.g. `AWS_ENDPOINT_URL` with recent boto3) or use a compatibility layer.

## Retention

Lifecycle rules (expiration, Intelligent-Tiering) are configured on the **bucket** — not in this application. See also [DATA_RETENTION.md](DATA_RETENTION.md).

### Example: expire old artifact objects (AWS S3)

Artifacts use keys like `{ARTIFACTS_S3_PREFIX}/{user_id}/{job_id}/resume.pdf`. A common pattern is to delete or transition objects under that prefix after **N** days.

**AWS CLI** (`lifecycle.json`):

```json
{
  "Rules": [
    {
      "ID": "expire-artifacts-after-400d",
      "Status": "Enabled",
      "Filter": { "Prefix": "artifacts/" },
      "Expiration": { "Days": 400 }
    }
  ]
}
```

Apply (replace `your-bucket`):

```bash
aws s3api put-bucket-lifecycle-configuration --bucket your-bucket --lifecycle-configuration file://lifecycle.json
```

Adjust the prefix to match `ARTIFACTS_S3_PREFIX` (default `artifacts/`). For **versioned** buckets, add `NoncurrentVersionExpiration` if you enable versioning.

**Terraform** (illustrative):

```hcl
resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.app.id
  rule {
    id     = "expire-artifacts"
    status = "Enabled"
    filter { prefix = "artifacts/" }
    expiration { days = 400 }
  }
}
```

**MinIO / S3-compatible:** use the vendor’s lifecycle or ILM API; semantics mirror S3-style rules when the backend supports them.
