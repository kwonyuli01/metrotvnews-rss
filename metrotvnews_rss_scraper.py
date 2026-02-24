#!/usr/bin/env python3
"""
MetroTV News RSS Feed Scraper - Channel Ekonomi
=================================================
Menggunakan Playwright (headless browser) untuk bypass proteksi.
Scrape halaman channel ekonomi + konten artikel lengkap.

Dijalankan otomatis via GitHub Actions + publish ke GitHub Pages.
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup, NavigableString
from datetime import datetime, timezone, timedelta
import time
import re
import os
import html
import hashlib

# ============================================================
# KONFIGURASI
# ============================================================

BASE_URL = "https://www.metrotvnews.com"
CHANNEL_URL = "https://www.metrotvnews.com/channel/ekonomi"

# ~8 artikel per halaman, ambil 3 halaman = ~24 artikel
LIST_PAGES = 3
MAX_ARTICLES = 20

FEED_TITLE = "MetroTV News - Ekonomi"
FEED_DESCRIPTION = "RSS Feed channel Ekonomi dari metrotvnews.com dengan konten artikel lengkap"
FEED_LINK = "https://www.metrotvnews.com/channel/ekonomi"

OUTPUT_FILE = "docs/feed.xml"
REQUEST_DELAY = 3

WIB = timezone(timedelta(hours=7))

BULAN_EN = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12
}

# ============================================================
# BROWSER SETUP
# ============================================================

browser = None
context = None
page = None


def init_browser():
    """Inisialisasi Playwright browser."""
    global browser, context, page

    pw = sync_playwright().start()

    browser = pw.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
        ]
    )

    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        locale='id-ID',
        timezone_id='Asia/Jakarta',
        extra_http_headers={
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        }
    )

    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['id-ID', 'id', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        window.chrome = { runtime: {} };
    """)

    page = context.new_page()
    print("[*] Browser Playwright berhasil diinisialisasi")
    return pw


def fetch_page(url, retries=3):
    """Fetch halaman menggunakan Playwright browser."""
    for attempt in range(retries):
        try:
            print(f"  [>] Fetching: {url}")
            response = page.goto(url, wait_until='domcontentloaded', timeout=30000)

            if response is None:
                print(f"  [!] Response None (percobaan {attempt+1}/{retries})")
                time.sleep(REQUEST_DELAY * 2)
                continue

            status = response.status
            print(f"  [>] Status: {status}")

            if status == 403 or status == 503:
                print(f"  [~] Challenge terdeteksi, menunggu...")
                time.sleep(8)
                content = page.content()
                if len(content) > 5000:
                    print(f"  [+] Berhasil melewati challenge ({len(content)} chars)")
                    return content
                else:
                    print(f"  [!] Gagal bypass (percobaan {attempt+1}/{retries})")
                    time.sleep(REQUEST_DELAY * 2)
                    continue

            if status == 200:
                time.sleep(2)
                content = page.content()
                print(f"  [+] Berhasil ({len(content)} chars)")
                return content

            print(f"  [!] Status {status} (percobaan {attempt+1}/{retries})")
            time.sleep(REQUEST_DELAY * 2)

        except Exception as e:
            print(f"  [!] Error: {e} (percobaan {attempt+1}/{retries})")
            if attempt < retries - 1:
                time.sleep(REQUEST_DELAY * 2)

    return None


def close_browser():
    """Tutup browser."""
    global browser, context
    try:
        if context:
            context.close()
        if browser:
            browser.close()
    except Exception:
        pass


# ============================================================
# PARSING FUNCTIONS
# ============================================================

