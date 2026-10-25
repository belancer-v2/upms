import io

import pytest
from fastapi import HTTPException

from app.services import storage as S
from conftest import login
from test_property import prop_headers


class FakeS3:
    """Just enough of the boto3 client."""

    class Err(Exception):
        def __init__(self, code):
            self.response = {"Error": {"Code": code}}

    def __init__(self):
        self.objs, self.calls = {}, []

    def put_object(self, **kw):
        self.calls.append(("put", kw))
        self.objs[kw["Key"]] = kw["Body"]

    def get_object(self, Bucket, Key):
        if Key not in self.objs:
            raise self.Err("NoSuchKey")
        return {"Body": io.BytesIO(self.objs[Key])}

    def head_object(self, Bucket, Key):
        if Key not in self.objs:
            raise self.Err("404")

    def delete_object(self, Bucket, Key):
        self.objs.pop(Key, None)

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://s3.example/{Params['Bucket']}/{Params['Key']}?exp={ExpiresIn}&ct={Params.get('ResponseContentType', '')}"

    def list_objects_v2(self, Bucket, Prefix="", **kw):
        return {"Contents": [{"Key": k} for k in self.objs if k.startswith(Prefix)], "IsTruncated": False}


def test_key_cleaning_blocks_traversal():
    for bad in ("../x", "/etc/passwd", "a/../../b", ""):
        with pytest.raises(ValueError):
            S.clean_key(bad)
    assert S.clean_key("a\\b/c.png") == "a/b/c.png"


def test_local_storage_roundtrip(tmp_path):
    st = S.LocalStorage(tmp_path)
    st.put("agencies/1/a.pdf", b"hello", "application/pdf")
    assert st.exists("agencies/1/a.pdf") and st.get("agencies/1/a.pdf") == b"hello"
    assert st.iter_keys() == ["agencies/1/a.pdf"]
    r = st.serve("agencies/1/a.pdf", "application/pdf", "doc.pdf")
    assert r.media_type == "application/pdf"
    st.delete("agencies/1/a.pdf")
    st.delete("agencies/1/a.pdf")        # missing is fine
    assert not st.exists("agencies/1/a.pdf")
    with pytest.raises(FileNotFoundError):
        st.get("agencies/1/a.pdf")
    with pytest.raises(HTTPException) as e:
        st.serve("nope", "image/png")
    assert e.value.status_code == 404


def test_s3_storage_with_fake_client():
    c = FakeS3()
    st = S.S3Storage("bkt", client=c, prefix="fw", sse="aws:kms", sse_kms_key_id="k1")
    st.put("rental/2/x.png", b"png", "image/png")
    kw = c.calls[0][1]
    assert kw["Key"] == "fw/rental/2/x.png" and kw["ServerSideEncryption"] == "aws:kms" and kw["SSEKMSKeyId"] == "k1" and kw["ContentType"] == "image/png"
    assert st.exists("rental/2/x.png") and st.get("rental/2/x.png") == b"png" and not st.exists("rental/2/none.png")
    assert st.iter_keys() == ["rental/2/x.png"]
    r = st.serve("rental/2/x.png", "image/png", "pic.png")       # proxy mode streams the bytes
    assert r.body == b"png" and "pic.png" in r.headers["content-disposition"]
    st.download = "redirect"
    r = st.serve("rental/2/x.png", "image/png")
    assert r.status_code == 302 and r.headers["location"].startswith("https://s3.example/bkt/fw/rental/2/x.png?exp=60") and r.headers["cache-control"] == "no-store"
    with pytest.raises(HTTPException):
        st.serve("rental/2/missing.png", "image/png")
    st.delete("rental/2/x.png")
    assert not st.exists("rental/2/x.png")
    with pytest.raises(FileNotFoundError):
        st.get("rental/2/x.png")


def test_s3_without_bucket_is_an_error():
    with pytest.raises(RuntimeError):
        S.S3Storage("", client=FakeS3())


def test_copy_script_is_idempotent(tmp_path):
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location("copy_uploads", pathlib.Path(__file__).parent.parent / "scripts" / "copy_uploads_to_s3.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    src = S.LocalStorage(tmp_path)
    src.put("a/1.png", b"1")
    src.put("b/2.pdf", b"22")
    dst = S.S3Storage("bkt", client=FakeS3())
    assert m.copy(src, dst, log=lambda *_: None) == {"copied": 2, "skipped": 0, "failed": 0, "deleted": 0}
    assert m.copy(src, dst, log=lambda *_: None)["skipped"] == 2
    assert m.copy(src, dst, delete_local=True, log=lambda *_: None)["deleted"] == 2 and src.iter_keys() == []
    assert dst.get("b/2.pdf") == b"22"


def test_uploads_work_through_the_s3_backend(client, monkeypatch):
    """An existing upload route, with storage swapped for a fake bucket: same API answers."""
    fake = S.S3Storage("bkt", client=FakeS3())
    monkeypatch.setattr(S, "OVERRIDE", fake)
    h = prop_headers(client, "padmin")
    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")
    uid = login(client, "padmin")[1]["user"]["id"]
    r = client.post(f"/api/profiles/user/{uid}/photo", files={"file": ("a.png", png, "image/png")}, headers=h)
    assert r.status_code == 200, r.text
    assert any(k.startswith("avatars/user_") for k in fake.client.objs)
    g = client.get(f"/api/profiles/user/{uid}/photo", headers=h)
    assert g.status_code == 200 and g.content == png and g.headers["content-type"] == "image/png"
    client.delete(f"/api/profiles/user/{uid}/photo", headers=h)
    assert not any(k.startswith("avatars/user_") for k in fake.client.objs)
