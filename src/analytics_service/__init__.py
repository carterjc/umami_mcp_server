from . import server
import asyncio
import subprocess
import sys
import os

def setup_crawl4ai():
    """Run crawl4ai-setup command."""
    try:
        # Get the path to the virtual environment's bin directory
        venv_bin = os.path.dirname(sys.executable)
        setup_cmd = os.path.join(venv_bin, "crawl4ai-setup")
        
        # Run the command with output redirected to devnull
        with open(os.devnull, 'w') as devnull:
            subprocess.run([setup_cmd], check=True, stdout=devnull, stderr=devnull)
    except subprocess.CalledProcessError:
        raise RuntimeError("Failed to initialize crawl4ai. Please check the logs for more details.")
    except FileNotFoundError:
        raise RuntimeError("crawl4ai-setup command not found. Please ensure crawl4ai is properly installed.")

def main():
    """Main entry point for the package."""
    setup_crawl4ai()
    asyncio.run(server.main())

# Optionally expose other important items at package level
__all__ = ['main', 'server']