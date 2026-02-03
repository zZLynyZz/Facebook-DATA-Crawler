import asyncio
import os
from src.login_fb import FacebookLogin
from src.get_posts import FacebookPostCrawler
from src.get_comments import FacebookCommentCrawler
from src.get_reactions import FacebookReactionCrawler

async def main():
    # 1. Khởi tạo cấu trúc thư mục cần thiết
    folders = ["data", "profiles"]
    for folder in folders:
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"📁 Đã tạo thư mục: {folder}")

    print("\n" + "="*50)
    print("🚀 BẮT ĐẦU QUY TRÌNH CRAWL DỮ LIỆU TỰ ĐỘNG")
    print("="*50)

    # Bước 1: Quét danh sách bài viết từ Fanpage
    print("\nSTEP 1: 📝 Đang quét danh sách bài viết...")
    post_bot = FacebookPostCrawler()
    await post_bot.run()

    # Bước 2: Quét bình luận (Comments) dựa trên file posts_detail.csv
    print("\nSTEP 2: 💬 Đang quét chi tiết bình luận...")
    comment_bot = FacebookCommentCrawler()
    await comment_bot.run()

    # Bước 3: Quét cảm xúc (Reactions) dựa trên file posts_detail.csv
    print("\nSTEP 3: ❤️ Đang quét chi tiết cảm xúc...")
    reaction_bot = FacebookReactionCrawler()
    await reaction_bot.run()

    print("\n" + "="*50)
    print("🎉 HOÀN THÀNH TOÀN BỘ QUY TRÌNH!")
    print(f"📍 Kết quả lưu tại: data/")
    print("="*50)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Chương trình đã được dừng bởi người dùng.")
    except Exception as e:
        print(f"\n❌ Có lỗi xảy ra trong quá trình vận hành: {e}")