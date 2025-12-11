from pathlib import Path
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import sys

def convert_html_to_markdown(html_path: Path) -> str:
    """
    Converts a single HTML file to a Markdown string.
    Removes navigation bars and extraneous content before conversion.

    Args:
        html_path: Path to the input HTML file.

    Returns:
        The converted Markdown content.
    """
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Remove navigation elements (heuristic based on common Sphinx/PyData themes)
        for selector in [
            "nav", 
            ".bd-sidebar", 
            ".bd-header", 
            ".bd-footer", 
            ".skip-link", 
            ".pst-scroll-pixel-helper",
            ".pst-async-banner-revealer",
            "script",
            "style",
            "noscript",
            ".headerlink" # Sphinx anchor links
        ]:
            for tag in soup.select(selector):
                tag.decompose()
                
        # Get the main content if possible
        main_content = soup.select_one("main") or soup.select_one("article") or soup.select_one(".bd-content") or soup.body
        
        if main_content:
            text = str(main_content)
        else:
            text = str(soup)

        markdown = md(text, heading_style="atx")
        
        # Add a title/header indicating origin file?
        header = f"\n\n<!-- Source: {html_path.name} -->\n\n"
        return header + markdown

    except Exception as e:
        print(f"Error converting {html_path}: {e}", file=sys.stderr)
        return f"\n\n<!-- Error converting {html_path.name} -->\n\n"