def parse_list_pages():
    """Parse beberapa halaman channel untuk mendapatkan daftar artikel."""
    all_articles = []
    seen_links = set()

    for page_num in range(LIST_PAGES):
        if page_num == 0:
            url = CHANNEL_URL
        else:
            url = f"{CHANNEL_URL}?page={page_num}"

        print(f"\n[*] Scraping halaman list: {url}")
        html_content = fetch_page(url)
        if not html_content:
            continue

        soup = BeautifulSoup(html_content, 'lxml')

        # 1. Headline articles: div.main-news-head div.news-item h2 a
        for item in soup.select('div.main-news-head div.news-item'):
            link_tag = item.select_one('h2 a')
            if not link_tag:
                continue

            href = link_tag.get('href', '')
            title = link_tag.get_text(strip=True)
            img_tag = item.select_one('img')
            thumb = ''
            if img_tag:
                thumb = img_tag.get('src', '')

            if href and title and href not in seen_links:
                seen_links.add(href)
                if not href.startswith('http'):
                    href = BASE_URL + href
                all_articles.append({'title': title, 'link': href, 'thumb': thumb})

        # 2. Latest articles: div.content-item-list h3 a
        for item in soup.select('div.content-item-list'):
            link_tag = item.select_one('h3 a')
            if not link_tag:
                continue

            href = link_tag.get('href', '')
            title = link_tag.get_text(strip=True)
            img_tag = item.select_one('img')
            thumb = ''
            if img_tag:
                thumb = img_tag.get('src', '')

            if href and title and href not in seen_links:
                seen_links.add(href)
                if not href.startswith('http'):
                    href = BASE_URL + href
                all_articles.append({'title': title, 'link': href, 'thumb': thumb})

        print(f"  [+] Total artikel terkumpul: {len(all_articles)}")

        if len(all_articles) >= MAX_ARTICLES:
            break

        time.sleep(REQUEST_DELAY)

    return all_articles[:MAX_ARTICLES]


def parse_article_page(url):
    """Parse halaman artikel untuk mendapatkan konten lengkap."""
    print(f"  [>] Mengambil artikel: {url}")

    # Skip video articles (/play/)
    if '/play/' in url:
        print(f"  [~] Artikel video, skip konten detail")
        return None

    html_content = fetch_page(url)
    if not html_content:
        return None

    soup = BeautifulSoup(html_content, 'lxml')
    article_data = {}

    # JUDUL
    h1 = soup.select_one('h1')
    article_data['title'] = h1.get_text(strip=True) if h1 else ''

    # AUTHOR & TANGGAL: "Eko Nordiansyah • 24 February 2026 20:33"
    author_date = soup.select_one('p.pt-20.date')
    reporter = ''
    pub_date_str = ''
    if author_date:
        text = author_date.get_text(strip=True)
        # Split by bullet •
        if '•' in text:
            parts = text.split('•', 1)
            reporter = parts[0].strip()
            pub_date_str = parts[1].strip()
        else:
            pub_date_str = text

    # Fallback author dari div#author: "(Eko Nordiansyah)"
    if not reporter:
        author_div = soup.select_one('div#author')
        if author_div:
            reporter = author_div.get_text(strip=True).strip('()')

    article_data['reporter'] = reporter
    article_data['pub_date'] = parse_date(pub_date_str)

    # GAMBAR UTAMA
    main_image = ''
    news_img = soup.select_one('img.news-image')
    if news_img:
        main_image = news_img.get('src', '')
    if not main_image:
        og_image = soup.find('meta', property='og:image')
        if og_image:
            main_image = og_image.get('content', '')
    article_data['image'] = main_image

    # CAPTION (p.pt-10.date pertama, di bawah gambar)
    caption = ''
    caption_p = soup.select_one('p.pt-10.date')
    if caption_p:
        caption = caption_p.get_text(strip=True)
    article_data['caption'] = caption

    # KONTEN ARTIKEL: div.news-text > p (satu p besar berisi semua konten)
    content_parts = extract_content(soup)
    article_data['content'] = '\n\n'.join(content_parts)

    # TAGS: div.tag-item a
    tags = []
    for tag_link in soup.select('div.tag-item a'):
        tag_text = tag_link.get_text(strip=True)
        if tag_text and tag_text not in tags:
            tags.append(tag_text)
    article_data['tags'] = tags

    # KATEGORI
    article_data['category'] = 'Ekonomi'

    return article_data


