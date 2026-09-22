import asyncio
import argparse
import csv
import os
import re
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

def parse_count(raw_str):
    if not raw_str: return None
    match = re.search(r'([\d.]+)\s*([KMBkmb])?', raw_str.replace(',', '').strip())
    if not match: return None
    number = float(match.group(1))
    multiplier = match.group(2).upper() if match.group(2) else ''
    multipliers = {'K': 1e3, 'M': 1e6, 'B': 1e9}
    return int(number * multipliers.get(multiplier, 1))

def extract_email(text):
    if not text:
        return None
    match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    return match.group(0) if match else None

async def main():
    parser = argparse.ArgumentParser(description="TikTok Creator Finder")
    parser.add_argument("--tags", type=str, required=True, help="Comma-separated hashtags (e.g., collegelife,introvert)")
    parser.add_argument("--min", type=int, default=200, help="Minimum followers")
    parser.add_argument("--max", type=int, default=3000, help="Maximum followers")
    parser.add_argument("--bio-keywords", type=str, default="", help="Comma-separated words that MUST appear in their bio")
    parser.add_argument("--require-email", action="store_true", default=True, help="Only keep creators with an email in their bio")
    parser.add_argument("--limit", type=int, default=10, help="Max creators to find per tag")
    args = parser.parse_args()

    tags = [t.strip() for t in args.tags.split(",")]
    bio_keywords = [k.strip().lower() for k in args.bio_keywords.split(",")] if args.bio_keywords else []
    
    csv_file = "creator-submissions.csv"
    file_exists = os.path.isfile(csv_file)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Date found', 'Handle', 'Email', 'Profile URL', 'Followers', 'Bio', 'Matched Tag'])

            for tag in tags:
                print(f"[*] Searching #{tag}...")
                await page.goto(f"https://www.tiktok.com/tag/{tag}", wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(4)

                hrefs = await page.eval_on_selector_all('a[href*="/@"]', 'elements => elements.map(e => e.href)')
                
                matches = [re.search(r'/@([A-Za-z0-9._]+)', h) for h in hrefs]
                handles = list(set([m.group(1) for m in matches if m]))
                
                kept_count = 0
                for handle in handles:
                    if kept_count >= args.limit: break
                    
                    await page.goto(f"https://www.tiktok.com/@{handle}", wait_until="domcontentloaded", timeout=45000)
                    await asyncio.sleep(3)
                    
                    # Prevent crashes by catching timeout errors if the page is blocked or dead
                    try:
                        followers_text = await page.locator('[data-e2e="followers-count"]').first.text_content(timeout=5000)
                        followers = parse_count(followers_text) if followers_text else 0
                        
                        bio_text = await page.locator('[data-e2e="user-bio"]').first.text_content(timeout=2000)
                    except Exception:
                        print(f"  [-] Skipped @{handle} (Profile failed to load or captcha blocked)")
                        continue
                    
                    email = extract_email(bio_text)

                    if args.require_email and not email:
                        print(f"  [-] Skipped @{handle} (No email found in bio)")
                        continue

                    if followers < args.min or followers > args.max:
                        print(f"  [-] Skipped @{handle} (Followers: {followers})")
                        continue
                        
                    if bio_keywords and not any(word in bio_text.lower() for word in bio_keywords):
                        print(f"  [-] Skipped @{handle} (Bio didn't match keywords)")
                        continue

                    print(f"  [+] Kept @{handle} | Email: {email} | Followers: {followers}")
                    writer.writerow([
                        datetime.now().strftime("%Y-%m-%d"),
                        handle,
                        email,
                        f"https://www.tiktok.com/@{handle}",
                        followers,
                        bio_text.replace('\n', ' '),
                        tag
                    ])
                    f.flush()
                    kept_count += 1

        await browser.close()
        print(f"\nDone! Saved to {csv_file}")

if __name__ == "__main__":
    asyncio.run(main())