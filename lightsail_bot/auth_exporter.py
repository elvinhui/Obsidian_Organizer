from playwright.sync_api import sync_playwright
import os

def export_auth():
    print("🚀 启动身份凭证导出器 (Playwright)...")
    
    with sync_playwright() as p:
        # headless=False 意味着会弹出一个真实的浏览器窗口供您扫码
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # ----------------------------------------
        # 导出 抖音 (Douyin) 凭证
        # ----------------------------------------
        print("\n正在打开 抖音 登录页面...")
        page.goto("https://www.douyin.com/")
        print("⏳ 请在浏览器中点击右上角的『登录』，使用抖音扫码。")
        input("👉 【重要】扫码登录成功，看到首页推荐流后，请回到这个命令行窗口，按下 Enter 键继续...")
        
        douyin_path = "douyin_auth.json"
        context.storage_state(path=douyin_path)
        print(f"✅ 抖音 登录凭证已保存至: {os.path.abspath(douyin_path)}")
        
        # 关闭浏览器
        browser.close()
        
        print("\n🎉 凭证导出完成！")
        print("💡 接下来，请将生成的 douyin_auth.json 上传到 Lightsail 服务器的项目中。")

if __name__ == "__main__":
    export_auth()
