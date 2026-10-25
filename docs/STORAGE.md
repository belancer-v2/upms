# File storage

All uploads (tenant documents, avatars, visitor and vehicle photos, agency documents, rental agreements) go through `backend/app/services/storage.py`. Callers pass relative keys such as `agencies/3/ab12.pdf`; keys that are absolute or contain `..` are refused.

`STORAGE_BACKEND=local` (default): files under `UPLOAD_DIR`, as before.
`STORAGE_BACKEND=s3`: any S3-compatible service (AWS S3, Cloudflare R2, MinIO, Backblaze B2). `pip install boto3` (imported only when used).

```
STORAGE_BACKEND=s3
S3_BUCKET=flatwise-private          # PRIVATE bucket, no public access, no public ACLs
S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com   # empty for AWS; http://minio:9000 for MinIO
S3_REGION=auto                      # R2: auto; AWS: e.g. ap-southeast-1
S3_ACCESS_KEY_ID=...  S3_SECRET_ACCESS_KEY=...
S3_PREFIX=                          # optional folder inside the bucket
S3_SSE=AES256                       # AES256 | aws:kms | empty (R2 encrypts at rest by itself and ignores it)
S3_SSE_KMS_KEY_ID=
S3_ADDRESSING=path                  # path | virtual
STORAGE_DOWNLOAD=proxy              # proxy | redirect
S3_URL_TTL=60                       # seconds a presigned URL lives
```
Downloads always pass through our authenticated endpoints first (same permission checks as before). `proxy` (default) then streams the bytes from the bucket, so the browser keeps working with its sign-in header exactly as today. `redirect` answers `302` to a presigned URL valid for `S3_URL_TTL` seconds (`Cache-Control: no-store`); use it for big files, and note the web app fetches photos with `fetch()`, so the bucket then needs a CORS rule allowing GET from your site.

Copy existing files: `cd backend && STORAGE_BACKEND=s3 S3_... python scripts/copy_uploads_to_s3.py [--dry-run] [--delete-local]`. Keys are unchanged, so the database needs no change; run it before switching the env, run it again after (it skips what is already there), and keep the local folder until you have checked a few downloads.

Back up the bucket (versioning or the provider's snapshot) as you would `UPLOAD_DIR`; `NID_KEY` is still needed to read NID numbers.
Tests: `tests/test_p3_storage.py` (LocalStorage, S3Storage against a fake client, the copy script, and a real upload route running on the fake bucket).
