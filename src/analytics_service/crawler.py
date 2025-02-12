from crawl4ai import AsyncWebCrawler
import base64
from io import BytesIO, StringIO
from PIL import Image
import asyncio
import logging
import os
import sys
import contextlib

@contextlib.contextmanager
def capture_output():
    """Temporarily capture stdout and stderr."""
    # Save the original stdout/stderr
    old_stdout, old_stderr = sys.stdout, sys.stderr
    # Create string buffers
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    
    try:
        # Replace stdout/stderr with our buffers
        sys.stdout, sys.stderr = stdout_buffer, stderr_buffer
        yield
    finally:
        # Restore original stdout/stderr
        sys.stdout, sys.stderr = old_stdout, old_stderr

def optimize_screenshot(base64_data: str, max_size: int = 100_000) -> str:
    """Optimize screenshot to reduce size while maintaining quality.
    
    Args:
        base64_data: Original base64 encoded image
        max_size: Target maximum size in bytes for the base64 string
    
    Returns:
        Optimized base64 encoded image
    """
    try:
        # Decode base64 to bytes
        image_data = base64.b64decode(base64_data)
        
        # Open image with PIL
        img = Image.open(BytesIO(image_data))
        
        # Initial quality and size parameters
        quality = 85
        max_dimension = 1920
        
        # Resize if dimensions are too large
        if max(img.size) > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = tuple(int(dim * ratio) for dim in img.size)
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary (removes alpha channel)
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1])
            img = background
        
        # Compress image
        buffer = BytesIO()
        while quality > 10:
            buffer.seek(0)
            buffer.truncate()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            
            # Check if size is within limit
            if len(buffer.getvalue()) < (max_size * 3/4):  # 3/4 to account for base64 overhead
                break
                
            quality -= 10
        
        # Convert back to base64
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        # Return original data if optimization fails
        return base64_data
    finally:
        # Clean up resources
        if 'img' in locals():
            img.close()
        if 'buffer' in locals():
            buffer.close()

class CrawlingAPI:
    def __init__(self):
        # Configure crawl4ai logging
        self.logger = logging.getLogger('crawl4ai')
        self.logger.setLevel(logging.ERROR)  # Only log errors
        
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Add file handler if not already added
        if not self.logger.handlers:
            handler = logging.FileHandler(os.path.join(log_dir, 'crawl4ai.log'))
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(handler)
            
        # Prevent propagation to root logger
        self.logger.propagate = False
    
    async def get_screenshot(self, url: str, timeout: int = 30):
        """Get a screenshot of a webpage.
        
        Args:
            url: URL to take screenshot of
            timeout: Timeout in seconds for the screenshot operation
            
        Returns:
            Base64 encoded screenshot
        
        Raises:
            RuntimeError: If screenshot operation fails
        """
        try:
            crawler = AsyncWebCrawler(verbose=False)
            with capture_output():  # Capture all stdout/stderr during crawl
                async with crawler:
                    task = asyncio.create_task(crawler.arun(url=url, screenshot=True))
                    result = await asyncio.wait_for(task, timeout=timeout)
                    
                    if not result or not result.screenshot:
                        raise RuntimeError("No screenshot data returned")
                    
                    # Remove the data URI prefix if present
                    base64_img = result.screenshot
                    if "data:image" in base64_img:
                        base64_img = base64_img.split(",")[1]
                        
                    # Optimize the screenshot
                    return optimize_screenshot(base64_img)
        except asyncio.TimeoutError:
            raise RuntimeError(f"Screenshot operation timed out after {timeout} seconds")
        except Exception as e:
            raise RuntimeError(f"Failed to get screenshot: {str(e)}")
        
    async def get_html(self, url: str, timeout: int = 30):
        """Get the HTML of a webpage.
        
        Args:
            url: URL to get HTML from
            timeout: Timeout in seconds for the operation
            
        Returns:
            HTML content as string
            
        Raises:
            RuntimeError: If operation fails
        """
        try:
            crawler = AsyncWebCrawler(verbose=False)
            with capture_output():  # Capture all stdout/stderr during crawl
                async with crawler:
                    task = asyncio.create_task(crawler.arun(url=url, screenshot=False))
                    result = await asyncio.wait_for(task, timeout=timeout)
                    
                    if not result or not result.html:
                        raise RuntimeError("No HTML data returned")
                        
                    return result.html
        except asyncio.TimeoutError:
            raise RuntimeError(f"HTML fetch operation timed out after {timeout} seconds")
        except Exception as e:
            raise RuntimeError(f"Failed to get HTML: {str(e)}")
        