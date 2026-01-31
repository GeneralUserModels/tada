#!/usr/bin/env python3
"""
Test screenshot resizing and measure Qwen3-VL token counts.

Usage:
    python scripts/test_compression.py --dpi 72
    python scripts/test_compression.py --dpi 96
    python scripts/test_compression.py --dpi 144 --no-tokens  # skip token counting
"""

import argparse
import io
import subprocess
import sys
import tempfile
from pathlib import Path

from screeninfo import get_monitors


# Save to tmp_images in project root
TEMP_DIR = Path(__file__).resolve().parents[1] / "tmp_images"

# Default model for token counting
DEFAULT_MODEL = "Qwen/Qwen3-VL-30B-A3B-Instruct"


def get_screen_dpi():
    """Get the DPI of the primary monitor using screeninfo."""
    monitors = get_monitors()
    if not monitors:
        print("Warning: Could not detect any monitors, assuming 72 DPI")
        return 72.0
    
    # Use the primary monitor (first one, or one marked as primary)
    monitor = monitors[0]
    for m in monitors:
        if getattr(m, 'is_primary', False):
            monitor = m
            break
    
    # Calculate DPI from physical dimensions if available
    if monitor.width_mm and monitor.height_mm and monitor.width_mm > 0:
        # DPI = pixels / inches, where inches = mm / 25.4
        dpi_x = monitor.width / (monitor.width_mm / 25.4)
        dpi_y = monitor.height / (monitor.height_mm / 25.4)
        dpi = (dpi_x + dpi_y) / 2  # average of horizontal and vertical DPI
        return dpi
    else:
        # Fallback: assume standard Retina scaling
        # macOS Retina displays are typically ~220 DPI
        print("Warning: Physical monitor dimensions not available, assuming 220 DPI (Retina)")
        return 220.0


def take_screenshot():
    """Capture the screen using macOS screencapture."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        temp_path = f.name
    
    result = subprocess.run(
        ["screencapture", "-x", temp_path],
        capture_output=True
    )
    
    if result.returncode != 0:
        print(f"screencapture failed: {result.stderr.decode()}")
        sys.exit(1)
    
    return temp_path


def process_image(input_path, target_dpi, screen_dpi):
    """Resize an image based on target DPI, return processed image and stats."""
    from PIL import Image
    
    img = Image.open(input_path)
    original_size = Path(input_path).stat().st_size
    original_dims = img.size
    
    # Calculate resize factor from DPI ratio
    resize_factor = target_dpi / screen_dpi
    
    # Resize maintaining aspect ratio
    if abs(resize_factor - 1.0) > 0.01:  # only resize if factor differs from 1.0
        new_width = int(img.width * resize_factor)
        new_height = int(img.height * resize_factor)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    new_dims = img.size
    
    # Save as PNG to preserve quality
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    compressed_size = buffer.tell()
    buffer.seek(0)
    
    return {
        "image": img,
        "buffer": buffer,
        "original_size": original_size,
        "compressed_size": compressed_size,
        "original_dims": original_dims,
        "new_dims": new_dims,
        "resize_factor": resize_factor,
    }


def format_size(size_bytes):
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} GB"


def count_tokens(pil_image, model_name=DEFAULT_MODEL):
    """
    Count vision tokens for an image using tinker_cookbook's image processor.
    
    Returns token_count or None on error.
    """
    try:
        from tinker_cookbook.image_processing_utils import get_image_processor
        from tinker_cookbook.tokenizer_utils import get_tokenizer
        from tinker_cookbook.renderers.qwen3 import Qwen3VLInstructRenderer
        
        tokenizer = get_tokenizer(model_name)
        image_processor = get_image_processor(model_name)
        renderer = Qwen3VLInstructRenderer(tokenizer, image_processor)
        
        # Build a simple message with just the image
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "image": pil_image},
                {"type": "text", "text": "What is this?"},
            ]
        }]
        
        # Render to get token count
        prompt = renderer.build_generation_prompt(messages)
        return prompt.length
        
    except Exception as e:
        print(f"Warning: Could not count tokens: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Test screenshot resizing for VLM token usage"
    )
    parser.add_argument(
        "--dpi", "-d", type=int, default=None,
        help="Target DPI (default: screen DPI, i.e. no resize)"
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output file path (default: tmp_images/)"
    )
    parser.add_argument(
        "--no-show", action="store_true",
        help="Don't open the image after saving"
    )
    parser.add_argument(
        "--input", "-i", type=str, default=None,
        help="Use existing image instead of taking screenshot"
    )
    parser.add_argument(
        "--no-tokens", action="store_true",
        help="Skip counting vision tokens"
    )
    parser.add_argument(
        "--model", "-m", type=str, default=DEFAULT_MODEL,
        help=f"Model for token counting (default: {DEFAULT_MODEL})"
    )
    
    args = parser.parse_args()
    
    # Get screen DPI
    screen_dpi = get_screen_dpi()
    print(f"Detected screen DPI: {screen_dpi:.1f}")
    
    # Use screen DPI if no target specified
    target_dpi = args.dpi if args.dpi else screen_dpi
    
    # Get input image
    if args.input:
        input_path = args.input
        print(f"Using input image: {input_path}")
    else:
        print("Taking screenshot...")
        input_path = take_screenshot()
        print(f"Screenshot saved to: {input_path}")
    
    # Process
    print(f"\nProcessing: target DPI={target_dpi} (from screen DPI={screen_dpi:.1f})")
    result = process_image(input_path, target_dpi, screen_dpi)
    
    # Output path
    if args.output:
        output_path = args.output
    else:
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        output_path = TEMP_DIR / f"dpi{target_dpi}.png"
    
    # Save
    with open(output_path, "wb") as f:
        f.write(result["buffer"].getvalue())
    
    # Count tokens by default
    token_count = None
    if not args.no_tokens:
        print("Counting tokens...")
        token_count = count_tokens(result["image"], args.model)
    
    # Print stats
    print("\n" + "=" * 50)
    print("RESIZE RESULTS")
    print("=" * 50)
    print(f"Screen DPI:          {screen_dpi:.1f}")
    print(f"Target DPI:          {target_dpi}")
    print(f"Resize factor:       {result['resize_factor']:.2%}")
    print("-" * 50)
    print(f"Original dimensions: {result['original_dims'][0]} x {result['original_dims'][1]}")
    print(f"New dimensions:      {result['new_dims'][0]} x {result['new_dims'][1]}")
    print(f"Original size:       {format_size(result['original_size'])}")
    print(f"New size:            {format_size(result['compressed_size'])}")
    if token_count is not None:
        print("-" * 50)
        print(f"Vision tokens:       {token_count:,}")
    print("=" * 50)
    print(f"Output: {output_path}")
    
    # Show by default
    if not args.no_show:
        subprocess.run(["open", str(output_path)])


if __name__ == "__main__":
    main()
