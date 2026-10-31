import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "demo"))
from server import SAMPLES, sample_bytes, serve  # noqa: E402

from gomtai.core import Manager, category_for, filename_from_url


@pytest.fixture
def srv():
    s = serve(0, delay=0.005)
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


def test_category():
    assert category_for("a.MP4") == "Video"
    assert category_for("a.pdf") == "TaiLieu"
    assert category_for("a.unknown") == "Khac"
    assert filename_from_url("http://x/a%20b.zip?q=1") == "a b.zip"
    assert filename_from_url("http://x/") == "download"


def test_parallel_and_sort(srv, tmp_path):
    m = Manager(tmp_path, workers=3)
    m.add_many("\n".join(f"{srv}/{n}" for n in SAMPLES) + "\n# comment\n")
    assert m.wait(60)
    for t in m.tasks.values():
        assert t.status == "done", t.error
        with open(t.final_path, "rb") as f:
            assert f.read() == sample_bytes(t.filename)
    assert (tmp_path / "Video" / "phim-mau.mp4").exists()
    assert (tmp_path / "Khac" / "ghi-chu.xyz").exists()


def _pause_mid(m, t):
    while t.downloaded == 0:
        time.sleep(0.01)
    m.pause(t.id)
    while t.status == "downloading":
        time.sleep(0.01)
    assert t.status == "paused"
    return t.downloaded


def test_pause_resume_range(srv, tmp_path):
    m = Manager(tmp_path, workers=1)
    t = m.add(f"{srv}/phim-mau.mp4")
    got = _pause_mid(m, t)
    assert 0 < got < SAMPLES["phim-mau.mp4"]
    m.resume(t.id)
    assert m.wait(60)
    assert t.status == "done" and t.resumable is True
    assert open(t.final_path, "rb").read() == sample_bytes("phim-mau.mp4")


def test_resume_without_range_restarts(srv, tmp_path):
    m = Manager(tmp_path, workers=1)
    t = m.add(f"{srv}/norange/phim-mau.mp4")
    _pause_mid(m, t)
    m.resume(t.id)
    assert m.wait(60)
    assert t.status == "done" and t.resumable is False
    assert open(t.final_path, "rb").read() == sample_bytes("phim-mau.mp4")


def test_http_error_respected(srv, tmp_path):
    m = Manager(tmp_path, workers=1)
    a = m.add(f"{srv}/forbidden")
    b = m.add(f"{srv}/khong-co.bin")
    assert m.wait(30)
    assert a.status == "error" and "403" in a.error
    assert b.status == "error" and "404" in b.error


def test_rejects_non_http(tmp_path):
    m = Manager(tmp_path)
    with pytest.raises(ValueError):
        m.add("file:///etc/passwd")


def test_duplicate_names(srv, tmp_path):
    m = Manager(tmp_path, workers=2)
    m.add(f"{srv}/anh-chup.png"); m.add(f"{srv}/anh-chup.png")
    assert m.wait(30)
    assert sorted(os.listdir(tmp_path / "Anh")) == ["anh-chup (1).png", "anh-chup.png"]


def test_web_api(srv, tmp_path):
    from gomtai.web import create_app
    m = Manager(tmp_path, workers=2)
    c = create_app(m).test_client()
    assert "Gom tải" in c.get("/").get_data(as_text=True)
    r = c.post("/api/tasks", json={"links": f"{srv}/tai-lieu.pdf"})
    tid = r.get_json()[0]["id"]
    assert m.wait(30)
    assert c.get("/api/tasks").get_json()[0]["status"] == "done"
    assert c.post(f"/api/tasks/{tid}/explode").status_code == 404
    assert c.post("/api/tasks", json={"links": "ftp://x"}).status_code == 400
