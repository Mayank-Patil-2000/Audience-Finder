import asyncio
import argparse
import csv
import os
import re
from datetime import datetime
from playwright.async_api import async_playwright

def parse_count(raw_str):
    if not raw_str: return None
    match = re.search(r'([\d.]+)\s*([KMBkmb])?', raw_str.replace(',', '').strip())
    if not match: return None
    number = float(match.group(1))
    multiplier = match.group(2).upper() if match.group(2) else ''
    multipliers = {'K': 1e3, 'M': 1e6, 'B': 1e9}
    return int(number * multipliers.get(multiplier, 1))

async def main():
    parser = argparse.ArgumentParser(description="TikTok Creator Finder")
    parser.add_argument("--tags", type=str, required=True, help="Comma-separated hashtags (e.g., collegelife,introvert)")
    parser.add_argument("--min", type=int, default=200, help="Minimum followers")
    parser.add_argument("--max", type=int, default=3000, help="Maximum followers")
    parser.add_argument("--bio-keywords", type=str, default="", help="Comma-separated words that MUST appear in their bio")
    parser.add_argument("--limit", type=int, default=10, help="Max creators to find per tag")
    args = parser.parse_args()

    tags = [t.strip() for t in args.tags.split(",")]
    bio_keywords = [k.strip().lower() for k in args.bio_keywords.split(",")] if args.bio_keywords else []
    
    csv_file = "creator-submissions.csv"
    file_exists = os.path.isfile(csv_file)
    
    async with async_playwright() as p:
        # Launching a visible browser helps bypass TikTok's automated bot detection without logging in.
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Date found', 'Handle', 'Profile URL', 'Followers', 'Bio', 'Matched Tag'])

            for tag in tags:
                print(f"[*] Searching #{tag}...")
                await page.goto(f"https://www.tiktok.com/tag/{tag}", wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(4)

                # Extract handles from the tag feed
                hrefs = await page.eval_on_selector_all('a[href*="/@"]', 'elements => elements.map(e => e.href)')
                handles = list(set([re.search(r'/@([A-Za-z0-9._]+)', h).group(1) for h in hrefs if '/@' in h]))
                
                kept_count = 0
                for handle in handles:
                    if kept_count >= args.limit: break
                    
                    await page.goto(f"https://www.tiktok.com/@{handle}", wait_until="domcontentloaded", timeout=45000)
                    await asyncio.sleep(3) # Pause to mimic human browsing
                    
                    # Extract follower count
                    followers_text = await page.locator('[data-e2e="followers-count"]').first.text_content()
                    followers = parse_count(followers_text) if followers_text else 0
                    
                    # Extract bio for Modash-style keyword filtering
                    bio_text = ""
                    try:
                        bio_text = await page.locator('[data-e2e="user-bio"]').first.text_content()
                    except:
                        pass
                    
                    # Apply Filters
                    if followers < args.min or followers > args.max:
                        print(f"  [-] Skipped @{handle} (Followers: {followers})")
                        continue
                        
                    if bio_keywords and not any(word in bio_text.lower() for word in bio_keywords):
                        print(f"  [-] Skipped @{handle} (Bio didn't match keywords)")
                        continue

                    # Save qualifying creator
                    print(f"  [+] Kept @{handle} (Followers: {followers})")
                    writer.writerow([
                        datetime.now().strftime("%Y-%m-%d"),
                        handle,
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