import asyncio
import json
import csv
import os
import re
import random
from playwright.async_api import async_playwright

# ==============================================================================
# 1. PHẦN CẤU HÌNH (SETTINGS)
# ==============================================================================
INPUT_POSTS_FILE = 'data/posts_detail.csv'          # File chứa danh sách bài viết đầu vào
OUTPUT_REACTIONS_FILE = 'data/reactions_detail.csv' # File kết quả đầu ra
CURRENT_PROFILE_NAME = "acc_clone_1"                    # Tên Profile Chrome

MAX_RETRIES_PER_POST = 3  # Số lần thử lại tối đa nếu 1 bài bị lỗi
SCROLL_TIMEOUT = 1500     # Tốc độ cuộn trong popup (miliseconds)

class FacebookReactionCrawler:
    def __init__(self):
        """Khởi tạo: Thiết lập đường dẫn và file CSV"""
        self.input_path = os.path.join(os.getcwd(), INPUT_POSTS_FILE)
        self.output_path = os.path.join(os.getcwd(), OUTPUT_REACTIONS_FILE)
        self.user_data_dir = os.path.join(os.getcwd(), "profiles", CURRENT_PROFILE_NAME)
        
        # Biến theo dõi trạng thái
        self.current_post_id = ""       # ID bài viết đang chạy (VD: POST_001)
        self.current_captured_count = 0 # Đếm số reaction bắt được của bài hiện tại
        self.reaction_map = {}          # Bảng tra cứu ID -> Tên (VD: 123 -> Haha)
        
        # [QUAN TRỌNG] Biến đếm tổng số Reaction (để tạo ID REAC_001, REAC_002...)
        self.total_reaction_counter = 0

        # Tạo thư mục nếu chưa có
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        
        # [CẬP NHẬT] Header file CSV theo yêu cầu mới
        self.headers = [
            'reaction_id',      # ID tự tăng (REAC_001)
            'post_id',          # ID bài viết (POST_001)
            'user_id',          # ID người reaction (FB_123...)
            'social_user',      # Tên người reaction
            'reaction_type',    # Loại (Like, Tim, Haha...)
            'reaction_fb_id'    # ID gốc của Facebook trả về
        ]
        
        # Tạo file mới và ghi dòng tiêu đề
        with open(self.output_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(self.headers)
            
        print(f"🧹 [INIT] Đã tạo file sạch: {OUTPUT_REACTIONS_FILE}")

    # ==========================================================================
    # HÀM ĐỌC DỮ LIỆU ĐẦU VÀO
    # ==========================================================================
    def read_posts_from_csv(self):
        """Đọc danh sách link từ file posts_detail.csv"""
        posts = []
        if not os.path.exists(self.input_path):
            print(f"❌ Không tìm thấy file input: {self.input_path}")
            return posts

        with open(self.input_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Chỉ lấy những dòng có link bài viết
                if row.get('post_link'):
                    posts.append({
                        'post_id': row['post_id'],       # Lấy ID bài viết (POST_001)
                        'post_link': row['post_link']    # Lấy Link
                    })
        print(f"📂 [READ] Đã đọc {len(posts)} bài viết cần xử lý.")
        return posts

    # ==========================================================================
    # HÀM XỬ LÝ JSON (QUAN TRỌNG)
    # ==========================================================================
    def parse_reaction_packet(self, json_data):
        """Phân tích gói tin JSON từ Facebook để lấy dữ liệu"""
        extracted_rows = []
        try:
            # Facebook có thể trả về list hoặc dict, cần xử lý cả 2
            nodes = json_data if isinstance(json_data, list) else [json_data]
            
            for root in nodes:
                # Tìm node chứa dữ liệu chính
                data_node = root.get('data', {}).get('node', {})
                if not data_node: continue

                # 1. Cập nhật bảng map (ID -> Tên Reaction)
                # Facebook gửi kèm định nghĩa các loại reaction trong gói tin đầu
                top_reactions = data_node.get('top_reactions', {}).get('summary', [])
                for r in top_reactions:
                    r_info = r.get('reaction', {})
                    if r_info.get('id'): 
                        self.reaction_map[r_info.get('id')] = r_info.get('localized_name')

                # 2. Lấy danh sách người reaction (reactors -> edges)
                edges = data_node.get('reactors', {}).get('edges', [])
                for edge in edges:
                    user_node = edge.get('node', {})
                    if not user_node: continue

                    # Lấy thông tin cơ bản
                    user_id = f"FB_{user_node.get('id')}"
                    user_name = user_node.get('name')
                    
                    # Xác định loại reaction (dựa vào bảng map ở trên)
                    reaction_info = edge.get('feedback_reaction_info', {})
                    react_fb_id = reaction_info.get('id')
                    react_type = self.reaction_map.get(react_fb_id, "Unknown")

                    # [CẬP NHẬT] Tạo ID tự tăng (REAC_xxx)
                    self.total_reaction_counter += 1
                    internal_reac_id = f"REAC_{self.total_reaction_counter:03d}"

                    # Thêm vào danh sách chờ ghi
                    extracted_rows.append([
                        internal_reac_id,       # reaction_id
                        self.current_post_id,   # post_id
                        user_id,                # user_id
                        user_name,              # social_user
                        react_type,             # reaction_type
                        react_fb_id             # reaction_fb_id
                    ])

            # Ghi ngay vào file CSV để an toàn dữ liệu
            if extracted_rows:
                with open(self.output_path, "a", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f).writerows(extracted_rows)
                return len(extracted_rows) # Trả về số lượng lấy được
        except Exception: 
            pass
        return 0

    # ==========================================================================
    # CHIẾN THUẬT TÌM NÚT (SMART SELECTOR)
    # ==========================================================================
    async def find_reaction_button(self, page):
        """Tìm nút mở danh sách reaction (nút số lượng hoặc nút 'Tất cả')"""
        print("      🔍 Đang quét nút mở danh sách...")
        
        # CHIẾN THUẬT 1: Tìm theo Aria-Label (Chính xác nhất)
        # Đây là text ẩn hỗ trợ người khiếm thị mà Facebook gắn vào nút
        aria_selectors = [
            "div[aria-label*='Xem ai đã bày tỏ']",
            "span[aria-label*='Xem ai đã bày tỏ']"
        ]
        for sel in aria_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(): return el
            except: pass

        # CHIẾN THUẬT 2: Tìm theo Text ẩn "Tất cả cảm xúc"
        hidden_text_selectors = [
            "div[role='button']:has-text('Tất cả cảm xúc')",
            "div[role='button']:has-text('All reactions')"
        ]
        for sel in hidden_text_selectors:
            try:
                el = page.locator(sel).last
                if await el.is_visible(): return el
            except: pass

        # CHIẾN THUẬT 3: Tìm nút SỐ nằm trong Toolbar (Dự phòng)
        try:
            toolbar = page.locator("span[role='toolbar'][aria-label*='bày tỏ cảm xúc']").first
            if await toolbar.is_visible():
                btn = toolbar.locator("div[role='button']").last
                if await btn.is_visible(): return btn
        except: pass

        return None

    # ==========================================================================
    # HÀM XỬ LÝ 1 BÀI VIẾT (CÓ THỬ LẠI 3 LẦN)
    # ==========================================================================
    async def process_single_post(self, page, post_data):
        self.current_post_id = post_data['post_id']
        link = post_data['post_link']
        
        print(f"\n🌐 Đang xử lý: {self.current_post_id} | {link}")

        # Vòng lặp thử lại (Retry Loop)
        for attempt in range(1, MAX_RETRIES_PER_POST + 1):
            self.current_captured_count = 0 # Reset bộ đếm của lần thử này
            self.reaction_map = {}          # Reset bảng map
            
            print(f"   🔄 Lần thử {attempt}/{MAX_RETRIES_PER_POST}...")
            
            try:
                await page.goto(link)
                await page.wait_for_timeout(4000) # Chờ trang tải xong

                # 1. Tìm nút mở popup
                button = await self.find_reaction_button(page)
                
                if button:
                    # Cuộn nút vào giữa màn hình để tránh bị che
                    await button.scroll_into_view_if_needed()
                    await page.wait_for_timeout(1000)

                    # Click force=True để xuyên qua các lớp ảo
                    print("      🖱️ Click mở danh sách...")
                    await button.click(force=True)
                    await page.wait_for_timeout(3000)

                    # 2. Kiểm tra Popup & Cuộn
                    if await page.locator("div[role='dialog']").count() > 0:
                        print("      ✅ Popup đã mở! Đang cuộn lấy data...")
                        
                        dialog = page.locator("div[role='dialog']").first
                        
                        # Di chuột vào giữa popup để kích hoạt thanh cuộn
                        box = await dialog.bounding_box()
                        if box:
                            await page.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                        
                        # Cuộn liên tục để tải dữ liệu
                        for _ in range(30): 
                            await page.mouse.wheel(0, 3000)
                            await page.wait_for_timeout(SCROLL_TIMEOUT)
                        
                        # Nếu bắt được dữ liệu -> Thành công -> Thoát vòng lặp retry
                        if self.current_captured_count > 0:
                            print(f"      🎉 Thành công! Đã lấy {self.current_captured_count} reaction.")
                            return 
                        else:
                            print("      ⚠️ Đã cuộn nhưng không thấy dữ liệu mới.")
                    else:
                        print("      ⚠️ Click rồi nhưng Popup không hiện.")
                else:
                    print("      ❌ Không tìm thấy nút Reaction nào.")

            except Exception as e:
                print(f"      ⚠️ Lỗi: {e}")

            # Nếu thất bại thì chờ 2s rồi thử lại
            print("      🛑 Thất bại. Đang tải lại trang...")
            await asyncio.sleep(2)

        print(f"   ❌ BỎ QUA bài viết {self.current_post_id} sau 3 lần thử.")

    # ==========================================================================
    # HÀM CHẠY CHÍNH (MAIN)
    # ==========================================================================
    async def run(self):
        # Đọc dữ liệu đầu vào
        posts_to_crawl = self.read_posts_from_csv()
        if not posts_to_crawl: return

        async with async_playwright() as p:
            print(f"🚀 [START] Profile: {CURRENT_PROFILE_NAME}")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir, 
                headless=False,
                args=["--disable-notifications"],
                viewport={"width": 1280, "height": 800}
            )
            page = context.pages[0]

            # --- THIẾT LẬP LẮNG NGHE MẠNG ---
            # Chỉ bắt các gói tin GraphQL phương thức POST
            async def handle_response(response):
                if "graphql" in response.url and response.request.method == "POST":
                    try:
                        text = await response.text()
                        # Dấu hiệu nhận biết gói tin chứa reaction
                        if '"reactors"' in text and '"edges"' in text:
                            count = self.parse_reaction_packet(json.loads(text))
                            if count > 0: 
                                self.current_captured_count += count
                                print(f"         + {count} dòng mới...")
                    except: pass
            
            page.on("response", handle_response)

            # Chạy vòng lặp qua từng bài viết
            total = len(posts_to_crawl)
            for i, post in enumerate(posts_to_crawl):
                print(f"\n--- TIẾN ĐỘ: [{i+1}/{total}] ---")
                await self.process_single_post(page, post)

            print(f"\n🎉 [DONE] Hoàn thành! File kết quả: {OUTPUT_REACTIONS_FILE}")

if __name__ == "__main__":
    crawler = FacebookReactionCrawler()
    asyncio.run(crawler.run())