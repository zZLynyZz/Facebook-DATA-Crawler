import asyncio
import json
import csv
import os
import base64
import re
from datetime import datetime
from playwright.async_api import async_playwright

# ==============================================================================
# 1. PHẦN CẤU HÌNH (SETTINGS)
# ==============================================================================
INPUT_POSTS_FILE = 'data/posts_detail.csv'      # File chứa danh sách bài viết (Đầu vào)
OUTPUT_COMMENTS_FILE = 'data/comments_detail.csv' # File chứa comment (Đầu ra)
CURRENT_PROFILE_NAME = "acc_clone_1"                # Profile Chrome

SCROLL_DELAY = 3      # Thời gian nghỉ khi cuộn (giây)
MAX_RETRIES = 3       # Số lần thử cuộn lại nếu hết comment

class FacebookCommentCrawler:
    def __init__(self):
        """
        Khởi tạo:
        - Thiết lập đường dẫn file input/output.
        - Tạo file CSV đầu ra chứa các cột dữ liệu comment.
        """
        self.input_path = os.path.join(os.getcwd(), INPUT_POSTS_FILE)
        self.output_path = os.path.join(os.getcwd(), OUTPUT_COMMENTS_FILE)
        self.user_data_dir = os.path.join(os.getcwd(), "profiles", CURRENT_PROFILE_NAME)
        
        self.record_counter = 0         # Biến đếm số lượng comment lấy được
        self.current_post_id = ""       # Lưu ID bài viết đang xử lý hiện tại (VD: POST_001)
        
        # Tạo thư mục chứa data nếu chưa có
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        
        # [CẬP NHẬT] Đổi tên cột cuối cùng thành comment_fb_id
        self.headers = [
            'record_id',     # ID dòng (REC_001)
            'source_channel',# Nguồn (Facebook)
            'post_id',       # ID bài viết gốc (POST_001)
            'timestamp',     # Thời gian comment
            'user_id',       # ID người comment
            'social_user',   # Tên người comment
            'original_text', # Nội dung comment
            'comment_fb_id'  # ID số của comment (Đã số hóa)
        ]
        
        # Tạo file mới (Ghi đè - 'w')
        with open(self.output_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(self.headers)
        print(f"🧹 [INIT] Đã tạo file sạch: {OUTPUT_COMMENTS_FILE}")

    # ==========================================================================
    # HÀM HỖ TRỢ: SỐ HÓA ID (MỚI)
    # ==========================================================================
    def extract_numeric_id(self, base64_id):
        """
        Giải mã ID từ dạng Base64 (Y29tbWVudDoxMjM...) sang số (123...)
        """
        if not base64_id: return "Unknown"
        try:
            # Nếu ID đã là số rồi thì trả về luôn
            if re.match(r'^\d+$', str(base64_id)): return str(base64_id)
            
            # Giải mã Base64
            decoded_bytes = base64.b64decode(base64_id)
            decoded_str = decoded_bytes.decode('utf-8')
            
            # Lấy chuỗi số cuối cùng (Logic của FB thường là Type:ID)
            match = re.search(r'(\d+)$', decoded_str)
            if match: return match.group(1)
        except: pass
        # Nếu không giải mã được thì trả về nguyên gốc để debug
        return base64_id

    # ==========================================================================
    # HÀM ĐỌC DỮ LIỆU ĐẦU VÀO
    # ==========================================================================
    def read_posts_from_csv(self):
        """Đọc danh sách bài viết từ file posts_detail.csv"""
        posts = []
        if not os.path.exists(self.input_path):
            print(f"❌ Không tìm thấy file input: {self.input_path}")
            return posts

        with open(self.input_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('post_link'):
                    posts.append({
                        'post_id': row['post_id'],
                        'post_link': row['post_link']
                    })
        print(f"📂 [READ] Đã đọc được {len(posts)} bài viết cần lấy comment.")
        return posts

    # ==========================================================================
    # HÀM LƯU DỮ LIỆU (SAVE)
    # ==========================================================================
    def save_to_csv(self, items):
        if not items: return
        
        with open(self.output_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            for item in items:
                self.record_counter += 1
                rec_id = f"REC_{self.record_counter:03d}"
                
                raw_uid = item.get("author_id", "unknown")
                user_real_id = f"FB_{raw_uid}" if raw_uid != "unknown" else "FB_Unknown"

                writer.writerow([
                    rec_id,                     
                    'Facebook',                 
                    self.current_post_id,       
                    item.get("time"),           
                    user_real_id,               
                    item.get("name"),           
                    item.get("text"),           
                    item.get("id")  # Đây giờ là ID đã được số hóa
                ])
                print(f"      + [{self.current_post_id}] {item.get('name')}: {item.get('text')[:30]}...")

    # ==========================================================================
    # CÁC HÀM BÓC TÁCH JSON (PARSING)
    # ==========================================================================
    def find_text_recursively(self, data, depth=0):
        if depth > 5: return ""
        if isinstance(data, dict):
            if "text" in data and isinstance(data["text"], str) and len(data["text"]) > 0: return data["text"]
            for k, v in data.items():
                if k not in ["__typename", "id"]:
                    res = self.find_text_recursively(v, depth + 1)
                    if res: return res
        elif isinstance(data, list):
            for item in data:
                res = self.find_text_recursively(item, depth + 1)
                if res: return res
        return ""

    def parse_comments_json(self, data, collected_items):
        if isinstance(data, dict):
            if data.get("__typename") == "Comment":
                # 1. Lấy nội dung
                body = self.find_text_recursively(data.get("body", {})) or self.find_text_recursively(data)
                
                # 2. Lấy tác giả
                author_obj = data.get("author", {})
                author_name = author_obj.get("name", "Unknown")
                author_id = author_obj.get("id", "unknown")

                # 3. Lấy và xử lý ID Comment (SỐ HÓA)
                raw_comment_id = data.get("id", "")
                numeric_comment_id = self.extract_numeric_id(raw_comment_id)

                # 4. Lấy thời gian
                time_str = ""
                try:
                    ts = data.get("created_time")
                    if ts: time_str = datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
                except: pass

                if body:
                    collected_items.append({
                        "id": numeric_comment_id, # Đã chuyển thành số
                        "author_id": author_id,
                        "name": author_name,
                        "text": body.replace("\n", " "),
                        "time": time_str
                    })
            
            for val in data.values(): self.parse_comments_json(val, collected_items)
        
        elif isinstance(data, list):
            for item in data: self.parse_comments_json(item, collected_items)

    # ==========================================================================
    # HÀM CHẠY CHÍNH (RUN)
    # ==========================================================================
    async def run(self):
        posts_to_crawl = self.read_posts_from_csv()
        if not posts_to_crawl: return

        async with async_playwright() as p:
            print(f"🚀 [START] Khởi động Profile: {CURRENT_PROFILE_NAME}")
            
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir, headless=False,
                args=["--disable-notifications"], viewport={"width": 1280, "height": 800}
            )
            page = context.pages[0]

            async def handle_response(response):
                if response.request.resource_type in ["xhr", "fetch"]:
                    try:
                        text = await response.text()
                        if text.startswith("for (;;);"): text = text[9:]
                        
                        if '"Comment"' in text or '"feedback"' in text:
                            try:
                                items = []
                                self.parse_comments_json(json.loads(text), items)
                                if items: 
                                    self.save_to_csv(items)
                            except: pass
                    except: pass
            
            page.on("response", handle_response)

            total_posts = len(posts_to_crawl)
            for i, post in enumerate(posts_to_crawl):
                self.current_post_id = post['post_id'] 
                link = post['post_link']
                
                print(f"\n[{i+1}/{total_posts}] 🌐 Đang xử lý: {self.current_post_id}")
                print(f"    🔗 Link: {link}")
                
                try:
                    await page.goto(link)
                    await page.wait_for_timeout(5000)

                    # --- BƯỚC 1: CHỈNH BỘ LỌC ---
                    print("    ⚙️ Đang chỉnh bộ lọc bình luận...")
                    try:
                        filter_btn = page.locator("div[role='button']:has-text('Phù hợp nhất'), div[role='button']:has-text('Mới nhất'), div[role='button']:has-text('Most relevant')").first
                        if await filter_btn.is_visible():
                            await filter_btn.click()
                            await page.wait_for_timeout(2000)
                            all_opt = page.locator("div[role='menuitem']:has-text('Tất cả bình luận'), div[role='menuitem']:has-text('All comments')").first
                            if await all_opt.is_visible():
                                await all_opt.click()
                                await page.wait_for_timeout(3000)
                            else:
                                newest_opt = page.locator("div[role='menuitem']:has-text('Mới nhất'), div[role='menuitem']:has-text('Newest')").first
                                if await newest_opt.is_visible(): await newest_opt.click(); await page.wait_for_timeout(3000)
                    except: pass

                    # --- BƯỚC 2: CUỘN ---
                    print(f"    🔄 Bắt đầu cuộn...")
                    last_count = 0
                    retry_count = 0
                    
                    while True:
                        current_count = await page.locator("div[role='article'][aria-label*='luan'], div[role='article'][aria-label*='ment']").count()
                        if current_count == 0: current_count = await page.locator("div[role='article']").count()

                        if current_count == last_count and current_count > 0:
                            retry_count += 1
                            print(f"      ⚠️ Chưa thấy mới ({retry_count}/{MAX_RETRIES})...")
                            if retry_count >= MAX_RETRIES:
                                print(f"      🛑 Dừng cuộn bài này.")
                                break
                        else:
                            if current_count > last_count:
                                print(f"      ⬇️ Tải thêm {current_count - last_count} comment...")
                                retry_count = 0
                            last_count = current_count

                        await page.keyboard.press("End")
                        await page.wait_for_timeout(SCROLL_DELAY * 1000)

                        try:
                            view_more = page.locator("span:text('Xem thêm bình luận'), span:text('View more comments')").first
                            if await view_more.is_visible(): 
                                await view_more.click()
                                await page.wait_for_timeout(2000)
                        except: pass

                except Exception as e:
                    print(f"    ⚠️ Lỗi: {e}")

            print(f"\n🎉 [DONE] Hoàn thành!")
            print(f"📂 [FILE] Kết quả: {OUTPUT_COMMENTS_FILE}")

if __name__ == "__main__":
    crawler = FacebookCommentCrawler()
    asyncio.run(crawler.run())