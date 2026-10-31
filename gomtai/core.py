"""Lõi tải file: hàng đợi, tải song song, tạm dừng/tiếp tục, phân loại thư mục.

Không vượt qua bất kỳ cơ chế chặn/bảo vệ nào: lỗi HTTP (403, 404, 429...) được
ghi nhận là lỗi và dừng lại, không thử lách.
"""
from __future__ import annotations

import os
import queue
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field

CATEGORIES = {
    "Video": {".mp4", ".mkv", ".webm", ".mov", ".avi"},
    "Nhac": {".mp3", ".flac", ".wav", ".ogg", ".m4a"},
    "Anh": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"},
    "TaiLieu": {".pdf", ".doc", ".docx", ".txt", ".md", ".csv", ".xlsx", ".pptx"},
    "NenCo": {".zip", ".rar", ".7z", ".tar", ".gz", ".xz"},
    "ChuongTrinh": {".exe", ".msi", ".deb", ".dmg", ".appimage", ".apk"},
}
OTHER = "Khac"
CHUNK = 64 * 1024
USER_AGENT = "gomtai/0.1 (+https://github.com/vietphan98/gomtai)"


def category_for(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    for name, exts in CATEGORIES.items():
        if ext in exts:
            return name
    return OTHER


def filename_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    name = os.path.basename(urllib.parse.unquote(path)) or "download"
    name = name.replace("/", "_").replace("\\", "_").strip(". ") or "download"
    return name


def unique_path(path: str) -> str:
    base, ext = os.path.splitext(path)
    i, out = 1, path
    while os.path.exists(out):
        out = f"{base} ({i}){ext}"
        i += 1
    return out


@dataclass
class Task:
    url: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    filename: str = ""
    status: str = "queued"  # queued, downloading, paused, done, error
    downloaded: int = 0
    total: int | None = None
    resumable: bool | None = None
    error: str = ""
    final_path: str = ""

    def __post_init__(self):
        self.filename = self.filename or filename_from_url(self.url)
        self._pause = threading.Event()

    @property
    def progress(self) -> float | None:
        if self.total:
            return min(1.0, self.downloaded / self.total)
        return None

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in (
            "id", "url", "filename", "status", "downloaded", "total",
            "resumable", "error", "final_path")} | {"progress": self.progress}


class Manager:
    def __init__(self, dest: str, workers: int = 3, timeout: float = 30):
        self.dest = os.path.abspath(dest)
        self.tmp = os.path.join(self.dest, ".partial")
        os.makedirs(self.tmp, exist_ok=True)
        self.timeout = timeout
        self.tasks: dict[str, Task] = {}
        self._q: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._threads = [threading.Thread(target=self._worker, daemon=True)
                         for _ in range(max(1, workers))]
        for t in self._threads:
            t.start()

    # ---- API công khai ----
    def add(self, url: str) -> Task:
        url = url.strip()
        if urllib.parse.urlparse(url).scheme not in ("http", "https"):
            raise ValueError(f"Chỉ hỗ trợ http/https: {url!r}")
        task = Task(url)
        with self._lock:
            self.tasks[task.id] = task
        self._q.put(task.id)
        return task

    def add_many(self, text: str) -> list[Task]:
        out = []
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(self.add(line))
        return out

    def pause(self, task_id: str) -> None:
        t = self.tasks[task_id]
        if t.status in ("queued", "downloading"):
            t._pause.set()
            if t.status == "queued":
                t.status = "paused"

    def resume(self, task_id: str) -> None:
        t = self.tasks[task_id]
        if t.status in ("paused", "error"):
            t._pause.clear()
            t.error = ""
            t.status = "queued"
            self._q.put(t.id)

    def wait(self, timeout: float | None = None) -> bool:
        """Chờ đến khi không còn task đang chờ/đang tải. Trả về True nếu xong."""
        import time
        end = None if timeout is None else time.monotonic() + timeout
        while any(t.status in ("queued", "downloading") for t in self.tasks.values()):
            if end is not None and time.monotonic() > end:
                return False
            time.sleep(0.05)
        return True

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [t.to_dict() for t in self.tasks.values()]

    # ---- nội bộ ----
    def _worker(self):
        while True:
            tid = self._q.get()
            task = self.tasks.get(tid)
            if task is None or task.status != "queued":
                continue
            if task._pause.is_set():
                task.status = "paused"
                continue
            try:
                self._download(task)
            except Exception as e:  # ghi lỗi, không thử lách
                task.status = "error"
                task.error = str(e)

    def _part_path(self, task: Task) -> str:
        return os.path.join(self.tmp, f"{task.id}.part")

    def _download(self, task: Task):
        task.status = "downloading"
        part = self._part_path(task)
        have = os.path.getsize(part) if os.path.exists(part) else 0
        headers = {"User-Agent": USER_AGENT}
        if have:
            headers["Range"] = f"bytes={have}-"
        req = urllib.request.Request(task.url, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            if e.code == 416 and have and task.total == have:
                resp = None  # đã đủ
            else:
                raise RuntimeError(f"HTTP {e.code} {e.reason}") from None
        if resp is not None:
            with resp:
                status = resp.status
                length = resp.headers.get("Content-Length")
                if status == 206:
                    task.resumable = True
                    mode = "ab"
                    cr = resp.headers.get("Content-Range", "")
                    if "/" in cr and cr.rsplit("/", 1)[1].isdigit():
                        task.total = int(cr.rsplit("/", 1)[1])
                elif status == 200:
                    # Máy chủ không hỗ trợ Range: tải lại từ đầu.
                    task.resumable = resp.headers.get("Accept-Ranges", "").lower() == "bytes"
                    mode, have = "wb", 0
                    task.total = int(length) if length and length.isdigit() else None
                else:
                    raise RuntimeError(f"HTTP {status} không mong đợi")
                task.downloaded = have
                with open(part, mode) as f:
                    while True:
                        if task._pause.is_set():
                            task.status = "paused"
                            return
                        chunk = resp.read(CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        task.downloaded += len(chunk)
            if task.total is not None and task.downloaded < task.total:
                raise RuntimeError("Kết nối bị ngắt trước khi tải xong")
        folder = os.path.join(self.dest, category_for(task.filename))
        os.makedirs(folder, exist_ok=True)
        final = unique_path(os.path.join(folder, task.filename))
        shutil.move(part, final)
        task.final_path = final
        task.total = task.total or task.downloaded
        task.status = "done"
