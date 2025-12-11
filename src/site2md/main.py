import cyclopts
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
from rich.console import Console
from rich.progress import Progress

from site2md.finder import find_html_files
from site2md.converter import convert_html_to_markdown
from site2md.merger import merge_markdowns

app = cyclopts.App(name="site2md")
console = Console()

def download_website(url: str) -> Path:
    """
    Downloads a website using wget to a temporary directory.
    Returns the path to the temporary directory containing the downloaded site.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="site2md_wget_"))
    console.print(f"[cyan]Downloading {url} to {temp_dir}...[/cyan]")
    
    # wget command as requested:
    # wget --mirror --convert-links --adjust-extension --page-requisites --no-parent <url> -P <temp_dir>
    cmd = [
        "wget",
        "--mirror",
        "--convert-links",
        "--adjust-extension",
        "--page-requisites",
        "--no-parent",
        url,
        "-P",
        str(temp_dir)
    ]
    
    try:
        # We don't use check=True because wget might return non-zero for minor errors (like 404 on robots.txt)
        # Exit code 8 is common for "Server issued an error response" which happens during recursive fetch.
        subprocess.run(cmd, check=False, capture_output=False)
    except Exception as e:
        console.print(f"[red]Error executing wget:[/red] {e}")
        shutil.rmtree(temp_dir)
        sys.exit(1)
        
    return temp_dir

@app.command(name="build")
def build(
    input_source: str, # Changed name to be more generic, handled as str
    *,
    output: Path = Path("complete_manual.md"),
    keep_temp: bool = False
):
    """
    Builds a single Markdown file from a directory of HTML files or a URL.

    Args:
        input_source: Directory containing HTML files OR a URL (starts with http).
        output: Path where the result Markdown should be saved.
        keep_temp: If True, temporary download directories are not deleted.
    """
    
    temp_download_dir = None
    input_dir = None

    # 1. Determine input type
    if input_source.startswith("http://") or input_source.startswith("https://"):
        temp_download_dir = download_website(input_source)
        # wget creates the host directory inside the prefix
        # e.g. temp/yasa-sleep.org/
        # We need to find where the files are.
        # usually it is temp_dir / domain
        # Let's just treat temp_download_dir as the root for search, finder logic will handle subdirs.
        input_dir = temp_download_dir
    else:
        input_dir = Path(input_source)
        if not input_dir.exists():
            console.print(f"[red]Error:[/red] Input '{input_dir}' does not exist.")
            sys.exit(1)

    try:
        # 1. Find HTML files
        console.print(f"[bold green]Scanning[/bold green] {input_dir} for HTML files...")
        html_files = find_html_files(input_dir)
        if not html_files:
            console.print("[yellow]No HTML files found.[/yellow]")
            sys.exit(0)

        console.print(f"Found [bold]{len(html_files)}[/bold] HTML files.")

        # 2. Convert to Markdown
        markdown_contents = []
        
        with Progress() as progress:
            task = progress.add_task("[cyan]Converting HTML to Markdown...", total=len(html_files))
            
            for html_file in html_files:
                # convert
                content = convert_html_to_markdown(html_file)
                markdown_contents.append(content)
                progress.advance(task)

        # 3. Merge Markdowns
        if markdown_contents:
            console.print(f"[bold green]Merging[/bold green] {len(markdown_contents)} files into {output}...")
            merge_markdowns(markdown_contents, output)
            console.print(f"[bold white on green]Success![/bold white on green] Markdown created at {output}")
        else:
            console.print("[red]No content was generated.[/red]")

    finally:
        # Cleanup temp dir if we created one and not keeping it
        if temp_download_dir and not keep_temp:
            console.print(f"[dim]Cleaning up temporary files provided at {temp_download_dir} ...[/dim]")
            shutil.rmtree(temp_download_dir)
        elif temp_download_dir:
             console.print(f"[dim]Temporary files kept at {temp_download_dir}[/dim]")

if __name__ == "__main__":
    app()
