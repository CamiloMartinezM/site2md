#!/bin/bash

# site2md Installation Script
# Supports Linux and macOS

set -e

echo "╔═══════════════════════════════════════════════════════╗"
echo "║             site2md - Installer                      ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Check Python version
echo "[1/4] Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed!"
    echo "   Please install Python 3.10 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✓ Found Python $PYTHON_VERSION"

# Check pip
echo ""
echo "[2/4] Checking pip..."
if ! command -v pip3 &> /dev/null; then
    echo "❌ Error: pip3 is not installed!"
    echo "   Installing pip..."
    python3 -m ensurepip --upgrade
fi
echo "✓ pip is ready"

# Install package
echo ""
echo "[3/4] Installing site2md..."
pip3 install --upgrade pip
pip3 install -e .

echo "✓ Installation complete!"

# Check wget (required for URL feature)
echo ""
echo "[4/4] Checking wget (required for URL mirroring)..."
if ! command -v wget &> /dev/null; then
    echo "⚠ Warning: wget is not installed!"
    echo "   URL downloading features will not work without it."
    echo "   To install wget:"
    echo "     • Ubuntu/Debian: sudo apt install wget"
    echo "     • macOS: brew install wget"
    echo "     • Fedora: sudo dnf install wget"
else
    WGET_VERSION=$(wget --version | head -n1 | awk '{print $3}')
    echo "✓ wget $WGET_VERSION is installed"
fi

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║              Installation Successful! 🎉              ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""
echo "Usage:"
echo "  • Local directory:    site2md build ./my_site --output manual.md"
echo "  • URL mirroring:      site2md build https://example.com --output manual.md"
echo "  • Help:               site2md --help"
echo ""
