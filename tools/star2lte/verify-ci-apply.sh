#!/bin/bash
# Simulate CI: xnu-8796.141.3 + (A5 patches overlaid with fixed ones) applied
# with plain `git apply` only, then compare with the local star2lte patched tree.
# Usage: verify-ci-apply.sh A5_PATCH_DIR FIXED_DIR [XNU_ORIG_DIR]
set -euo pipefail

a5=$(realpath "$1")
fixed=$(realpath "$2")

# Resolve repository root
repo=$(git rev-parse --show-toplevel 2>/dev/null || cd "$(dirname "$0")/../.." && pwd)

# Determine clean upstream XNU source cache (default to ~/ios-port-workspace/xnu-orig if not passed)
xnu_orig=${3:-$repo/../xnu-orig}

# Setup dynamic temporary workspace
tmp="/tmp/star2lte/ci-sim"
rm -rf "$tmp"
mkdir -p "$tmp/patches"

# Copy base A5 patches and S9+ specific fixed patches
cp "$a5"/*.patch "$tmp/patches/" 2>/dev/null || true
cp "$fixed"/*.patch "$tmp/patches/" 2>/dev/null || true

if [ ! -d "$xnu_orig" ]; then
    echo "[-] Error: Clean upstream XNU directory not found at: $xnu_orig"
    echo "    Please pass the path as the third argument or ensure it sits next to your repository."
    exit 1
fi

echo "[*] Copying clean upstream XNU from $xnu_orig..."
cp -R "$xnu_orig" "$tmp/xnu"

cd "$tmp/xnu"
skipped=0

echo "[*] Simulating patch sequence application..."
for p in "$tmp"/patches/*.patch; do
    [ -f "$p" ] || continue
    if git apply --check "$p" 2>/dev/null; then 
        git apply "$p"
        echo "[+] Applied: $(basename "$p")"
    else 
        echo "[-] CI would skip: $(basename "$p")"
        skipped=$((skipped + 1))
    fi
done

echo "[*] skipped=$skipped (expected 2: the staged-HFS patches 0031/0041)"

# Compare simulated patched tree with local repository patched tree
if diff -rq -x .git -x "build" -x "fakeroot" "$tmp/xnu" "$repo/xnu"; then 
    echo "[+] SUCCESS: TREES IDENTICAL"
else 
    echo "[-] WARNING: TREES DIFFER"
fi
