import asyncio
import json
import csv
import os
import base64
import re
import random
from playwright.async_api import async_playwright

# --- CẤU HÌNH MẶC ĐỊNH ---
DEFAULT_TARGET_URL = "https://www.facebook.com/abcxyz" # Page mặc định
DEFAULT_OUTPUT_FILE = 'data/posts_detail.csv'       # File đầu ra
DEFAULT_MAX_POSTS = 5                                   # Số bài mặc định
CURRENT_PROFILE_NAME = "acc_clone_1"                    # Tên profile chrome
SCROLL_DELAY = 3                                        # Thời gian nghỉ cuộn

class FacebookPostCrawler:
    def __init__(self, target_url=None, max_posts=None):
        # Ưu tiên lấy tham số từ file main truyền qua
        self.target_url = target_url if target_url else DEFAULT_TARGET_URL
        self.max_posts = max_posts if max_posts else DEFAULT_MAX_POSTS
        
        # Thiết lập đường dẫn lưu file và profile người dùng
        self.output_path = os.path.join(os.getcwd(), DEFAULT_OUTPUT_FILE)
        self.user_data_dir = os.path.join(os.getcwd(), "profiles", CURRENT_PROFILE_NAME)
        
        self.post_counter = 0        # Biến đếm số bài thu thập được
        self.captured_fb_ids = set() # Tập hợp lưu ID để chống trùng bài
        
        # Khởi tạo thư mục và ghi dòng tiêu đề (Header) cho file CSV
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        self.headers = ["post_id", "user_id", "social_user", "context_content", "post_link", "post_fb_id"]
        with open(self.output_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(self.headers)
            
        print("-" * 40)
        print(f"🧹 [INIT] Đã tạo file sạch: {DEFAULT_OUTPUT_FILE}")
        print(f"🎯 [TARGET] Page: {self.target_url}")
        print(f"🔢 [LIMIT] Lấy tối đa: {self.max_posts} bài")
        print("-" * 40)

    # Giải mã ID từ Base64 sang dạng số (VD: Uzpf... -> 1000...)
    def extract_numeric_id(self, base64_id):
        if not base64_id: return None
        try:
            if re.match(r'^\d+$', str(base64_id)): return str(base64_id) # Nếu đã là số
            decoded_bytes = base64.b64decode(base64_id) # Giải mã base64
            decoded_str = decoded_bytes.decode('utf-8') # Chuyển về chuỗi
            match = re.search(r'(\d+)$', decoded_str)   # Tìm dãy số ở cuối
            if match: return match.group(1)
        except: pass
        return None

    # Tìm và lấy nội dung văn bản của bài viết (xử lý cả cấu hình cũ và mới)
    def get_text_content(self, node):
        content = ""
        try: content = node['comet_sections']['content']['story']['message']['text']
        except:
            try: content = node['message']['text']
            except: pass
        return content.replace("\n", " ").strip() if content else "" # Xóa xuống dòng

    # Lấy ID và Tên của người/Page đăng bài
    def get_author_info(self, node):
        uid, name = "Unknown", "Unknown"
        try:
            actors = node['comet_sections']['context_layout']['story']['actors']
            if actors:
                uid = actors[0].get('id', 'Unknown')   # Lấy User ID
                name = actors[0].get('name', 'Unknown') # Lấy tên hiển thị
                return uid, name
        except: pass
        return uid, name

    # Phân loại để bỏ qua các bài chia sẻ (Share) hoặc Video
    def determine_post_type(self, node):
        try:
            if node['comet_sections']['content']['story']['attached_story']: return "Share"
        except: pass
        return "Status"

    # Lưu dữ liệu vào file CSV sau khi đã lọc điều kiện
    def process_and_save(self, node):
        if self.post_counter >= self.max_posts: return # Dừng nếu đủ số lượng

        try:
            raw_id = node.get('id')
            fb_id = self.extract_numeric_id(raw_id) # Lấy ID bài viết gốc
            if not fb_id or fb_id in self.captured_fb_ids: return # Bỏ qua nếu trùng

            user_id, social_user = self.get_author_info(node) # Lấy info tác giả
            if user_id == "Unknown": return 

            if self.determine_post_type(node) != "Status": return # Chỉ lấy Status/Ảnh

            content = self.get_text_content(node) # Lấy text bài viết
            link = f"https://www.facebook.com/{user_id}/posts/{fb_id}" # Tạo link bài
            
            self.post_counter += 1 # Tăng biến đếm
            internal_id = f"POST_{self.post_counter:03d}" # ID tự tăng (POST_001)
            
            # Ghi dòng dữ liệu vào file CSV
            with open(self.output_path, "a", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow([internal_id, f"FB_{user_id}", social_user, content, link, fb_id])

            self.captured_fb_ids.add(fb_id) # Đưa vào danh sách đã lấy
            print(f"✅ [{self.post_counter}/{self.max_posts}] {social_user}: {content[:30]}...")
        except Exception: pass

    # Duyệt đệ quy để tìm tất cả các bài viết ẩn trong gói JSON của Facebook
    def parse_graphql_response(self, data):
        if isinstance(data, dict):
            if 'timeline_list_feed_units' in data: # Cấu trúc danh sách bài viết
                for edge in data['timeline_list_feed_units'].get('edges', []):
                    if 'node' in edge: self.process_and_save(edge['node'])
            elif data.get('__typename') in ['Story', 'CometStory']: # Cấu trúc bài lẻ
                self.process_and_save(data)
            for v in data.values(): # Duyệt sâu xuống các nhánh con
                if isinstance(v, (dict, list)): self.parse_graphql_response(v)
        elif isinstance(data, list):
            for item in data: self.parse_graphql_response(item)

    async def run(self):
        async with async_playwright() as p:
            # Mở trình duyệt với Profile cố định để dùng lại Cookie
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir, headless=False,
                args=["--disable-notifications"], viewport={"width": 1280, "height": 900}
            )
            page = context.pages[0]

            # Lắng nghe các gói tin phản hồi từ Server Facebook
            async def handle_response(response):
                if "graphql" in response.url: # Chỉ xử lý gói tin GraphQL
                    try:
                        text = await response.text()
                        for line in text.split('\n'): # Tách từng dòng JSON
                            if line.strip():
                                try: self.parse_graphql_response(json.loads(line))
                                except: pass
                    except: pass

            page.on("response", handle_response) # Kích hoạt lắng nghe
            await page.goto(self.target_url)     # Truy cập Page mục tiêu
            await page.wait_for_timeout(3000)    # Chờ trang tải

            last_count = 0
            while self.post_counter < self.max_posts:
                await page.keyboard.press("End") # Cuộn xuống cuối trang
                await asyncio.sleep(random.uniform(SCROLL_DELAY, SCROLL_DELAY + 2))
                if self.post_counter == last_count: # Nếu không có bài mới
                    await asyncio.sleep(2) # Chờ thêm 2 giây
                last_count = self.post_counter
            await context.close() # Đóng trình duyệt khi xong

if __name__ == "__main__":
    asyncio.run(FacebookPostCrawler().run()) # Chạy lẻ module này