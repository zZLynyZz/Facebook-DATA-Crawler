import asyncio
import os
from playwright.async_api import async_playwright

# --- CẤU HÌNH ---
# Tên profile (Giữ nguyên tên này cho các file khác dùng chung)
CURRENT_PROFILE_NAME = "acc_clone_1" 

class FacebookLogin:
    def __init__(self):
        # Đường dẫn lưu Profile (Cookies, LocalStorage...)
        self.user_data_dir = os.path.join(os.getcwd(), "profiles", CURRENT_PROFILE_NAME)
        os.makedirs(self.user_data_dir, exist_ok=True)

    async def run(self):
        print(f"🚀 Đang khởi tạo Profile tại: {self.user_data_dir}")
        print("⚠️ HƯỚNG DẪN: Trình duyệt sẽ mở ra.")
        print("   1. Nhập User/Pass và đăng nhập Facebook.")
        print("   2. Nếu có 2FA, hãy nhập mã.")
        print("   3. Khi nào thấy Newsfeed (Trang chủ) hiện ra thì tắt trình duyệt.")
        
        async with async_playwright() as p:
            # Mở trình duyệt với Profile cố định
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=False, # Phải hiện trình duyệt để bạn nhập
                viewport={"width": 1280, "height": 900},
                args=["--disable-notifications"]
            )
            page = context.pages[0]
            
            # Vào trang chủ FB
            await page.goto("https://www.facebook.com/")
            
            # Treo máy chờ bạn thao tác
            # Chúng ta dùng vòng lặp vô tận, khi bạn đóng trình duyệt thì code sẽ tự ngắt
            try:
                await page.wait_for_timeout(9999999) 
            except:
                print("\n✅ Đã đóng trình duyệt. Cookie và Session đã được lưu!")

if __name__ == "__main__":
    bot = FacebookLogin()
    asyncio.run(bot.run())