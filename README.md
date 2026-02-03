FB Data Crawler (Playwright) 🚀
Bộ công cụ thu thập dữ liệu Facebook (Posts, Comments, Reactions) sử dụng Playwright và kỹ thuật Network Intercepting để lấy dữ liệu chính xác từ GraphQL. Dự án phục vụ mục đích phân tích dữ liệu và nghiên cứu thị trường.



📁 Cấu trúc thư mục
Plaintext
FB_DATA_CRAWLER/
├── data/               # Nơi lưu trữ file kết quả (CSV)
├── profiles/           # Lưu trữ Session/Cookie (Tránh login lại nhiều lần)
├── src/                # Mã nguồn các module xử lý
│   ├── __init__.py     # Khai báo package
│   ├── login_fb.py     # Module đăng nhập và khởi tạo Profile
│   ├── get_posts.py    # Module quét bài viết từ Page
│   ├── get_comments.py # Module quét bình luận từ danh sách bài viết
│   └── get_reactions.py# Module quét cảm xúc (Hỗ trợ thủ công)
├── main.py             # File điều hướng chạy toàn bộ quy trình
└── requirements.txt    # Danh sách thư viện cần thiết




🛠 Cài đặt
Cài đặt Python: Đảm bảo bạn đã cài Python 3.8+.

Cài đặt thư viện:

pip install -r requirements.txt
Cài đặt trình duyệt Playwright:


playwright install chromium
📖 Hướng dẫn sử dụng
Bước 1: Khởi tạo Profile (Đăng nhập)
Trước khi crawl, bạn cần chạy module login để Facebook lưu lại phiên đăng nhập vào thư mục profiles.

Lưu ý: Nên đăng nhập bằng acc clone để tránh bị bay acc

python src/login_fb.py
Trình duyệt sẽ mở ra, bạn đăng nhập FB và vượt qua 2FA (nếu có).

Khi thấy Newsfeed hiện lên, hãy đóng trình duyệt để lưu Session.

Bước 2: Chạy quy trình tổng thể
Chỉnh sửa cấu hình (Target URL, Max Posts...) trong các file tương ứng trong src/, sau đó chạy:

python main.py
⚠️ Lưu ý quan trọng cho từng Module
1. Quét bài viết (get_posts.py)
Dữ liệu được lấy trực tiếp từ gói tin GraphQL nên rất sạch.

Mặc định loại bỏ các bài viết dạng Share và Video để tối ưu cho phân tích văn bản.
(Có thể thay đổi số lượng bài viết giới hạn)
(Nếu thích có thể thay đổi các loại bài viết Share hoặc Video ở trong file)

2. Quét bình luận (get_comments.py)
Tự động chuyển bộ lọc sang "Tất cả bình luận" để không bỏ sót dữ liệu.

Tự động cuộn đến khi hết bình luận.

3. Quét cảm xúc (get_reactions.py) - Thao tác thủ công
Do cơ chế bảo mật của Facebook đối với danh sách Reaction rất cao, module này yêu cầu sự hỗ trợ thủ công để đảm bảo an toàn cho tài khoản:

Script sẽ tự động mở link bài viết.

Người dùng thực hiện: Click chuột vào biểu tượng/số lượng cảm xúc để mở popup danh sách người tương tác.

Người dùng thực hiện: Cuộn danh sách (scroll) trong popup bằng tay.

Hệ thống: Script sẽ tự động "bắt" các gói tin trả về khi bạn cuộn và ghi dữ liệu vào reactions_detail.csv theo thời gian thực.

📊 Định dạng dữ liệu đầu ra
Dữ liệu được lưu tại data/ dưới định dạng CSV (UTF-8-SIG), có thể mở trực tiếp bằng Excel mà không bị lỗi font:

Post ID: Định dạng POST_001, POST_002...

User ID: Luôn có tiền tố FB_ (VD: FB_100012345678).

Content: Nội dung văn bản đã được làm sạch xuống dòng.

🛡 Chính sách sử dụng
Công cụ này chỉ nên sử dụng cho mục đích học tập và nghiên cứu.

Không nên lạm dụng quét quá nhiều yêu cầu trong thời gian ngắn để tránh bị khóa tài khoản (Checkpoint).