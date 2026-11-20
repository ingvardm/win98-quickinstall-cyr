#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build.sh -- build Cyrillic QuickInstall ISOs from ANY QuickInstall image.
#
#   ./build.sh <input.iso> [input2.iso ...]
#
# Each input produces <stem>_cyr.iso next to it. Nothing here is tied to a
# release version or filename: any single-variant QuickInstall ISO works, and
# no input hashes are checked.
# See README.md (in this directory) for the recipe and pipeline.
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$HERE/../../.." && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"          # repo root (canonical input location)
TOOL="$HERE/cyrillize.py"
PY="${PYTHON:-python3}"

usage() {
    cat <<EOF
Usage: $(basename "$0") <input.iso> [input2.iso ...]

Build a Cyrillic (cp1251 / cp866, English UI) version of each QuickInstall ISO.
Output: <stem>_cyr.iso, written next to the input
        (e.g. foo.iso -> foo_cyr.iso). Source ISOs are never modified.

Nothing is tied to a release version: any single-variant QuickInstall ISO
can be passed. Input paths are resolved relative to the current directory,
then to the REPO ROOT (where win98/ and the ISOs live), then to the
workspace root (legacy). Outputs are written next to each input.

Options (passed through to cyrillize.py):
  --rebuild=inplace     (default) preserve every other byte of the ISO
  --rebuild=makeiso     rebuild via upstream makeiso.py
  --usb=<file.img>      patch the upstream USB image instead of building ISOs;
                        produces <stem>_cyr.img for real-hardware USB boot
  -h, --help            show this help

Examples:
  ./build.sh win98qi_stock.iso
  ./build.sh win98qi_stock.iso win98qi_micro.iso
  ./build.sh /path/to/any-quickinstall.iso
  ./build.sh --usb=win98qi_v1.1.0_ALL_usb.img

For a custom output name call cyrillize.py directly:
  python3 "$TOOL" --iso <input.iso> --out <output.iso>
  python3 "$TOOL" --usb <input.img> --out <output.img>
EOF
}

ISOS=()
OPTS=()
USB=""
for arg in "$@"; do
    case "$arg" in
        -h|--help) usage; exit 0 ;;
        --usb=*) USB="${arg#*=}" ;;
        --rebuild=inplace|--rebuild=makeiso) OPTS+=(--rebuild "${arg#*=}") ;;
        -*) echo "Unknown option: $arg" >&2; usage >&2; exit 1 ;;
        *) ISOS+=("$arg") ;;
    esac
done

if [ -n "$USB" ]; then
    [ ${#ISOS[@]} -eq 0 ] || { echo "ERROR: --usb cannot be combined with ISO inputs" >&2; exit 1; }
    src="$USB"
    [ -f "$src" ] || src="$REPO/$USB"
    [ -f "$src" ] || src="$WORKSPACE/$USB"
    [ -f "$src" ] || { echo "ERROR: input USB image not found: $USB" >&2; exit 1; }
    out="${src%.*}_cyr.img"
    cd "$REPO"
    echo "Repo root: $REPO"
    echo "=== USB build: $(basename "$src") -> $(basename "$out") ==="
    "$PY" "$TOOL" --usb "$src" --out "$out"
    echo "=== USB verify ==="
    "$PY" "$TOOL" --verify --usb "$out"
    echo "All done. Generated: $out"
    echo "Write it to a USB stick with: dd if=$out of=/dev/sdX bs=4M status=progress"
    exit 0
fi

if [ ${#ISOS[@]} -eq 0 ]; then
    usage >&2
    exit 1
fi

# Resolve each input to an absolute path (CWD, then repo root, then workspace).
resolve_iso() {
    local a="$1"
    if [ -f "$a" ]; then
        echo "$(cd "$(dirname "$a")" && pwd)/$(basename "$a")"
    elif [ -f "$REPO/$a" ]; then
        echo "$REPO/$a"
    elif [ -f "$WORKSPACE/$a" ]; then
        echo "$WORKSPACE/$a"
    else
        echo "ERROR: input ISO not found: $a" >&2
        return 1
    fi
}

SRCS=()
for iso in "${ISOS[@]}"; do
    SRCS+=("$(resolve_iso "$iso")")
done

cd "$REPO"
echo "Repo root: $REPO"
echo

echo "=== Step 0: toolchain / registry-editor smoke test ==="
"$PY" "$TOOL" --smoke-test --iso "${SRCS[0]}" ${OPTS[@]+"${OPTS[@]}"}

OUTS=()
for src in "${SRCS[@]}"; do
    dir="$(dirname "$src")"
    base="$(basename "$src")"
    stem="${base%.*}"
    out="$dir/${stem}_cyr.iso"
    echo "=== Build: $base -> $(basename "$out") ==="
    "$PY" "$TOOL" --iso "$src" --out "$out" ${OPTS[@]+"${OPTS[@]}"}
    OUTS+=("$out")
done

for out in "${OUTS[@]}"; do
    echo "=== Verify: $(basename "$out") ==="
    "$PY" "$TOOL" --verify --iso "$out"
done

echo
echo "All done. Generated:"
printf '  %s\n' "${OUTS[@]}"
echo "Source ISOs were never modified; delete the *_cyr.iso files to roll back."
