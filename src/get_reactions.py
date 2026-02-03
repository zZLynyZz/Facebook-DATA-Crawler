import asyncio
import json
import csv
import os
from playwright.async_api import async_playwright

# --- CẤU HÌNH ---
MANUAL_LINKS = [
    "https://www.facebook.com/dreamingsalty/posts/pfbid0DHRpxtn63m6Bv96RSA4CE9QbpobtsATXT1hHA4AmaGznAiaGMr56vrAG6q27Qe7ml"
]

OUTPUT_FILE = 'data/raw/reactions_detail.csv'
CURRENT_PROFILE_NAME = "acc_clone_1"
SCROLL_TIMEOUT = 2000 # 2 giây

class FacebookReactionCrawler:
    def __init__(self):
        self.output_path = os.path.join(os.getcwd(), OUTPUT_FILE)
        self.user_data_dir = os.path.join(os.getcwd(), "profiles", CURRENT_PROFILE_NAME)
        
        # Tạo thư mục và file CSV
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        self.headers = ['post_id', 'user_id', 'social_user', 'reaction_type', 'reaction_id']
        
        # Ghi header (chế độ ghi đè 'w')
        with open(self.output_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(self.headers)
            
        # Bộ nhớ tạm để lưu định nghĩa Reaction (ID -> Name, ví dụ: 1159.. -> Haha)
        self.reaction_map = {} 

    def parse_reaction_packet(self, json_data, post_id):
        """Hàm xử lý JSON trả về từ Facebook"""
        extracted_rows = []
        try:
            # Xử lý trường hợp data trả về là list hoặc dict
            nodes = json_data if isinstance(json_data, list) else [json_data]
            
            for root in nodes:
                # Tìm node gốc
                data_node = root.get('data', {}).get('node', {})
                if not data_node: continue

                # BƯỚC 1: CẬP NHẬT BẢNG TRA CỨU REACTION (Nếu có)
                # Facebook thường gửi định nghĩa này ở gói tin đầu tiên
                top_reactions = data_node.get('top_reactions', {}).get('summary', [])
                for r in top_reactions:
                    r_info = r.get('reaction', {})
                    r_id = r_info.get('id')
                    r_name = r_info.get('localized_name') # "Haha", "Thích"...
                    if r_id and r_name:
                        self.reaction_map[r_id] = r_name

                # BƯỚC 2: BÓC TÁCH NGƯỜI DÙNG
                edges = data_node.get('reactors', {}).get('edges', [])
                for edge in edges:
                    user_node = edge.get('node', {})
                    if not user_node: continue

                    # Lấy thông tin User
                    user_id = f"FB_{user_node.get('id')}"
                    user_name = user_node.get('name')
                    
                    # Lấy thông tin Reaction của User này
                    reaction_info = edge.get('feedback_reaction_info', {})
                    react_id = reaction_info.get('id')
                    
                    # Tra cứu tên Reaction từ bảng map (Nếu ko có thì để mặc định Like)
                    react_type = self.reaction_map.get(react_id, "Like/Unknown")

                    extracted_rows.append([
                        post_id,
                        user_id,
                        user_name,
                        react_type,
                        react_id # Lưu thêm ID để debug nếu cần
                    ])

            # Ghi vào file CSV ngay lập tức
            if extracted_rows:
                with open(self.output_path, "a", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f).writerows(extracted_rows)
                return len(extracted_rows)

        except Exception as e:
            # print(f"Lỗi parse JSON: {e}") 
            pass
        return 0

    async def run(self):
        async with async_playwright() as p:
            print(f"🚀 Khởi động Profile: {self.user_data_dir}")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir, 
                headless=False,
                args=["--disable-notifications"],
                viewport={"width": 1280, "height": 800}
            )
            page = context.pages[0]
            
            current_post_id = ""

            # --- LẮNG NGHE NETWORK ---
            async def handle_response(response):
                if "graphql" in response.url and response.request.method == "POST":
                    try:
                        text = await response.text()
                        # Chỉ xử lý nếu gói tin có chứa danh sách người react
                        if '"reactors"' in text and '"edges"' in text:
                            json_obj = json.loads(text)
                            count = self.parse_reaction_packet(json_obj, current_post_id)
                            if count > 0:
                                print(f"   ✅ Đã lưu {count} dòng.")
                    except: pass

            page.on("response", handle_response)

            # --- VÒNG LẶP CÁC BÀI POST ---
            for i, link in enumerate(MANUAL_LINKS):
                current_post_id = f"POST_{i+1:03d}"
                self.reaction_map = {} # Reset map cho bài mới
                
                print(f"\n[{i+1}/{len(MANUAL_LINKS)}] 🌐 Link: {link}")
                await page.goto(link)
                await page.wait_for_timeout(3000)

                # 1. Tìm và Click nút mở Popup (Logic cũ nhưng cải tiến selector)
                print("   🖱️ Đang tìm nút mở danh sách cảm xúc...")
                try:
                    # Các selector phổ biến để mở popup reaction
                    triggers = [
                        "span[role='toolbar']", 
                        "a[href*='/reaction/profile']",
                        "div[aria-label*='Thích:'][role='button']", # Nút đếm số like
                        "div[role='button']:has-text('Tất cả cảm xúc')"
                    ]
                    
                    popup_opened = False
                    for sel in triggers:
                        if await page.locator(sel).first.is_visible():
                            await page.locator(sel).first.click()
                            await page.wait_for_timeout(2000)
                            # Check xem popup mở chưa
                            if await page.locator("div[role='dialog']").count() > 0:
                                popup_opened = True
                                break
                    
                    if not popup_opened:
                        print("   ⚠️ Không tự mở được popup. Hãy click tay vào số lượng Like!")
                        await page.wait_for_timeout(5000) # Chờ click tay
                except: pass

                # 2. Cuộn bên trong Popup
                print("   🔄 Đang cuộn dữ liệu...")
                # Tìm vùng popup
                dialog = page.locator("div[role='dialog'] div[class*='scroll']").first
                if not await dialog.is_visible():
                     # Fallback nếu class thay đổi: tìm dialog chung
                     dialog = page.locator("div[role='dialog']").first

                # Di chuột vào giữa dialog để cuộn được
                try:
                    box = await dialog.bounding_box()
                    if box:
                        await page.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                except: pass

                # Vòng lặp cuộn
                no_new_data_count = 0
                for _ in range(50): # Max 50 lần cuộn (tùy chỉnh)
                    await page.mouse.wheel(0, 1000)
                    await page.wait_for_timeout(SCROLL_TIMEOUT)
                    
                    # Logic dừng thông minh (nếu cần) có thể thêm ở đây
                    # Hiện tại cứ cuộn 'trâu bò' để đảm bảo trigger network

            print(f"\n🎉 XONG! Kiểm tra file: {OUTPUT_FILE}")

if __name__ == "__main__":
    crawler = FacebookReactionCrawler()
    asyncio.run(crawler.run())