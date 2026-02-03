import asyncio
import json
import csv
import os
import re
from playwright.async_api import async_playwright

# ==============================================================================
# 1. CẤU HÌNH (SETTINGS)
# ==============================================================================
INPUT_POSTS_FILE = 'data/posts_detail.csv'          # File chứa link bài viết
OUTPUT_REACTIONS_FILE = 'data/reactions_detail.csv' # File chứa kết quả
CURRENT_PROFILE_NAME = "acc_clone_1"                    # Profile Chrome

MAX_NO_DATA_RETRIES = 3   # Số lần cuộn không thấy mới thì dừng
SCROLL_TIMEOUT = 2000     # Thời gian chờ khi cuộn (2s)

class FacebookReactionCrawler:
    def __init__(self):
        """Khởi tạo: Đường dẫn file và các biến đếm"""
        self.input_path = os.path.join(os.getcwd(), INPUT_POSTS_FILE)
        self.output_path = os.path.join(os.getcwd(), OUTPUT_REACTIONS_FILE)
        self.user_data_dir = os.path.join(os.getcwd(), "profiles", CURRENT_PROFILE_NAME)
        
        # Biến đếm toàn cục để tạo ID REAC_xxx
        self.total_reaction_counter = 0 
        
        # Các biến tạm thời
        self.current_post_id = ""
        self.session_captured_count = 0 
        self.reaction_map = {}

        # Tạo thư mục và file CSV
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        self.headers = ['reaction_id', 'post_id', 'user_id', 'social_user', 'reaction_type', 'reaction_fb_id']
        with open(self.output_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(self.headers)
            
        print(f"🧹 [INIT] Đã khởi tạo file: {OUTPUT_REACTIONS_FILE}")

    # ==========================================================================
    # HÀM ĐỌC CSV (Lấy Link bài viết)
    # ==========================================================================
    def read_posts_from_csv(self):
        posts = []
        if not os.path.exists(self.input_path): return posts
        with open(self.input_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('post_link'):
                    posts.append({
                        'post_id': row['post_id'],    # ID bài viết (POST_xxx)
                        'post_link': row['post_link'] # Link
                    })
        return posts

    # ==========================================================================
    # HÀM XỬ LÝ GÓI TIN (Lắng nghe ngầm)
    # ==========================================================================
    def parse_reaction_packet(self, json_data):
        extracted_rows = []
        try:
            nodes = json_data if isinstance(json_data, list) else [json_data]
            for root in nodes:
                data_node = root.get('data', {}).get('node', {})
                if not data_node: continue

                # 1. Map tên Reaction (Like, Haha...)
                top_reactions = data_node.get('top_reactions', {}).get('summary', [])
                for r in top_reactions:
                    r_info = r.get('reaction', {})
                    if r_info.get('id'): self.reaction_map[r_info.get('id')] = r_info.get('localized_name')

                # 2. Lấy danh sách người thả reaction
                edges = data_node.get('reactors', {}).get('edges', [])
                for edge in edges:
                    user_node = edge.get('node', {})
                    if not user_node: continue

                    # Tăng ID Reaction (REAC_001...)
                    self.total_reaction_counter += 1
                    internal_reac_id = f"REAC_{self.total_reaction_counter:03d}"
                    
                    extracted_rows.append([
                        internal_reac_id,
                        self.current_post_id,
                        f"FB_{user_node.get('id')}",
                        user_node.get('name'),
                        self.reaction_map.get(edge.get('feedback_reaction_info', {}).get('id'), "Unknown"),
                        edge.get('feedback_reaction_info', {}).get('id')
                    ])

            # Ghi vào file ngay lập tức
            if extracted_rows:
                with open(self.output_path, "a", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f).writerows(extracted_rows)
                return len(extracted_rows)
        except Exception: pass
        return 0

    # ==========================================================================
    # HÀM TÌM NÚT (Chiến thuật Toolbar + Text Ẩn)
    # ==========================================================================
    async def find_reaction_button(self, page):
        print("      🔍 Đang quét nút mở danh sách...")
        
        # 1. Tìm theo Text ẩn "Tất cả cảm xúc" (Cách này thường trúng nhất với layout hiện tại)
        hidden_text_selectors = [
            "div[role='button']:has-text('Tất cả cảm xúc')", 
            "div[role='button']:has-text('All reactions')"
        ]
        for sel in hidden_text_selectors:
            try:
                el = page.locator(sel).last 
                if await el.is_visible(): return el
            except: pass

        # 2. Tìm theo Toolbar (Thẻ bao quanh các icon)
        try:
            toolbar = page.locator("span[role='toolbar'][aria-label*='bày tỏ cảm xúc']").first
            if await toolbar.is_visible():
                # Nút cuối cùng trong toolbar thường là nút tổng
                btn = toolbar.locator("div[role='button']").last
                if await btn.is_visible(): return btn
        except: pass
        
        # 3. Tìm nút số có chữ "Tất cả" (Fallback cuối cùng)
        candidates = await page.locator("div[role='button']").all()
        for el in candidates:
            if await el.is_visible():
                try:
                    txt = await el.inner_text()
                    if re.match(r'^\d+[.,]?\d*[KMkm]?$', txt.strip()):
                        html = await el.evaluate("el => el.innerHTML")
                        if "Tất cả" in html or "All" in html:
                            return el
                except: pass
        return None

    # ==========================================================================
    # HÀM CHẠY CHÍNH CHO 1 BÀI VIẾT
    # ==========================================================================
    async def run(self):
        # 1. Đọc danh sách bài viết
        posts_to_crawl = self.read_posts_from_csv()
        if not posts_to_crawl: return

        async with async_playwright() as p:
            print(f"🚀 [START] Profile: {CURRENT_PROFILE_NAME}")
            
            # Mở trình duyệt
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir, 
                headless=False,
                args=["--disable-notifications"],
                viewport={"width": 1280, "height": 800}
            )
            page = context.pages[0]

            # Thiết lập lắng nghe mạng (Network Listener)
            async def handle_response(response):
                if "graphql" in response.url and response.request.method == "POST":
                    try:
                        text = await response.text()
                        if '"reactors"' in text: # Nếu thấy gói tin chứa reactors
                            count = self.parse_reaction_packet(json.loads(text))
                            if count > 0: 
                                self.session_captured_count += count
                                # print(f"      ✅ +{count}...") 
                    except: pass
            page.on("response", handle_response)

            # 2. Vòng lặp qua từng bài viết
            total_posts = len(posts_to_crawl)
            for i, post in enumerate(posts_to_crawl):
                # Gán thông tin bài hiện tại
                self.current_post_id = post['post_id']
                link = post['post_link']
                self.session_captured_count = 0
                self.reaction_map = {}

                print(f"\n--- [{i+1}/{total_posts}] 🌐 {self.current_post_id} | {link}")
                
                try:
                    await page.goto(link)
                    await page.wait_for_timeout(4000) # Chờ load trang

                    # A. Tìm nút mở danh sách
                    button = await self.find_reaction_button(page)

                    if button:
                        # [VISUAL DEBUG - GIỮ LẠI ĐỂ ỔN ĐỊNH TOOL]
                        # Vẽ viền đỏ và nền vàng để mắt người nhìn thấy
                        # Việc này cũng tạo ra độ trễ nhỏ giúp tool click chính xác hơn
                        await button.evaluate("el => el.style.border = '4px solid red'")
                        await button.evaluate("el => el.style.backgroundColor = 'yellow'")
                        await button.scroll_into_view_if_needed()
                        await page.wait_for_timeout(1000) # Dừng 1 giây cho chắc ăn

                        print("      🖱️ Click mở popup...")
                        try:
                            await button.click(force=True) # Click xuyên thấu
                            await page.wait_for_timeout(3000)
                        except: pass
                    else:
                        print("      ❌ Không tìm thấy nút mở Reaction.")

                    # B. Logic Cuộn Popup & Kiểm tra dừng (Stuck Check)
                    if await page.locator("div[role='dialog']").count() > 0:
                        print("      ✅ Popup MỞ! Bắt đầu cuộn...")
                        
                        # Tìm hộp thoại popup
                        dialog = page.locator("div[role='dialog']").first
                        
                        # Di chuột vào giữa popup để kích hoạt thanh cuộn
                        box = await dialog.bounding_box()
                        if box: await page.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2)

                        retry_count = 0
                        last_total = 0
                        
                        # Vòng lặp cuộn
                        while True:
                            await page.mouse.wheel(0, 3000)
                            await page.wait_for_timeout(SCROLL_TIMEOUT)
                            
                            # Lấy tổng số reaction đã bắt được
                            current_total = self.session_captured_count
                            
                            # So sánh với lần trước
                            if current_total > last_total:
                                print(f"         ⬇️ Tải thêm... (Tổng: {current_total})")
                                last_total = current_total
                                retry_count = 0 # Có dữ liệu mới -> Reset bộ đếm lỗi
                            else:
                                retry_count += 1
                                print(f"         ⚠️ Không thấy mới... ({retry_count}/{MAX_NO_DATA_RETRIES})")
                                
                                # Nếu 3 lần liên tiếp không thấy mới -> Dừng bài này
                                if retry_count >= MAX_NO_DATA_RETRIES:
                                    print(f"         🛑 Dừng bài này. ")
                                    break
                    else:
                        print("      ⚠️ Popup chưa mở (Lỗi click hoặc không có reaction).")

                except Exception as e:
                    print(f"      ⚠️ Lỗi xử lý bài này: {e}")

            print(f"\n🎉 HOÀN THÀNH TOÀN BỘ! File: {OUTPUT_REACTIONS_FILE}")

if __name__ == "__main__":
    crawler = FacebookReactionCrawler()
    asyncio.run(crawler.run())