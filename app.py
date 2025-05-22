import csv
import requests
import re
import time
import random
import asyncio
import streamlit as st
from bs4 import BeautifulSoup
import google.generativeai as genai
import nest_asyncio
from playwright.async_api import async_playwright
from io import StringIO

nest_asyncio.apply()

# ========== CONFIG ==========
API_KEYS = [
    "AIzaSyAl-aYFguI3wgdEvOK-1OsPp7mWJISwT0I",
    "AIzaSyAVyOWmZCsV_zOxGIq17EWlYLaIeMKtKjA"
]
api_index = 0

def rotate_api_key():
    global api_index
    key = API_KEYS[api_index]
    genai.configure(api_key=key)
    api_index = (api_index + 1) % len(API_KEYS)

# ========== SCRAPING ==========
def scrape_with_bs(domain):
    pages_to_try = [
        f"https://{domain}/about", f"https://{domain}/about-us", f"https://{domain}/company",
        f"https://{domain}", f"https://{domain}/products", f"https://{domain}/services"
    ]
    scraped_content = []

    for url in pages_to_try:
        try:
            response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                meta_description = soup.find("meta", attrs={"name": "description"}) or \
                                   soup.find("meta", attrs={"property": "og:description"})
                if meta_description:
                    scraped_content.append(meta_description["content"].strip())
                paragraphs = ' '.join([p.get_text(separator=' ').strip() for p in soup.find_all(['p', 'h2', 'h3'])])
                scraped_content.append(paragraphs)

                cleaned_content = re.sub(
                    r'\b(learn more|contact us|careers|privacy policy|terms of service|subscribe|read more)\b',
                    '', ' '.join(scraped_content), flags=re.IGNORECASE
                )
                return cleaned_content[:3000] if cleaned_content else ""
        except:
            pass
    return ""

async def scrape_with_playwright(domain):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        url = f"https://{domain}"
        try:
            await page.goto(url, timeout=10000)
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            paragraphs = ' '.join([p.get_text(separator=' ').strip() for p in soup.find_all(['p', 'h2', 'h3'])])
            await browser.close()
            return paragraphs[:3000] if paragraphs else ""
        except:
            await browser.close()
            return ""

# ========== GEMINI ==========
def generate_company_info(content):
    try:
        if not content.strip():
            return "No Name", ""

        prompt = f"""
Extract the company name and write a professional company description based on the provided text.
- Provide the exact company name as it appears on the website.
- Description should focus on services offered and the target audience but it needs to be complete and ready to use for clients, No extra remarks.
- Keep the description under 250 words.
- Avoid placeholders like [Company Name] or any extra remark either clean description and name or say "No Description".
- Format response as:
  Company Name: <name>
  Description: <description>

Content: {content}
"""
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        match = re.search(r'Company Name: (.*?)\nDescription: (.*)', response.text, re.DOTALL)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return "No Name", ""
    except:
        return "Error", ""

# ========== PROCESS ==========
async def process_domains(domains):
    names, descriptions = [], []
    for index, domain in enumerate(domains, start=1):
        st.info(f"Processing {index}/{len(domains)}: {domain}")
        try:
            content = scrape_with_bs(domain)
            if not content:
                content = await scrape_with_playwright(domain)
            if content:
                rotate_api_key()
                time.sleep(random.uniform(1, 3))
                name, desc = generate_company_info(content)
            else:
                name, desc = "", ""
        except:
            name, desc = "", ""
        names.append("" if name in ["No Name", "Error"] else name)
        descriptions.append("" if desc in ["No Description", "Error", "No content found", "No meaningful content found"] else desc)
    return names, descriptions

# ========== UI ==========
st.title("Domain Intelligence Extractor")
st.markdown("Upload a CSV of domains. This app scrapes content, uses Gemini, and shows company names and descriptions.")

uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

if uploaded_file:
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    reader = csv.reader(stringio)
    domains = [row[0] for row in reader if row]

    if st.button("Process Domains"):
        names, descriptions = asyncio.run(process_domains(domains))
        result_data = list(zip(domains, names, descriptions))

        if result_data:
            st.success("Processing complete.")
            st.markdown("### Result")
            st.dataframe(result_data, use_container_width=True)

            # Add Copy to Clipboard Button
            result_text = "\n".join([f"{d}, {n}, {desc}" for d, n, desc in result_data])
            st.markdown(
                f"""
                <button onclick="navigator.clipboard.writeText(`{result_text}`)">📋 Copy to Clipboard</button>
                """,
                unsafe_allow_html=True,
            )
