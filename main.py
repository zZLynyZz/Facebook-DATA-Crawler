import asyncio
import os

# Import tất cả các Class từ thư mục src (nhờ file __init__.py)
from src import (
    FacebookLogin,
    FacebookPostCrawler,
    FacebookCommentCrawler,
    FacebookReactionCrawler
)

# ==========================================
# CẤU HÌNH TẬP TRUNG TẠI ĐÂY
# ==========================================
TARGET_PAGE = "https://www.facebook.com/abcxyz" # Fanpage cần lấy dữ liệu
POST_LIMIT = 10                                    # Số lượng bài muốn lấy
DO_LOGIN = True                                    # Mở bước login trước
# ==========================================

async def main():
    # Tạo thư mục data/raw nếu chưa tồn tại
    os.makedirs("data/raw", exist_ok=True)

    print(f"🚀 [BẮT ĐẦU] Mục tiêu: {TARGET_PAGE}")

    # Bước 0: Kiểm tra đăng nhập (Xác nhận Profile)
    if DO_LOGIN:
        print("\n[STEP 0] Đang check Login...")
        # Bạn cần tắt trình duyệt thủ công sau khi login để chạy tiếp
        await FacebookLogin().run()

    # Bước 1: Quét bài viết (Truyền tham số Link và Limit vào)
    print("\n[STEP 1] Đang lấy danh sách bài viết...")
    post_bot = FacebookPostCrawler(target_url=TARGET_PAGE, max_posts=POST_LIMIT)
    await post_bot.run()

    # Bước 2: Quét bình luận (Sử dụng danh sách từ posts_detail.csv)
    print("\n[STEP 2] Đang lấy bình luận chi tiết...")
    await FacebookCommentCrawler().run()

    # Bước 3: Quét cảm xúc (Sử dụng danh sách từ posts_detail.csv)
    print("\n[STEP 3] Đang lấy cảm xúc người dùng...")
    await FacebookReactionCrawler().run()

    print("\n" + "="*40)
    print("🎉 TẤT CẢ QUY TRÌNH ĐÃ HOÀN TẤT!")
    print("="*40)

if __name__ == "__main__":
    try:
        asyncio.run(main()) # Thực thi luồng chính
    except KeyboardInterrupt:
        print("\n🛑 Đã dừng tool.") # Xử lý khi bấm Ctrl+C