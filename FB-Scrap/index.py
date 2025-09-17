import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import sys
import json
import re

# Configuration
PAGE_URL = "https://www.facebook.com/******/photos_by"
DOWNLOAD_DIR = "fb_images"
NUM_SCROLLS = 5  # Number of times to scroll to load more images
DOWNLOAD_IMAGES = True  # Set to False to only list URLs

# Create directory to save images
if DOWNLOAD_IMAGES:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def setup_chrome_driver():
    """Setup Chrome WebDriver with fallback options"""
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")  # Comment this line if you want to see the browser
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # Try to find Chrome in common locations
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(os.getenv('USERNAME', ''))
        ]
        
        for path in chrome_paths:
            if os.path.exists(path):
                options.binary_location = path
                break
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        print("Chrome WebDriver initialized successfully!")
        return driver
    except Exception as e:
        print(f"Failed to initialize Chrome WebDriver: {e}")
        return None

def setup_firefox_driver():
    """Setup Firefox WebDriver as fallback"""
    try:
        options = webdriver.FirefoxOptions()
        options.add_argument("--headless")
        # Explicitly set the Firefox binary location
        options.binary_location = r"C:\Program Files\Mozilla Firefox\firefox.exe"
        driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()), options=options)
        print("Firefox WebDriver initialized successfully!")
        return driver
    except Exception as e:
        print(f"Failed to initialize Firefox WebDriver: {e}")
        return None

def get_best_image_url(thumbnail_url):
    """Convert thumbnail URL to the best possible image URL"""
    if not thumbnail_url:
        return None
    
    # Facebook image URL patterns - try multiple approaches
    url = thumbnail_url
    
    # Approach 1: Remove size parameters
    size_patterns = [
        's206x206', 's320x320', 's960x960', 's50x50', 's100x100',
        's150x150', 's200x200', 's300x300', 's400x400', 's500x500',
        's600x600', 's700x700', 's800x800', 's900x900'
    ]
    
    for pattern in size_patterns:
        url = url.replace(pattern, '')
    
    # Approach 2: Remove thumbnail suffixes
    if '_n.jpg' in url:
        url = url.replace('_n.jpg', '.jpg')
    elif '_n.png' in url:
        url = url.replace('_n.png', '.png')
    elif '_q.jpg' in url:
        url = url.replace('_q.jpg', '.jpg')
    elif '_q.png' in url:
        url = url.replace('_q.png', '.png')
    
    # Approach 3: Clean up parameters
    url = url.replace('&stp=dst-jpg_', '&stp=')
    url = url.replace('&stp=c0.', '&stp=')
    
    # Approach 4: Try to get base URL with minimal parameters
    if 'scontent' in url:
        base_parts = url.split('?')[0]
        if base_parts.endswith('.jpg') or base_parts.endswith('.png'):
            # Keep only essential parameters
            params = []
            if '?' in url:
                param_part = url.split('?')[1]
                for param in param_part.split('&'):
                    if not any(size in param for size in ['s206x206', 's320x320', 's960x960', 's50x50', 's100x100']):
                        params.append(param)
            
            if params:
                return f"{base_parts}?{'&'.join(params)}"
            else:
                return base_parts
    
    return url

def find_all_images(driver):
    """Find all possible images using multiple approaches"""
    all_images = []
    
    # Method 1: Direct image elements
    try:
        images = driver.find_elements(By.CSS_SELECTOR, "img[src*='scontent']")
        for img in images:
            src = img.get_attribute("src")
            if src:
                all_images.append({
                    "url": src,
                    "type": "direct_image",
                    "element": img
                })
    except Exception as e:
        print(f"Error finding direct images: {e}")
    
    # Method 2: Photo links
    try:
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/photo/']")
        for link in links:
            href = link.get_attribute("href")
            if href:
                all_images.append({
                    "url": href,
                    "type": "photo_link",
                    "element": link
                })
    except Exception as e:
        print(f"Error finding photo links: {e}")
    
    # Method 3: Extract from page source
    try:
        page_source = driver.page_source
        # Look for image URLs in the page source
        img_pattern = r'https://scontent[^"]*\.(?:jpg|png)(?:\?[^"]*)?'
        matches = re.findall(img_pattern, page_source)
        
        for match in matches:
            if match not in [img["url"] for img in all_images]:
                all_images.append({
                    "url": match,
                    "type": "page_source",
                    "element": None
                })
    except Exception as e:
        print(f"Error extracting from page source: {e}")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_images = []
    for img in all_images:
        if img["url"] not in seen:
            seen.add(img["url"])
            unique_images.append(img)
    
    return unique_images

