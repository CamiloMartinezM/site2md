#!/bin/bash

# site2md Installation Script
# Supports Linux and macOS

set -e

echo "╔═══════════════════════════════════════════════════════╗"
echo "║             site2md - Installer                      ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Check Python version
echo "[1/3] Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed!"
    echo "   Please install Python 3.10 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✓ Found Python $PYTHON_VERSION"

# Check pip
echo ""
echo "[2/3] Checking pip..."
if ! command -v pip3 &> /dev/null; then
    echo "❌ Error: pip3 is not installed!"
    echo "   Installing pip..."
    python3 -m ensurepip --upgrade
fi
echo "✓ pip is ready"

# Install package
echo ""
echo "[3/3] Installing site2md..."
pip3 install --upgrade pip
pip3 install -e .

echo "✓ Installation complete!"

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║              Installation Successful! 🎉              ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""
echo "Usage:"
echo "  • Local directory:    site2md build ./my_site --output manual.md"
echo "  • Remote page:        site2md build https://example.com --output page.md"
echo "  • Help:               site2md --help"
echo ""