def extract_content(soup):
    """Ekstrak konten dari div.news-text.

    HTML MetroTV menempatkan h2/ul/ol di dalam <p>,
    tapi parser auto-split jadi sibling. Jadi parse
    semua children dari div.news-text langsung.
    """
    content_parts = []

    news_text = soup.select_one('div.news-text')
    if not news_text:
        return content_parts

    for elem in news_text.children:
        if isinstance(elem, NavigableString):
            text = str(elem).strip().replace('\xa0', ' ')
            if text and len(text) > 3:
                content_parts.append(text)

        elif elem.name == 'br':
            continue

        elif elem.name == 'p':
            text = elem.get_text(strip=True).replace('\xa0', ' ')
            if text and len(text) > 5:
                content_parts.append(text)

        elif elem.name in ['h2', 'h3']:
            text = elem.get_text(strip=True)
            if text:
                content_parts.append(f"\n### {text}\n")

        elif elem.name == 'ul':
            for li in elem.find_all('li'):
                li_text = li.get_text(strip=True)
                if li_text:
                    content_parts.append(f"• {li_text}")

        elif elem.name == 'ol':
            for i, li in enumerate(elem.find_all('li'), 1):
                li_text = li.get_text(strip=True)
                if li_text:
                    content_parts.append(f"{i}. {li_text}")

        elif elem.name == 'div':
            classes = ' '.join(elem.get('class', []))
            # Skip Baca Juga, ads, player
            if any(skip in classes for skip in ['readother', 'ads', 'gliaplayer', 'banner']):
                continue

        elif elem.name in ['em', 'i']:
            text = elem.get_text(strip=True)
            if text and len(text) > 3:
                content_parts.append(text)

    return content_parts


# ============================================================
# DATE PARSING
# ============================================================

def parse_date(date_str):
    """Parse tanggal ke format RFC 822."""
    if not date_str:
        return datetime.now(WIB).strftime('%a, %d %b %Y %H:%M:%S +0700')

    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    # Format: "24 February 2026 20:33"
    m = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})\s+(\d{2}):(\d{2})', date_str)
    if m:
        day, month_str, year, hour, minute = m.groups()
        month_num = BULAN_EN.get(month_str.lower(), 0)
        if month_num:
            try:
                dt = datetime(int(year), month_num, int(day), int(hour), int(minute))
                return f"{days[dt.weekday()]}, {int(day):02d} {months[month_num-1]} {int(year)} {int(hour):02d}:{int(minute):02d}:00 +0700"
            except ValueError:
                pass

    return datetime.now(WIB).strftime('%a, %d %b %Y %H:%M:%S +0700')


# ============================================================
# RSS GENERATION
# ============================================================

def generate_rss(articles_data):
    """Generate file RSS XML."""
    print(f"\n[*] Generating RSS XML...")
    now = datetime.now(WIB).strftime('%a, %d %b %Y %H:%M:%S +0700')

    rss_items = []
    for article in articles_data:
        if not article:
            continue

        content_html = ''

        if article.get('image'):
            content_html += f'<p><img src="{html.escape(article["image"])}" alt="{html.escape(article.get("title", ""))}" style="max-width:100%;" /></p>\n'
        if article.get('caption'):
            content_html += f'<p><em>{html.escape(article["caption"])}</em></p>\n'
        if article.get('reporter'):
            content_html += f'<p><strong>Reporter:</strong> {html.escape(article["reporter"])}</p>\n'
        if article.get('content'):
            for para in article['content'].split('\n\n'):
                para = para.strip()
                if not para:
                    continue
                if para.startswith('### '):
                    content_html += f'<h3>{html.escape(para[4:])}</h3>\n'
                elif para.startswith('• '):
                    content_html += f'<p>{html.escape(para)}</p>\n'
                elif re.match(r'^\d+\. ', para):
                    content_html += f'<p>{html.escape(para)}</p>\n'
                else:
                    content_html += f'<p>{html.escape(para)}</p>\n'
        if article.get('tags'):
            tags_str = ', '.join(article['tags'])
            content_html += f'<p><strong>Tags:</strong> {html.escape(tags_str)}</p>\n'

        guid = article.get('link', hashlib.md5(article.get('title', '').encode()).hexdigest())

        rss_items.append({
            'title': article.get('title', 'Tanpa Judul'),
            'link': article.get('link', ''),
            'description': content_html,
            'pubDate': article.get('pub_date', now),
            'category': article.get('category', ''),
            'tags': article.get('tags', []),
            'guid': guid,
            'image': article.get('image', ''),
        })

    rss_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>{html.escape(FEED_TITLE)}</title>
    <description>{html.escape(FEED_DESCRIPTION)}</description>
    <link>{html.escape(FEED_LINK)}</link>
    <language>id</language>
    <lastBuildDate>{now}</lastBuildDate>
    <generator>MetroTV RSS Scraper - Playwright (GitHub Actions)</generator>