def download_image(url, filename, max_retries=3):
    """Download image with multiple retry strategies"""
    headers_list = [
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': PAGE_URL,
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        },
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Accept': 'image/webp,*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': PAGE_URL,
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        },
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Referer': PAGE_URL,
        }
    ]
    
    for attempt in range(max_retries):
        for headers in headers_list:
            try:
                response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
                if response.status_code == 200:
                    # Determine file extension
                    content_type = response.headers.get('content-type', '')
                    if 'jpeg' in content_type or 'jpg' in content_type:
                        ext = '.jpg'
                    elif 'png' in content_type:
                        ext = '.png'
                    else:
                        ext = '.jpg'
                    
                    if not filename.endswith(ext):
                        filename = filename.replace('.jpg', ext).replace('.png', ext)
                    
                    filepath = os.path.join(DOWNLOAD_DIR, filename)
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    print(f"Downloaded: {filename} ({len(response.content)} bytes)")
                    return True
                else:
                    print(f"Attempt {attempt + 1}: HTTP {response.status_code} for {url}")
            except Exception as e:
                print(f"Attempt {attempt + 1}: Error downloading {url}: {e}")
        
        if attempt < max_retries - 1:
            time.sleep(2)
    
    return False

# Try to setup WebDriver
driver = setup_chrome_driver()
if driver is None:
    print("Chrome not available, trying Firefox...")
    driver = setup_firefox_driver()

if driver is None:
    print("ERROR: Neither Chrome nor Firefox is available.")
    print("Please install one of the following browsers:")
    print("1. Google Chrome: https://www.google.com/chrome/")
    print("2. Mozilla Firefox: https://www.mozilla.org/firefox/")
    sys.exit(1)

try:
    print(f"Navigating to: {PAGE_URL}")
    driver.get(PAGE_URL)
    
    # Wait for page to load
    time.sleep(5)
    
    # Scroll the page to load more images
    print(f"Scrolling {NUM_SCROLLS} times to load more images...")
    for i in range(NUM_SCROLLS):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)  # Wait for images to load
        print(f"Scroll {i+1}/{NUM_SCROLLS} completed")

    # Collect image URLs
    print("Collecting image URLs...")
    image_elements = find_all_images(driver)
    print(f"Found {len(image_elements)} unique image elements")

    downloaded = set()
    successful_downloads = 0
    all_image_urls = []
    
    # Process image elements
    for idx, img in enumerate(image_elements):
        original_url = img["url"]
        if not original_url:
            continue
            
        # For photo links, try to get better image URL
        if img["type"] == "photo_link":
            # Try to get the best possible image URL from the photo link
            better_url = get_best_image_url(original_url)
            if better_url:
                original_url = better_url
        
        # For direct images, try to improve the URL
        elif img["type"] == "direct_image":
            better_url = get_best_image_url(original_url)
            if better_url:
                original_url = better_url
        
        all_image_urls.append({
            "index": f"img_{idx}",
            "original_url": img["url"],
            "improved_url": original_url,
            "type": img["type"]
        })
        
        if DOWNLOAD_IMAGES and original_url and original_url not in downloaded:
            if download_image(original_url, f"image_{idx}.jpg"):
                downloaded.add(original_url)
                successful_downloads += 1

    print(f"\nSummary:")
    print(f"Total image elements found: {len(image_elements)}")
    print(f"Total unique URLs collected: {len(all_image_urls)}")
    if DOWNLOAD_IMAGES:
        print(f"Successfully downloaded: {successful_downloads} images to '{DOWNLOAD_DIR}' folder.")
    
    # Save all image URLs to a JSON file
    urls_file = "image_urls.json"
    with open(urls_file, 'w', encoding='utf-8') as f:
        json.dump(all_image_urls, f, indent=2, ensure_ascii=False)
    print(f"All image URLs saved to: {urls_file}")
    
    # Also save as a simple text file for easy viewing
    txt_file = "image_urls.txt"
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write("Facebook Image URLs\n")
        f.write("=" * 50 + "\n\n")
        for item in all_image_urls:
            f.write(f"{item['index']} ({item['type']}):\n")
            f.write(f"  Original: {item['original_url']}\n")
            f.write(f"  Improved: {item['improved_url']}\n")
            f.write("-" * 30 + "\n")
    print(f"Image URLs also saved to: {txt_file}")

except Exception as e:
    print(f"An error occurred: {e}")
finally:
    driver.quit()
    print("WebDriver closed.")
