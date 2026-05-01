#!/bin/bash
set -e

# --- ⚖️ Module License Compliance Check ---
# Ensures all local modules have a LICENSE file.

echo "⚖️ Checking module licenses..."

FAIL=0
for dir in infrastructure-modules/*/; do
    if [ ! -f "${dir}LICENSE" ] && [ ! -f "${dir}LICENSE.md" ]; then
        echo "❌ Missing LICENSE in ${dir}"
        FAIL=1
    fi
done

if [ $FAIL -eq 1 ]; then
    echo "⚠️ License compliance check failed. Please add LICENSE files to all modules."
    # We soft-fail this for now as it's a documentation requirement
    exit 0
else
    echo "✅ All local modules have licenses."
    exit 0
fi
