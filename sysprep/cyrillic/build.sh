#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build.sh -- build Cyrillic QuickInstall ISOs from ANY QuickInstall image.
#
#   ./build.sh <input.iso> [input2.iso ...]
#
# Each input produces <stem>_cyr.iso next to it. Nothing here is tied to a
# release version, filename or hash: any single-variant QuickInstall ISO works.
# See README.md (in this directory) for the recipe and pipeline.
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$HERE/../../.." && pwd)"
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
then to the workspace root.

Options (passed through to cyrillize.py):
  --strict-hashes       verify ALL pinned hashes (default: only the donor CAB
                        plus --iso if its name is a known release)
  --rebuild=inplace     (default) preserve every other byte of the ISO
  --rebuild=makeiso     rebuild via upstream makeiso.py
  -h, --help            show this help

Examples:
  ./build.sh win98qi_v1.1.0_stock.iso
  ./build.sh win98qi_v1.1.0_stock.iso win98qi_v1.1.0_micro_directx81.iso
  ./build.sh /path/to/any-quickinstall.iso

For a custom output name call cyrillize.py directly:
  python3 "$TOOL" --iso <input.iso> --out <output.iso>
EOF
}

ISOS=()
OPTS=()
for arg in "$@"; do
    case "$arg" in
        -h|--help) usage; exit 0 ;;
        --strict-hashes) OPTS+=(--strict-hashes) ;;
        --rebuild=inplace|--rebuild=makeiso) OPTS+=(--rebuild "${arg#*=}") ;;
        -*) echo "Unknown option: $arg" >&2; usage >&2; exit 1 ;;
        *) ISOS+=("$arg") ;;
    esac
done

if [ ${#ISOS[@]} -eq 0 ]; then
    usage >&2
    exit 1
fi

# Resolve each input to an absolute path (relative to CWD, then workspace).
resolve_iso() {
    local a="$1"
    if [ -f "$a" ]; then
        echo "$(cd "$(dirname "$a")" && pwd)/$(basename "$a")"
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

cd "$WORKSPACE"
echo "Workspace: $WORKSPACE"
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
