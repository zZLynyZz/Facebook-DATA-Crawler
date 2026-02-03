import asyncio
import json
import csv
import os
import base64
import re
import random
from playwright.async_api import async_playwright

# ==============================================================================
# 1. PHẦN CẤU HÌNH (CONFIGURATION)
# ==============================================================================
TARGET_URL = "https://www.facebook.com/abcxyz"  # Link Page cần lấy
OUTPUT_FILE = 'data/posts_detail.csv'              # Tên file xuất ra
CURRENT_PROFILE_NAME = "acc_clone_1"                   # Tên Profile Chrome

MAX_POSTS = 5        # Số lượng bài viết tối đa muốn lấy
SCROLL_DELAY = 3      # Thời gian nghỉ (giây) giữa các lần cuộn
MAX_RETRIES = 5       # Số lần thử cuộn lại nếu không thấy bài mới

class FacebookPostCrawler:
    def __init__(self):
        """
        Khởi tạo Class:
        - Thiết lập đường dẫn file.
        - Tạo file CSV mới và ghi sẵn hàng tiêu đề.
        """
        self.output_path = os.path.join(os.getcwd(), OUTPUT_FILE)
        self.user_data_dir = os.path.join(os.getcwd(), "profiles", CURRENT_PROFILE_NAME)
        
        self.post_counter = 0        # Biến đếm số bài (để tạo POST_001...)
        self.captured_fb_ids = set() # Bộ nhớ tạm (Set) để lọc các bài trùng lặp
        
        # Tạo thư mục lưu data nếu chưa có
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        
        # [CẬP NHẬT] Header chuẩn hóa:
        # - post_id: ID nội bộ (POST_001) dùng để liên kết các file khác
        # - post_fb_id: ID gốc của Facebook
        self.headers = [
            "post_id",          # POST_001
            "user_id",          # FB_1000xxxxx
            "social_user",      # Tên người đăng
            "context_content",  # Nội dung bài viết
            "post_link",        # Link bài viết
            "post_fb_id"        # 123456789 (ID gốc)
        ]
        
        # Mở file và ghi dòng tiêu đề ngay lập tức
        with open(self.output_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(self.headers)
            
        print(f"🧹 [INIT] Đã tạo file sạch: {OUTPUT_FILE}")
        print("🚫 [RULE] Chế độ lọc: BỎ Unknown User, BỎ Share, BỎ Video")

    # ==========================================================================
    # CÁC HÀM HỖ TRỢ (HELPER FUNCTIONS)
    # ==========================================================================

    def extract_numeric_id(self, base64_id):
        """
        Giải mã ID dạng Base64 (UzpfS...) sang ID số (12345...)
        Facebook API thường trả về ID đã mã hóa, cần giải mã để dùng được.
        """
        if not base64_id: return None
        try:
            # Nếu đã là số thì trả về luôn
            if re.match(r'^\d+$', str(base64_id)): return str(base64_id)
            
            # Giải mã Base64
            decoded_bytes = base64.b64decode(base64_id)
            decoded_str = decoded_bytes.decode('utf-8')
            
            # Lấy chuỗi số cuối cùng trong chuỗi giải mã
            match = re.search(r'(\d+)$', decoded_str)
            if match: return match.group(1)
        except: pass
        return None

    def get_text_content(self, node):
        """
        Đào sâu vào cấu trúc JSON để lấy nội dung văn bản (Caption) của bài viết.
        """
        content = ""
        try: 
            # Cấu trúc phổ biến (Comet UI)
            content = node['comet_sections']['content']['story']['message']['text']
        except:
            try: 
                # Cấu trúc dự phòng
                content = node['message']['text']
            except: pass
        # Xóa xuống dòng thừa để file CSV gọn gàng
        return content.replace("\n", " ").strip() if content else ""

    def get_author_info(self, node):
        """
        Lấy Tên và ID gốc của người đăng bài.
        """
        uid, name = "Unknown", "Unknown"
        # Cách 1: Tìm trong 'actors' (Thường dùng cho Page)
        try:
            actors = node['comet_sections']['context_layout']['story']['actors']
            if actors:
                uid = actors[0].get('id', 'Unknown')
                name = actors[0].get('name', 'Unknown')
                return uid, name
        except: pass
        
        # Cách 2: Tìm trong 'owning_profile'
        try:
            profile = node['feedback']['owning_profile']
            if profile:
                uid = profile.get('id', 'Unknown')
                name = profile.get('name', 'Unknown')
        except: pass
        
        return uid, name

    def determine_post_type(self, node):
        """
        Xác định loại bài viết: Share, Video hay Status/Photo?
        Dùng để lọc bớt dữ liệu rác/khó xử lý.
        """
        # 1. Kiểm tra bài Share (Chia sẻ lại bài khác)
        try:
            if node['comet_sections']['content']['story']['attached_story']: return "Share"
        except: pass
        try:
             if 'shareable' in node and node['shareable']['__typename'] == 'EntityShareable': return "Share"
        except: pass

        # 2. Kiểm tra Video trong phần đính kèm (Attachments)
        attachments = []
        try: attachments = node['comet_sections']['content']['story']['attachments']
        except:
            try: attachments = node['attachments']
            except: pass

        if attachments:
            for att in attachments:
                # Kiểm tra các dấu hiệu của Video
                try:
                    if "Video" in att['styles']['attachment']['media']['__typename']: return "Video"
                except: pass
                try:
                    target_type = att['target']['__typename']
                    if target_type == "Story": return "Share"
                    if target_type == "Video": return "Video"
                except: pass
                try:
                    if "Video" in att['styles']['__typename']: return "Video"
                except: pass
        
        # Nếu không phải Share/Video -> Coi là Status hoặc Ảnh (Lấy được)
        return "Status"

    # ==========================================================================
    # HÀM XỬ LÝ CHÍNH (CORE LOGIC)
    # ==========================================================================
    def process_and_save(self, node):
        """
        Nhận 1 cục JSON bài viết -> Kiểm tra -> Lọc -> Ghi vào CSV
        """
        # Nếu đã đủ số lượng (MAX_POSTS) thì dừng ngay
        if self.post_counter >= MAX_POSTS: return

        try:
            # BƯỚC 1: Lấy ID gốc (Raw ID) và giải mã
            raw_id = node.get('id')
            fb_id = self.extract_numeric_id(raw_id)
            
            # Thử lấy ID từ feedback nếu ID chính bị lỗi
            if not fb_id:
                try: fb_id = self.extract_numeric_id(node['feedback']['id'])
                except: pass

            # Nếu không có ID hoặc ID này đã lấy rồi -> Bỏ qua
            if not fb_id or fb_id in self.captured_fb_ids: return

            # BƯỚC 2: Kiểm tra người đăng
            # Nếu Unknown -> Bài rác hệ thống -> BỎ QUA
            user_id, social_user = self.get_author_info(node)
            if user_id == "Unknown" or social_user == "Unknown": return 

            # BƯỚC 3: Kiểm tra loại bài viết (Lọc Share/Video)
            post_type = self.determine_post_type(node)
            if post_type == "Share": return  
            if post_type == "Video": return  

            # BƯỚC 4: Lấy nội dung
            content = self.get_text_content(node)
            
            # BƯỚC 5: Tạo dữ liệu chuẩn hóa
            link = f"https://www.facebook.com/{user_id}/posts/{fb_id}"
            
            # [CHUẨN HÓA] Thêm tiền tố FB_ vào user_id
            formatted_user_id = f"FB_{user_id}"

            # [CHUẨN HÓA] Tăng bộ đếm và tạo ID nội bộ (POST_001, POST_002...)
            self.post_counter += 1
            internal_id = f"POST_{self.post_counter:03d}"
            
            # BƯỚC 6: Ghi vào CSV
            with open(self.output_path, "a", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow([
                    internal_id,        # post_id (Nội bộ)
                    formatted_user_id,  # user_id (FB_...)
                    social_user,        # social_user
                    content,            # context_content
                    link,               # post_link
                    fb_id               # post_fb_id (ID gốc)
                ])

            # Lưu vào bộ nhớ để tránh trùng lặp
            self.captured_fb_ids.add(fb_id)
            print(f"✅ [{self.post_counter}/{MAX_POSTS}] {social_user} | {content[:30]}...")

        except Exception:
            pass

    def parse_graphql_response(self, data):
        """
        Hàm đệ quy: Duyệt qua cấu trúc JSON phức tạp để tìm node bài viết.
        """
        if isinstance(data, dict):
            # Trường hợp 1: Dữ liệu timeline (nhiều bài)
            if 'timeline_list_feed_units' in data:
                edges = data['timeline_list_feed_units'].get('edges', [])
                for edge in edges:
                    if 'node' in edge: self.process_and_save(edge['node'])
            
            # Trường hợp 2: Bài viết đơn lẻ (Story)
            elif data.get('__typename') in ['Story', 'CometStory']:
                self.process_and_save(data)
            
            # Tiếp tục đào sâu vào các nhánh con
            for v in data.values():
                if isinstance(v, (dict, list)): self.parse_graphql_response(v)
        elif isinstance(data, list):
            for item in data: self.parse_graphql_response(item)

    # ==========================================================================
    # HÀM CHẠY CHÍNH (RUNNER)
    # ==========================================================================
    async def run(self):
        async with async_playwright() as p:
            print(f"🚀 [START] Khởi động Profile: {CURRENT_PROFILE_NAME}")
            
            # Mở trình duyệt Chrome với Profile có sẵn
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=False, # True nếu muốn chạy ẩn
                args=["--disable-notifications"],
                viewport={"width": 1280, "height": 900}
            )
            page = context.pages[0]

            # --- THIẾT LẬP LẮNG NGHE MẠNG ---
            # Bắt các gói tin GraphQL chứa dữ liệu bài viết
            async def handle_response(response):
                if "graphql" in response.url:
                    try:
                        text = await response.text()
                        # Facebook stream response trả về nhiều dòng JSON
                        for line in text.split('\n'):
                            if line.strip():
                                try: self.parse_graphql_response(json.loads(line))
                                except: pass
                    except: pass

            page.on("response", handle_response)

            # Truy cập trang đích
            print(f"🌐 [GOTO] Truy cập: {TARGET_URL}")
            await page.goto(TARGET_URL)
            await page.wait_for_timeout(3000)

            # --- VÒNG LẶP CUỘN TRANG ---
            print(f"🔄 [SCROLL] Bắt đầu quét ({MAX_POSTS} bài)...")
            retry_count = 0
            last_count = 0

            while self.post_counter < MAX_POSTS:
                # Nhấn End để cuộn xuống
                await page.keyboard.press("End")
                # Chờ ngẫu nhiên để giống người thật
                await asyncio.sleep(random.uniform(SCROLL_DELAY, SCROLL_DELAY + 2))

                # Kiểm tra tiến độ
                if self.post_counter == last_count:
                    retry_count += 1
                    print(f"   ⏳ Đang chờ bài mới... ({retry_count}/{MAX_RETRIES})")
                    
                    # Nếu thử nhiều lần không được -> Dừng
                    if retry_count >= MAX_RETRIES:
                        print("🛑 [STOP] Không thấy bài mới nữa. Dừng cuộn.")
                        break
                    
                    # Thử click nút "Xem thêm" nếu có
                    try:
                        view_more = page.locator("div[role='button']:has-text('Xem thêm')").first
                        if await view_more.is_visible(): await view_more.click()
                    except: pass
                else:
                    # Có bài mới -> Reset biến đếm retry
                    retry_count = 0
                    last_count = self.post_counter

            print(f"\n🎉 [DONE] Hoàn thành! Tổng bài: {self.post_counter}")
            print(f"📂 [FILE] Kết quả: {OUTPUT_FILE}")

# Chạy chương trình
if __name__ == "__main__":
    crawler = FacebookPostCrawler()
    asyncio.run(crawler.run())