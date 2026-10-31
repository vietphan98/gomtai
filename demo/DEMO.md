# Kịch bản demo 20–30 giây

Chuẩn bị: 2 terminal + trình duyệt, đã `source .venv/bin/activate`.

1. (0–4s) Terminal 1: `python demo/server.py --delay 0.05` – "Máy chủ mẫu chạy cục bộ, không cần mạng."
2. (4–8s) Terminal 2: `gomtai web -d /tmp/gomtai-demo`, mở http://127.0.0.1:8800.
3. (8–13s) Dán 6 dòng trong `demo/links.txt`, bấm **Thêm vào hàng đợi** → 3 file chạy song song, mỗi file một thanh tiến độ.
4. (13–20s) Bấm **Tạm dừng** ở `phim-mau.mp4`, chờ 1–2 giây, bấm **Tiếp tục** → thanh chạy tiếp từ chỗ cũ (dòng chữ "hỗ trợ Range").
5. (20–27s) Khi tất cả "Hoàn tất", chạy `ls /tmp/gomtai-demo/*` → thấy các thư mục Video, Nhac, Anh, TaiLieu, NenCo, Khac.
6. (27–30s) Màn hình cuối: `github.com/vietphan98/gomtai`, MIT.

Muốn quay lại từ đầu: `rm -rf /tmp/gomtai-demo`.

## Hook Reel

"Dán một lúc nhiều link, tải song song, dừng giữa chừng rồi tải tiếp đúng chỗ cũ – file xong tự vào đúng thư mục. Mã nguồn mở, viết bằng Python."