'''

    for item in rss_items:
        rss_xml += f'''    <item>
      <title><![CDATA[{item['title']}]]></title>
      <link>{html.escape(item['link'])}</link>
      <guid isPermaLink="true">{html.escape(item['guid'])}</guid>
      <pubDate>{item['pubDate']}</pubDate>
'''
        if item['category']:
            rss_xml += f'      <category><![CDATA[{item["category"]}]]></category>\n'
        for tag in item.get('tags', []):
            rss_xml += f'      <category><![CDATA[{tag}]]></category>\n'
        if item['image']:
            rss_xml += f'      <media:content url="{html.escape(item["image"])}" medium="image" />\n'
        rss_xml += f'      <description><![CDATA[{item["description"]}]]></description>\n'
        rss_xml += f'      <content:encoded><![CDATA[{item["description"]}]]></content:encoded>\n'
        rss_xml += '    </item>\n'

    rss_xml += '''  </channel>
</rss>'''

    return rss_xml


# ============================================================
# MAIN
# ============================================================

def main():
    """Fungsi utama."""
    print("=" * 60)
    print("  MetroTV News RSS Scraper - Ekonomi (Playwright)")
    print("=" * 60)
    print(f"  Feed Title : {FEED_TITLE}")
    print(f"  Output     : {OUTPUT_FILE}")
    print(f"  Max Artikel: {MAX_ARTICLES}")
    print(f"  List Pages : {LIST_PAGES}")
    print(f"  Source URL : {CHANNEL_URL}")
    print("=" * 60)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    pw = init_browser()

    try:
        # Step 1: Scrape halaman channel (multi-page)
        articles = parse_list_pages()

        if not articles:
            print("\n[!] Tidak ada artikel ditemukan.")
            return

        print(f"\n[*] Total {len(articles)} artikel akan diproses")

        # Step 2: Fetch konten lengkap setiap artikel
        articles_data = []
        for i, article in enumerate(articles):
            print(f"\n--- Artikel {i+1}/{len(articles)} ---")

            if '/play/' in article['link']:
                # Artikel video: gunakan info dari list page saja
                print(f"  [~] Video artikel, skip detail fetch")
                articles_data.append({
                    'title': article['title'],
                    'link': article['link'],
                    'content': '(Artikel video - klik link untuk menonton)',
                    'pub_date': datetime.now(WIB).strftime('%a, %d %b %Y %H:%M:%S +0700'),
                    'image': article.get('thumb', ''),
                    'reporter': '', 'editor': '',
                    'tags': [], 'category': 'Ekonomi', 'caption': '',
                })
                continue

            article_data = parse_article_page(article['link'])

            if article_data:
                if not article_data.get('title'):
                    article_data['title'] = article['title']
                article_data['link'] = article['link']
                if not article_data.get('image') and article.get('thumb'):
                    article_data['image'] = article['thumb']
                articles_data.append(article_data)
            else:
                articles_data.append({
                    'title': article['title'],
                    'link': article['link'],
                    'content': '(Konten tidak dapat diambil)',
                    'pub_date': datetime.now(WIB).strftime('%a, %d %b %Y %H:%M:%S +0700'),
                    'image': article.get('thumb', ''),
                    'reporter': '', 'editor': '',
                    'tags': [], 'category': 'Ekonomi', 'caption': '',
                })

            time.sleep(REQUEST_DELAY)

        # Step 3: Generate & simpan RSS
        rss_xml = generate_rss(articles_data)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(rss_xml)

        print(f"\n{'=' * 60}")
        print(f"  SELESAI! File: {OUTPUT_FILE}")
        print(f"  Total artikel: {len(articles_data)}")
        print(f"{'=' * 60}")

    finally:
        close_browser()
        try:
            pw.stop()
        except Exception:
            pass


if __name__ == '__main__':
    main()
