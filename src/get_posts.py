import asyncio
import json
import csv
import os
import base64
import re
import random
from playwright.async_api import async_playwright

# ==============================================================================
# 1. PHẦN CẤU HÌNH (SETTINGS)
# ==============================================================================
TARGET_URL = "https://www.facebook.com/dreamingsalty"  # Link Page cần lấy
OUTPUT_FILE = 'data/posts_detail.csv'              # Tên file xuất ra
CURRENT_PROFILE_NAME = "acc_clone_1"                   # Tên profile chrome

MAX_POSTS = 20        # Số lượng bài viết tối đa
SCROLL_DELAY = 3      # Thời gian nghỉ khi cuộn
MAX_RETRIES = 5       # Số lần thử lại nếu tắc

class FacebookPostCrawler:
    def __init__(self):
        """Khởi tạo Class và File CSV"""
        self.output_path = os.path.join(os.getcwd(), OUTPUT_FILE)
        self.user_data_dir = os.path.join(os.getcwd(), "profiles", CURRENT_PROFILE_NAME)
        
        self.post_counter = 0        
        self.captured_fb_ids = set() 
        
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        
        # Header file CSV
        self.headers = [
            "post_id",          # POST_001
            "user_id",          # FB_1000xxx (Đã thêm prefix FB_)
            "social_user",      # Tên người đăng
            "context_content",  # Nội dung
            "post_link",        # Link bài
            "post_fb_id"        # ID gốc của bài viết (số)
        ]
        
        with open(self.output_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(self.headers)
            
        print(f"🧹 [INIT] Đã tạo file sạch: {OUTPUT_FILE}")
        print("🚫 [RULE] Mode: BỎ Unknown, BỎ Share, BỎ Video")

    # ==========================================================================
    # CÁC HÀM HỖ TRỢ (HELPER)
    # ==========================================================================

    def extract_numeric_id(self, base64_id):
        """Giải mã ID Base64 sang số"""
        if not base64_id: return None
        try:
            if re.match(r'^\d+$', str(base64_id)): return str(base64_id)
            decoded_bytes = base64.b64decode(base64_id)
            decoded_str = decoded_bytes.decode('utf-8')
            match = re.search(r'(\d+)$', decoded_str)
            if match: return match.group(1)
        except: pass
        return None

    def get_text_content(self, node):
        """Lấy nội dung bài viết"""
        content = ""
        try: content = node['comet_sections']['content']['story']['message']['text']
        except:
            try: content = node['message']['text']
            except: pass
        return content.replace("\n", " ").strip() if content else ""

    def get_author_info(self, node):
        """Lấy Tên và ID người đăng"""
        uid, name = "Unknown", "Unknown"
        # Cách 1: Tìm trong actors
        try:
            actors = node['comet_sections']['context_layout']['story']['actors']
            if actors:
                uid = actors[0].get('id', 'Unknown')
                name = actors[0].get('name', 'Unknown')
                return uid, name
        except: pass
        # Cách 2: Tìm trong feedback
        try:
            profile = node['feedback']['owning_profile']
            if profile:
                uid = profile.get('id', 'Unknown')
                name = profile.get('name', 'Unknown')
        except: pass
        return uid, name

    def determine_post_type(self, node):
        """Xác định loại bài viết (Share/Video/Status...)"""
        # Check Share
        try:
            if node['comet_sections']['content']['story']['attached_story']: return "Share"
        except: pass
        try:
             if 'shareable' in node and node['shareable']['__typename'] == 'EntityShareable': return "Share"
        except: pass

        # Check Attachments
        attachments = []
        try: attachments = node['comet_sections']['content']['story']['attachments']
        except:
            try: attachments = node['attachments']
            except: pass

        if attachments:
            for att in attachments:
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
        
        return "Status"

    # ==========================================================================
    # HÀM XỬ LÝ CHÍNH
    # ==========================================================================
    def process_and_save(self, node):
        if self.post_counter >= MAX_POSTS: return

        try:
            # 1. Lấy ID bài viết gốc
            raw_id = node.get('id')
            fb_id = self.extract_numeric_id(raw_id)
            if not fb_id:
                try: fb_id = self.extract_numeric_id(node['feedback']['id'])
                except: pass

            if not fb_id or fb_id in self.captured_fb_ids: return

            # 2. Lấy thông tin tác giả & Lọc Unknown
            user_id, social_user = self.get_author_info(node)
            if user_id == "Unknown" or social_user == "Unknown": return 

            # 3. Lọc loại bài viết (Bỏ Share/Video)
            post_type = self.determine_post_type(node)
            if post_type == "Share": return  
            if post_type == "Video": return  

            # 4. Lấy nội dung text
            content = self.get_text_content(node)
            
            # 5. Tạo link và Format lại User ID
            link = f"https://www.facebook.com/{user_id}/posts/{fb_id}"
            
            # [CẬP NHẬT] Thêm tiền tố FB_ vào user_id
            formatted_user_id = f"FB_{user_id}" 

            # 6. Ghi vào CSV
            self.post_counter += 1
            internal_id = f"POST_{self.post_counter:03d}"
            
            with open(self.output_path, "a", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow([
                    internal_id, 
                    formatted_user_id, # Sử dụng ID đã thêm FB_
                    social_user, 
                    content, 
                    link, 
                    fb_id
                ])

            self.captured_fb_ids.add(fb_id)
            print(f"✅ [{self.post_counter}/{MAX_POSTS}] {social_user} | {content[:30]}...")

        except Exception:
            pass

    def parse_graphql_response(self, data):
        """Đệ quy tìm bài viết trong JSON"""
        if isinstance(data, dict):
            if 'timeline_list_feed_units' in data:
                edges = data['timeline_list_feed_units'].get('edges', [])
                for edge in edges:
                    if 'node' in edge: self.process_and_save(edge['node'])
            elif data.get('__typename') in ['Story', 'CometStory']:
                self.process_and_save(data)
            
            for v in data.values():
                if isinstance(v, (dict, list)): self.parse_graphql_response(v)
        elif isinstance(data, list):
            for item in data: self.parse_graphql_response(item)

    # ==========================================================================
    # HÀM CHẠY (RUN)
    # ==========================================================================
    async def run(self):
        async with async_playwright() as p:
            print(f"🚀 [START] Profile: {CURRENT_PROFILE_NAME}")
            
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir, headless=False,
                args=["--disable-notifications"], viewport={"width": 1280, "height": 900}
            )
            page = context.pages[0]

            async def handle_response(response):
                if "graphql" in response.url:
                    try:
                        text = await response.text()
                        for line in text.split('\n'):
                            if line.strip():
                                try: self.parse_graphql_response(json.loads(line))
                                except: pass
                    except: pass

            page.on("response", handle_response)

            print(f"🌐 [GOTO] {TARGET_URL}")
            await page.goto(TARGET_URL)
            await page.wait_for_timeout(3000)

            print(f"🔄 [SCROLL] Bắt đầu quét...")
            retry_count = 0
            last_count = 0

            while self.post_counter < MAX_POSTS:
                await page.keyboard.press("End")
                await asyncio.sleep(random.uniform(SCROLL_DELAY, SCROLL_DELAY + 2))

                if self.post_counter == last_count:
                    retry_count += 1
                    print(f"   ⏳ Đang chờ... ({retry_count}/{MAX_RETRIES})")
                    if retry_count >= MAX_RETRIES:
                        print("🛑 Dừng cuộn.")
                        break
                    try:
                        view_more = page.locator("div[role='button']:has-text('Xem thêm')").first
                        if await view_more.is_visible(): await view_more.click()
                    except: pass
                else:
                    retry_count = 0
                    last_count = self.post_counter

            print(f"\n🎉 [DONE] Tổng: {self.post_counter} bài.")
            print(f"📂 [FILE] {OUTPUT_FILE}")

if __name__ == "__main__":
    crawler = FacebookPostCrawler()
    asyncio.run(crawler.run())