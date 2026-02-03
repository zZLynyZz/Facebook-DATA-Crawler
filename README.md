# Facebook Full Data Scraper (Automated) 🚀
Bộ công cụ thu thập dữ liệu Facebook tự động hoàn toàn, tích hợp kỹ thuật bắt gói tin GraphQL để lấy chi tiết Bài viết, Bình luận và Cảm xúc (Reactions) từ các Fanpage mục tiêu.

# 📁 Cấu trúc dự án
main.py: File điều hướng chính, tự động chạy toàn bộ quy trình từ đầu đến cuối.

src/: Thư mục chứa các module xử lý logic riêng biệt:

login_fb.py: Quản lý đăng nhập và lưu session vào thư mục Profile.

get_posts.py: Thu thập bài viết (ID, Link, Nội dung, Thời gian...).

get_comments.py: Thu thập bình luận (User, Nội dung, Timestamp...).

get_reactions.py: Thu thập danh sách người thả cảm xúc (Like, Love, Haha...).

data/: Nơi chứa kết quả đầu ra dưới dạng file CSV.

profiles/: Lưu trữ dữ liệu trình duyệt để tránh phải đăng nhập lại nhiều lần.

# 🛠 Cài đặt nhanh
Cài đặt thư viện cần thiết:

pip install -r requirements.txt

Cài đặt trình duyệt đi kèm:

playwright install chromium

# 🚀 Quy trình sử dụng
# Bước 1: Khởi tạo Profile (Chỉ làm lần đầu)
Chạy module đăng nhập để lưu Cookie và Session:

python src/login_fb.py

Trình duyệt sẽ mở ra, bạn tiến hành đăng nhập Facebook thủ công.

Khi đã vào đến Newsfeed, hãy đóng trình duyệt để hệ thống xác nhận lưu Session thành công.

Lưu ý: Nên tạo acc clone để tránh mất acc

# Bước 2: Chạy quét dữ liệu tự động
Bạn chỉ cần chạy duy nhất file main.py để thực hiện chuỗi hành động khép kín:

python main.py
Quy trình sẽ tự động diễn ra như sau:

Quét Post: Lấy danh sách link bài viết từ Fanpage mục tiêu.

Quét Comment: Mở từng link bài viết, chuyển bộ lọc sang "Tất cả bình luận" và tự động cuộn để lấy dữ liệu.

Quét Reaction: Mở popup cảm xúc, tự động cuộn để bắt danh sách người dùng tương tác.

Bạn có thể chạy lần lượt từng file nếu muốn kiểm tra 

# 📊 Định dạng dữ liệu đầu ra (CSV)
Tất cả kết quả được lưu tại thư mục data/raw/ với định dạng UTF-8-SIG (giúp mở trực tiếp bằng Excel mà không bị lỗi font tiếng Việt):

posts_detail.csv: Thông tin tổng quan về các bài viết.

comments_detail.csv: Chi tiết nội dung bình luận của từng bài.

reactions_detail.csv: Danh sách chi tiết các loại cảm xúc của người dùng.

⚠️ Lưu ý an toàn (Tránh Checkpoint)
Cấu hình: Nên để SCROLL_DELAY từ 3 giây trở lên để giả lập thao tác người dùng.

Số lượng: Không nên quét quá 50 bài viết trong một lần chạy để đảm bảo an toàn cho tài khoản.

Bảo mật: Tuyệt đối không chia sẻ thư mục profiles/ cho người khác vì nó chứa quyền truy cập tài khoản Facebook của bạn.