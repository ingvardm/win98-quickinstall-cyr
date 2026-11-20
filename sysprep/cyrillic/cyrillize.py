#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# cyrillize.py -- bake Cyrillic (cp1251 / cp866) support into a Windows 98
#                 QuickInstall ISO at image build time (English UI preserved).
#
# Implements the design documented in README.md. One tool, one recipe.ini.
# Any single-variant QuickInstall ISO is accepted; the output is conventionally
# named <stem>_cyr.iso (see build.sh). No release version is hardcoded.
#
# Design notes
#  * MercyPak V1 (ZIEG) / V2 (MRCY) reader+writer lives here.  Entries are kept
#    as an ORDERED LIST (not a dict) and every entry retains its DOS
#    attr / dosDate / dosTime.  This preserves the 76 hidden/system attributes
#    and keeps the build deterministic.  It also preserves the two duplicate
#    paths (oeminfo.ini / oemlogo.bmp) present in the 98Lite FULL.866.
#  * Overlay is insert-or-replace: existing entries keep attr/date/time, missing
#    ones get the fixed [meta] values.  One branch, no per-image implementation.
#  * SYSTEM.DAT (in SLOWPNP.866 / FASTPNP.866) is patched by a pure-Python
#    Win9x CREG value editor -- no wine / msdos.exe / regedit.exe needed. The
#    three functional values are same-length in-place ASCII edits.
#  * The ISO is rebuilt with pycdlib in-place rm_file/add_fp: every byte of
#    every other file (incl. El Torito boot.cat / cdrom.img / [BOOT]) is kept.
#    --rebuild makeiso reproduces the upstream ISO build via makeiso.py.
#  * --verify re-parses an output ISO and asserts the checklist in README.md.
#
# No Microsoft binaries are written into the repository: donor payloads are
# streamed out of win98ru/BASE4.CAB into a scratch dir under /tmp/opencode.
# The whole pipeline is wine-free.
# ---------------------------------------------------------------------------

import argparse
import configparser
import hashlib
import io
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

import pycdlib

HERE = os.path.dirname(os.path.abspath(__file__))
SYSPREP = os.path.dirname(HERE)                 # .../sysprep
REPO = os.path.dirname(SYSPREP)                 # .../win98-quickinstall
WORKSPACE = os.path.dirname(REPO)               # .../win98-qi-cyrillic
RECIPE = os.path.join(HERE, 'recipe.ini')

DONOR_CAB = os.path.join('win98ru', 'BASE4.CAB')

MERCYPAK_V1 = b'ZIEG'
MERCYPAK_V2 = b'MRCY'
MAX_FILES_PER_KNOWN_DATA = 8   # mercypak.py; install.c asserts <= 16

# The four files we replace inside each ISO.  (iso_path, joliet_path, basename)
TARGETS = [
    ('/OSROOTS/1/FULL.866',      '/osroots/1/FULL.866',      'FULL.866'),
    ('/OSROOTS/1/SLOWPNP.866',   '/osroots/1/SLOWPNP.866',   'SLOWPNP.866'),
    ('/OSROOTS/1/FASTPNP.866',   '/osroots/1/FASTPNP.866',   'FASTPNP.866'),
    ('/OSROOTS/1/WIN98QI.INF',   '/osroots/1/win98qi.inf',   'win98qi.inf'),
]
FULL_NAME, SLOW_NAME, FAST_NAME, INF_NAME = [t[2] for t in TARGETS]

TOOLS = ['git', 'cabextract', '7z', 'python3', 'unzip']


# ---------------------------------------------------------------------------
# Recipe / small helpers
# ---------------------------------------------------------------------------

def load_recipe():
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    if not cp.read(RECIPE):
        raise SystemExit(f'Cannot read recipe: {RECIPE}')
    return cp


def recipe_lines(cp, section, option):
    """Return a multi-line recipe value as a list of stripped, non-empty lines."""
    raw = cp.get(section, option)
    return [ln.strip() for ln in raw.strip().split('\n') if ln.strip()]


def parse_maps(cp, section):
    """Parse a 'DEST = source | size' section into an ordered list."""
    out = []
    for dest in cp.options(section):
        val = cp.get(section, dest)
        parts = [p.strip() for p in val.split('|')]
        if len(parts) != 2:
            raise ValueError(f'{section}: bad value for {dest}: {val!r}')
        out.append((dest, parts[0], int(parts[1])))
    return out


def norm(path):
    return path.replace('\\', '/').lower()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def resolve(path):
    """Resolve --iso/--out relative to CWD, then to WORKSPACE."""
    if os.path.isabs(path):
        return path
    if os.path.exists(path):
        return os.path.abspath(path)
    alt = os.path.join(WORKSPACE, path)
    if os.path.exists(alt):
        return alt
    return os.path.abspath(path)   # for --out: write relative to CWD


def die(msg):
    raise SystemExit('ERROR: ' + msg)


def check(cond, msg):
    if not cond:
        die(msg)
    print('  ok: ' + msg)


# ---------------------------------------------------------------------------
# Windows 9x (CREG) registry value editor -- pure Python, no wine/regedit
#
# SYSTEM.DAT / USER.DAT start with 'CREG' and store REG_SZ values as compact
# records:  [u16 name_len][u16 data_len][name bytes][data bytes]
# (a default value has an empty name), followed by an 8-byte type/next header.
# The Cyrillic recipe changes exactly three of these records, and every change
# is a SAME-LENGTH ASCII replacement (1252->1251, 437->866, 00000409->00000419).
# Editing those bytes in place is therefore safe: no key node, pointer, hash,
# value-count or free-space chain is touched.  This is also byte-for-byte what
# regedit does for those fields (verified by diffing its output); regedit's
# extra work is only for *adding* the optional "SystemLocale" value, which
# requires growing the hive and is deliberately omitted here (it is not used
# by Win9x -- the system locale is the Locale key's default value).
# ---------------------------------------------------------------------------

def creg_record(name, value):
    """Exact byte pattern of a Win9x REG_SZ value record."""
    return struct.pack('<HH', len(name), len(value)) + name + value


def creg_find(data, name, value):
    """Offsets of every record with this name and exact data."""
    pat = creg_record(name, value)
    offs = []
    i = data.find(pat)
    while i >= 0:
        offs.append(i)
        i = data.find(pat, i + 1)
    return offs


def creg_data_offset(off, name):
    return off + 4 + len(name)


def parse_creg_edits(cp):
    """[creg] section: name | current | desired  (name '@' = default value)."""
    out = []
    for key in cp.options('creg'):
        parts = [p.strip() for p in cp.get('creg', key).split('|')]
        if len(parts) != 2:
            raise ValueError(f'creg: bad value for {key}: {cp.get("creg", key)!r}')
        old, new = parts
        name = b'' if key == '@' else key.encode('cp1252')
        out.append((key, name, old.encode('cp1252'), new.encode('cp1252')))
    return out


def creg_patch(data, edits):
    """Apply same-length in-place REG_SZ edits. Returns (new_bytes, report).

    For the unnamed ('@') default value the record appears more than once in a
    hive; the Nls\\Locale default is the occurrence immediately preceding the
    Codepage key's ACP value (the Locale key's values precede Codepage's)."""
    out = bytearray(data)
    report = []
    # Anchor: locate the ACP record first (it is unique in both images).
    acp_name, acp_old = b'ACP', b'1252'
    acp_offs = creg_find(out, acp_name, acp_old)
    check(len(acp_offs) == 1, 'SYSTEM.DAT: unique ACP record found')
    acp_off = acp_offs[0]

    for key, name, old, new in edits:
        check(len(old) == len(new), f'creg {key}: same-length edit')
        offs = creg_find(out, name, old)
        check(bool(offs), f'creg {key}: current record present')
        if key == '@':
            before = [o for o in offs if o < acp_off]
            check(bool(before), f'creg {key}: find occurrence before Codepage key')
            off = max(before)
            check(acp_off - off < 0x2000,
                  f'creg {key}: occurrence belongs to the Nls\\Locale key')
        else:
            check(len(offs) == 1, f'creg {key}: record is unique')
            off = offs[0]
        d = creg_data_offset(off, name)
        out[d:d + len(new)] = new
        report.append((key, old.decode('ascii'), new.decode('ascii'), off))
        print(f'  creg: {key} {old.decode()} -> {new.decode()} @ {off:#x}')
    return bytes(out), report


def creg_verify(data, edits):
    """Assert the desired values. For the unnamed ('@') default value, other
    keys legitimately still hold the old value, so scope the check to the
    occurrence immediately preceding the ACP record (the Nls\\Locale key)."""
    for key, name, old, new in edits:
        if key == '@':
            acp = creg_find(data, b'ACP', b'1251')
            check(bool(acp), 'SYSTEM.DAT: ACP anchor present')
            candidates = [o for o in creg_find(data, name, old) +
                          creg_find(data, name, new) if o < acp[0]]
            check(bool(candidates), f'SYSTEM.DAT: {key} record before ACP')
            off = max(candidates)
            d = creg_data_offset(off, name)
            check(data[d:d + len(new)] == new,
                  f'SYSTEM.DAT: {key} = {new.decode()}')
        else:
            check(bool(creg_find(data, name, new)),
                  f'SYSTEM.DAT: {key} = {new.decode()}')
            check(not creg_find(data, name, old),
                  f'SYSTEM.DAT: old {key} value gone')


# ---------------------------------------------------------------------------
# MercyPak V1 / V2 reader + writer
# ---------------------------------------------------------------------------

class MercyPak:
    def __init__(self, magic, dirs, files):
        self.magic = magic
        self.dirs = dirs      # list of (attr:int, name:str)  -- name uses '\'
        self.files = files    # list of dict: path, attr, date, time, data

    @property
    def version(self):
        return 2 if self.magic == MERCYPAK_V2 else 1


def read_mercypak(data):
    magic = data[:4]
    if magic not in (MERCYPAK_V1, MERCYPAK_V2):
        raise ValueError(f'Not a MercyPak file: {magic!r}')
    v2 = (magic == MERCYPAK_V2)
    dir_count, file_count = struct.unpack_from('<II', data, 4)
    pos = 12
    dirs = []
    for _ in range(dir_count):
        attr = data[pos]; pos += 1
        ln = data[pos]; pos += 1
        name = data[pos:pos + ln].decode('cp1252'); pos += ln
        dirs.append((attr, name))

    files = []
    if v2:
        total = 0
        while total < file_count:
            cnt = data[pos]; pos += 1
            infos = []
            for _ in range(cnt):
                ln = data[pos]; pos += 1
                name = data[pos:pos + ln].decode('cp1252'); pos += ln
                attr = data[pos]; pos += 1
                date, time = struct.unpack_from('<HH', data, pos); pos += 4
                infos.append((name, attr, date, time))
            size, = struct.unpack_from('<I', data, pos); pos += 4
            blob = data[pos:pos + size]; pos += size
            for name, attr, date, time in infos:
                files.append({'path': name, 'attr': attr, 'date': date,
                              'time': time, 'data': blob})
            total += cnt
        if total != file_count:
            raise ValueError(f'V2 fileCount mismatch: {total} != {file_count}')
    else:
        for _ in range(file_count):
            ln = data[pos]; pos += 1
            name = data[pos:pos + ln].decode('cp1252'); pos += ln
            attr = data[pos]; pos += 1
            date, time = struct.unpack_from('<HH', data, pos); pos += 4
            size, = struct.unpack_from('<I', data, pos); pos += 4
            blob = data[pos:pos + size]; pos += size
            files.append({'path': name, 'attr': attr, 'date': date,
                          'time': time, 'data': blob})

    if pos != len(data):
        raise ValueError(f'Trailing bytes after MercyPak stream: {pos} != {len(data)}')
    return MercyPak(magic, dirs, files)


def _pack_name(name):
    b = name.encode('cp1252')
    if len(b) > 0xff:
        raise ValueError(f'MercyPak path too long: {name!r}')
    return struct.pack('B', len(b)) + b


def write_mercypak(mp):
    out = bytearray()
    out += mp.magic
    out += struct.pack('<II', len(mp.dirs), len(mp.files))
    for attr, name in mp.dirs:
        out += struct.pack('B', attr & 0xff)
        out += _pack_name(name)

    if mp.version == 1:
        for f in mp.files:
            out += _pack_name(f['path'])
            out += struct.pack('B', f['attr'] & 0xff)
            out += struct.pack('<HH', f['date'], f['time'])
            out += struct.pack('<I', len(f['data']))
            out += f['data']
    else:
        # Re-generate dedup groups by hashing, capped at MAX_FILES_PER_KNOWN_DATA,
        # mirroring upstream mercypak.py:add_to_known_files().
        groups = []                 # list of [data, [entries]]
        by_hash = {}                # digest -> list of groups
        for f in mp.files:
            h = hashlib.sha256(f['data']).digest()
            placed = False
            for g in by_hash.get(h, ()):
                if len(g[1]) < MAX_FILES_PER_KNOWN_DATA:
                    g[1].append(f)
                    placed = True
                    break
            if not placed:
                g = [f['data'], [f]]
                groups.append(g)
                by_hash.setdefault(h, []).append(g)
        for data, members in groups:
            out += struct.pack('B', len(members))
            for f in members:
                out += _pack_name(f['path'])
                out += struct.pack('B', f['attr'] & 0xff)
                out += struct.pack('<HH', f['date'], f['time'])
            out += struct.pack('<I', len(data))
            out += data
    return bytes(out)


def index_files(mp):
    idx = {}
    for f in mp.files:
        idx.setdefault(norm(f['path']), []).append(f)
    return idx


# ---------------------------------------------------------------------------
# Toolchain / pinned hashes   (no wine / regedit / DOS emulator needed)
# ---------------------------------------------------------------------------

def check_tools():
    for t in TOOLS:
        if shutil.which(t) is None:
            die(f'Missing required tool on PATH: {t}')
    print('  ok: toolchain present (' + ', '.join(TOOLS) + ')')


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def check_pinned_hashes(cp, iso_path, keys, strict=False):
    """Verify pinned digests for `keys` -- the inputs this run actually consumes.

    By default only those entries are checked; every other pinned file is
    ignored, so an unused donor / other input ISO neither has to exist nor can
    block the build with a stale hash. A checked file that is missing or
    mismatched is still a hard error (reproducibility for what we do read).
    `--strict-hashes` restores the original behaviour: check the whole table.
    """
    print('Checking pinned hashes:')
    if strict:
        targets = list(cp.items('hashes'))
    else:
        targets = [(k, cp.get('hashes', k)) for k in keys
                   if cp.has_option('hashes', k)]
    for name, expected in targets:
        path = iso_path if os.path.basename(iso_path) == name else os.path.join(WORKSPACE, name)
        check(os.path.isfile(path), f'{name} present')
        got = sha256_file(path)
        check(got == expected, f'{name} sha256 matches')
    for k in keys:
        if not cp.has_option('hashes', k):
            print(f'  note: {k} is not a pinned input; hash not checked')


# ---------------------------------------------------------------------------
# Donor extraction from win98ru/BASE4.CAB
# ---------------------------------------------------------------------------

def extract_donors(cp, workdir):
    cab = os.path.join(WORKSPACE, DONOR_CAB)
    print('Extracting donor payloads from ' + DONOR_CAB)
    donors = {}
    all_items = parse_maps(cp, 'fonts') + parse_maps(cp, 'adds')
    for _dest, src, size in all_items:
        if src in donors:
            continue
        raw = subprocess.run(['cabextract', '-p', '-F', src, cab],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             check=True).stdout
        check(len(raw) == size, f'donor {src} size {size}')
        donors[src] = raw
    return donors


# ---------------------------------------------------------------------------
# ISO reading (pycdlib)
# ---------------------------------------------------------------------------

def open_iso(path):
    iso = pycdlib.PyCdlib()
    iso.open(path)
    return iso


def read_iso_file(iso, joliet_path, workdir, tag):
    tmp = os.path.join(workdir, '_read_' + tag)
    iso.get_file_from_iso(tmp, joliet_path=joliet_path)
    with open(tmp, 'rb') as fh:
        data = fh.read()
    os.remove(tmp)
    return data


def read_all_targets(iso, workdir):
    out = {}
    for iso_path, joliet_path, base in TARGETS:
        out[base] = read_iso_file(iso, joliet_path, workdir, base)
    return out


# ---------------------------------------------------------------------------
# WIN.INI / SYSTEM.INI / label patching
# ---------------------------------------------------------------------------

def patch_win_ini(data, cyrsubs_lines):
    lines = data.split(b'\r\n')
    hdr = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() == b'[fontsubstitutes]':
            hdr = i
            break
    if hdr is None:
        raise ValueError('WIN.INI has no [FontSubstitutes] section')
    # Insert point: first blank line (or next [section]) after the header.
    ins = len(lines)
    for j in range(hdr + 1, len(lines)):
        if lines[j] == b'' or lines[j].startswith(b'['):
            ins = j
            break
    existing = set()
    for j in range(hdr + 1, ins):
        existing.add(lines[j].strip())
    additions = []
    for text in cyrsubs_lines:
        b = text.encode('cp1252')
        if b.strip() in existing or b in additions:
            continue
        additions.append(b)
    lines[ins:ins] = additions
    return b'\r\n'.join(lines)


def patch_system_ini(data, oemansi_line):
    new_val = oemansi_line.encode('cp1252')
    pat = re.compile(rb'(oemansi\.bin=)[^\r\n]*', re.IGNORECASE)
    if not pat.search(data):
        raise ValueError('SYSTEM.INI has no oemansi.bin= line')
    return pat.sub(lambda m: m.group(1) + new_val.split(b'=', 1)[1], data, count=1)


def patch_label(data, suffix):
    return data.rstrip(b'\r\n') + b' ' + suffix.encode('cp1252') + b'\n'


# ---------------------------------------------------------------------------
# Overlay into FULL.866
# ---------------------------------------------------------------------------

def overlay_full(mp, cp, donors):
    idx = index_files(mp)
    new_attr = cp.getint('meta', 'new_file_attr')
    new_date = cp.getint('meta', 'new_file_date')
    new_time = cp.getint('meta', 'new_file_time')

    for dest, src, size in parse_maps(cp, 'fonts') + parse_maps(cp, 'adds'):
        data = donors[src]
        key = norm(dest)
        if key in idx:                       # replace, keep attr/date/time
            for f in idx[key]:
                f['data'] = data
        else:                                # insert
            stored = dest.replace('/', '\\')
            entry = {'path': stored, 'attr': new_attr, 'date': new_date,
                     'time': new_time, 'data': data}
            mp.files.append(entry)
            idx[key] = [entry]

    cyrsubs = recipe_lines(cp, 'win_ini', 'cyrsubs')
    oemansi = cp.get('system_ini', 'oemansi').strip()
    idx['windows/win.ini'][0]['data'] = patch_win_ini(
        idx['windows/win.ini'][0]['data'], cyrsubs)
    idx['windows/system.ini'][0]['data'] = patch_system_ini(
        idx['windows/system.ini'][0]['data'], oemansi)
    return mp


# ---------------------------------------------------------------------------
# Win9x SYSTEM.DAT patching -- pure Python (see the CREG section above)
# ---------------------------------------------------------------------------

def patch_registry_payload(mp, edits, tag):
    check(mp.version == 1, f'{tag}: still MercyPak V1')
    check(len(mp.files) == 1, f'{tag}: exactly one entry')
    f = mp.files[0]
    check(norm(f['path']) == 'windows/system.dat',
          f'{tag}: single entry is WINDOWS/SYSTEM.DAT')
    before = f['data']
    f['data'], _report = creg_patch(before, edits)
    check(f['data'] != before, f'{tag}: SYSTEM.DAT patched in place')
    return mp


# ---------------------------------------------------------------------------
# ISO rebuild
# ---------------------------------------------------------------------------

def rebuild_inplace(iso, patched, out_path):
    """pycdlib rm_file/add_fp: replaces exactly the 4 target files, every other
    byte (El Torito, boot.cat, cdrom.img, [BOOT], all other files) is preserved."""
    keep = []   # keep BytesIO objects alive until write()
    for iso_path, joliet_path, base in TARGETS:
        iso.rm_file(iso_path=iso_path)
    for iso_path, joliet_path, base in TARGETS:
        data = patched[base]
        fp = io.BytesIO(data)
        keep.append(fp)
        iso.add_fp(fp, len(data), iso_path=iso_path, joliet_path=joliet_path)
    if os.path.exists(out_path):
        os.remove(out_path)
    iso.write(out_path)
    return keep


def rebuild_makeiso(iso_path, out_path, patched, workdir):
    """Upstream ISO build: full '7z x' extraction + makeiso.makeIso()."""
    tree = os.path.join(workdir, 'tree')
    os.makedirs(tree, exist_ok=True)
    subprocess.run(['7z', 'x', '-y', '-o' + tree, iso_path], check=True,
                   stdout=subprocess.DEVNULL)
    for _iso, _jol, base in TARGETS:
        with open(os.path.join(tree, 'osroots', '1', base), 'wb') as fh:
            fh.write(patched[base])
    # Avoid a duplicate BOOT.CAT: add_eltorito() creates the catalog itself.
    bc = os.path.join(tree, 'boot.cat')
    if os.path.exists(bc):
        os.remove(bc)
    sys.path.insert(0, SYSPREP)
    import makeiso
    makeiso.makeIso(tree, out_path, 'cdrom.img', 'QuickInstall')


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def make_workdir(out_path):
    base = '/tmp/opencode' if os.path.isdir('/tmp/opencode') else tempfile.gettempdir()
    stem = os.path.splitext(os.path.basename(out_path))[0]
    d = os.path.join(base, 'cyrillize-' + stem)
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)
    return d


def smoke_test(cp, iso_path, workdir, strict_hashes=False):
    """Step 0, wine-free: validate the toolchain and prove the pure-Python CREG
    editor can patch a real Win9x SYSTEM.DAT."""
    print('Smoke-testing the toolchain and pure-Python registry editor:')
    check_tools()
    check_pinned_hashes(cp, iso_path, [os.path.basename(iso_path)],
                        strict=strict_hashes)
    edits = parse_creg_edits(cp)
    iso = open_iso(iso_path)
    slow = read_mercypak(read_iso_file(iso, '/osroots/1/SLOWPNP.866', workdir, 'slow'))
    iso.close()
    sysdat = slow.files[0]['data']
    patched, _ = creg_patch(sysdat, edits)
    check(patched != sysdat, 'CREG editor modified a scratch SYSTEM.DAT')
    creg_verify(patched, edits)
    print('Smoke test PASSED -- toolchain and registry editor are usable.\n')


def build(cp, args):
    iso_path = resolve(args.iso)
    out_path = resolve(args.out)
    check(os.path.isfile(iso_path), f'input ISO exists: {iso_path}')
    check(iso_path != out_path, 'input and output paths differ')
    check_tools()
    # Only the input ISO and the donor CAB are actually consumed by a build.
    check_pinned_hashes(cp, iso_path,
                        [os.path.basename(iso_path), DONOR_CAB],
                        strict=args.strict_hashes)

    workdir = make_workdir(out_path)
    try:
        donors = extract_donors(cp, workdir)
        edits = parse_creg_edits(cp)

        iso = open_iso(iso_path)
        raw = read_all_targets(iso, workdir)

        # Parse payloads.
        full = read_mercypak(raw[FULL_NAME])
        slow = read_mercypak(raw[SLOW_NAME])
        fast = read_mercypak(raw[FAST_NAME])
        check(full.version == 2, 'FULL.866 is MercyPak V2 (MRCY)')
        check(len(full.files) == struct.unpack_from('<I', raw[FULL_NAME], 8)[0],
              'FULL.866 fileCount matches parsed entries')

        # Overlay FULL.866 and patch WIN.INI / SYSTEM.INI (insert-or-replace).
        overlay_full(full, cp, donors)
        patched = {
            FULL_NAME: write_mercypak(full),
        }

        # Patch both registry payloads separately (pure Python, no wine).
        patch_registry_payload(slow, edits, 'slowpnp')
        patch_registry_payload(fast, edits, 'fastpnp')
        patched[SLOW_NAME] = write_mercypak(slow)
        patched[FAST_NAME] = write_mercypak(fast)

        # Label.
        patched[INF_NAME] = patch_label(raw[INF_NAME],
                                        cp.get('meta', 'label_suffix').strip())

        # Rebuild.
        print(f'Rebuilding ISO ({args.rebuild}) -> {out_path}')
        if args.rebuild == 'makeiso':
            rebuild_makeiso(iso_path, out_path, patched, workdir)
        else:
            rebuild_inplace(iso, patched, out_path)
        iso.close()
        print(f'Wrote {out_path} ({os.path.getsize(out_path)} bytes)\n')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Verify (see README.md checklist)
# ---------------------------------------------------------------------------

def derive_input_iso(out_path):
    """stock_cyr.iso -> stock.iso ; look for it next to the output / WORKSPACE."""
    base = os.path.basename(out_path)
    cand = base.replace('_cyr.iso', '.iso')
    if cand == base:
        return None
    for p in (os.path.join(os.path.dirname(out_path), cand),
              os.path.join(WORKSPACE, cand)):
        if os.path.isfile(p):
            return p
    return None


def verify(cp, args):
    out_path = resolve(args.iso)
    check(os.path.isfile(out_path), f'output ISO exists: {out_path}')
    workdir = make_workdir(out_path + '.verify')
    try:
        # --- ISO level checks ---
        print('ISO / boot structure:')
        fileout = subprocess.check_output(['file', out_path]).decode(errors='replace')
        check('ISO 9660' in fileout, "'file' reports ISO 9660")
        check('bootable' in fileout.lower(), "'file' reports bootable")
        listing = subprocess.check_output(['7z', 'l', out_path]).decode(errors='replace')
        check('boot.cat' in listing, 'boot.cat present')
        check('cdrom.img' in listing, 'cdrom.img present')
        check('Boot-2.88M.img' in listing, '[BOOT]/Boot-2.88M.img present (El Torito)')
        iso = open_iso(out_path)
        check(iso.eltorito_boot_catalog is not None, 'pycdlib sees El Torito boot catalog')

        raw = read_all_targets(iso, workdir)
        iso.close()

        # --- FULL.866 ---
        print('FULL.866 payload:')
        full = read_mercypak(raw[FULL_NAME])
        check(full.magic == MERCYPAK_V2, 'FULL.866 magic is MRCY')
        fc = struct.unpack_from('<I', raw[FULL_NAME], 8)[0]
        check(len(full.files) == fc, 'FULL.866 fileCount equals parsed entries')
        idx = index_files(full)

        fonts = parse_maps(cp, 'fonts')
        adds = parse_maps(cp, 'adds')
        marker_w = cp.get('meta', 'win_ini_marker').encode('cp1252')
        marker_s = cp.get('meta', 'system_ini_marker').encode('cp1252')

        # 15 Cyrillic fonts have the recipe sizes; symbols unchanged (vs input).
        for dest, src, size in fonts:
            ents = idx.get(norm(dest), [])
            check(bool(ents) and all(len(e['data']) == size for e in ents),
                  f'font present with size {size}: {os.path.basename(dest)}')

        # The 4/5 added files present with expected sizes.
        for dest, src, size in adds:
            ents = idx.get(norm(dest), [])
            check(bool(ents) and all(len(e['data']) == size for e in ents),
                  f'added file {os.path.basename(dest)} size {size}')

        # UNICODE.BIN unchanged.
        ub = idx.get('windows/system/unicode.bin')
        check(bool(ub) and sha256(ub[0]['data']) == cp.get('meta', 'unicode_bin_sha256'),
              'UNICODE.BIN sha256 still fa7d22bb...')

        # INI markers.
        check(marker_w in idx['windows/win.ini'][0]['data'],
              'WIN.INI contains "MS Sans Serif,0=MS Sans Serif,204"')
        check(marker_s in idx['windows/system.ini'][0]['data'],
              'SYSTEM.INI contains "oemansi.bin=xlat866.bin"')

        # Attribute regression check. The 15 replaced font destinations must
        # keep their hidden/system bit (0x02); that is the loss the dedicated
        # reader/writer prevents. 98Lite additionally ships 7 WST_*.FON at
        # 0x20 -- those are legitimate and are verified unchanged (attr/date/
        # time) by the input-vs-output diff below. MSDOS.SYS stays 0x07.
        msdos = idx.get('msdos.sys')
        check(bool(msdos) and msdos[0]['attr'] == 0x07, 'MSDOS.SYS DOS attr still 0x07')
        font_dests = {norm(d) for d, _s, _z in fonts}
        replaced_attrs = [e['attr'] for k in font_dests for e in idx.get(k, [])]
        check(len(replaced_attrs) >= 15 and all(a == 0x02 for a in replaced_attrs),
              'all 15 Cyrillic font destinations still DOS attr 0x02')

        # USER.DAT: HKCU Locale still 00000409 (untouched).
        print('USER.DAT / English UI:')
        ud = idx.get('windows/user.dat')
        check(bool(ud) and b'\x06\x00\x08\x00Locale00000409' in ud[0]['data'],
              'HKCU Control Panel\\International Locale still 00000409')

        # --- registry payloads (pure-Python CREG value check) ---
        print('SLOWPNP.866 / FASTPNP.866 registries:')
        edits = parse_creg_edits(cp)
        for name in (SLOW_NAME, FAST_NAME):
            mp = read_mercypak(raw[name])
            check(mp.magic == MERCYPAK_V1, f'{name} is MercyPak V1 (ZIEG)')
            check(len(mp.files) == 1 and norm(mp.files[0]['path']) == 'windows/system.dat',
                  f'{name}: one WINDOWS/SYSTEM.DAT entry')
            creg_verify(mp.files[0]['data'], edits)

        # --- file-list / data diff against the input ISO (if available) ---
        inp = derive_input_iso(out_path)
        if inp and os.path.isfile(inp):
            print('Diff against input ISO (only intended entries may change):')
            iiso = open_iso(inp)
            iraw = read_iso_file(iiso, '/osroots/1/FULL.866', workdir, 'in_full')
            in_reg = {name: read_mercypak(
                read_iso_file(iiso, '/osroots/1/' + name, workdir, 'in_' + name))
                for name in (SLOW_NAME, FAST_NAME)}
            iiso.close()
            ifull = read_mercypak(iraw)
            iidx = index_files(ifull)
            changed = {norm(d) for d, _s, _z in fonts}
            changed |= {'windows/win.ini', 'windows/system.ini'}
            added_expected = {norm(d) for d, _s, _z in adds if norm(d) not in iidx}

            out_paths = set(idx.keys())
            in_paths = set(iidx.keys())
            check(in_paths - out_paths == set(), 'no files removed from FULL.866')
            check(out_paths - in_paths == added_expected,
                  'diff of file lists shows only the intended added entries')

            # Every unchanged file keeps identical data + DOS metadata.
            problems = []
            for key in sorted(in_paths & out_paths):
                a = iidx[key][0]
                b = idx[key][0]
                if (a['attr'], a['date'], a['time']) != (b['attr'], b['date'], b['time']):
                    problems.append(key + ' (metadata)')
                if key not in changed and a['data'] != b['data']:
                    problems.append(key + ' (data)')
            check(not problems, 'all unchanged entries keep data + attr/date/time'
                  + ('' if not problems else ' -> ' + ', '.join(problems[:5])))

            # Changed entries match the donor exactly.
            donors = extract_donors(cp, workdir)
            for dest, src, size in fonts + adds:
                for e in idx.get(norm(dest), []):
                    check(e['data'] == donors[src], f'{os.path.basename(dest)} == donor {src}')
            check(b'\x06\x00\x08\x00Locale00000409' in
                  iidx['windows/user.dat'][0]['data'],
                  'USER.DAT byte-identical to input (HKCU Locale preserved)')
            # symbol fonts unchanged
            for sym in ('windows/fonts/symbole.fon', 'windows/fonts/symbolf.fon'):
                check(iidx[sym][0]['data'] == idx[sym][0]['data'],
                      f'{sym} unchanged (hash matches input)')

            # Registry payloads are the deterministic pure-Python transformation
            # of the input SYSTEM.DAT (i.e. only the 5 intended bytes changed).
            for name in (SLOW_NAME, FAST_NAME):
                imp = in_reg[name]
                expected, _ = creg_patch(imp.files[0]['data'], edits)
                actual = read_mercypak(raw[name]).files[0]['data']
                check(actual == expected,
                      f'{name}: SYSTEM.DAT == pure-Python CREG patch of input')
        else:
            print('  note: input ISO not found next to output; skipped full data diff.')

        print('\nVERIFY PASSED for ' + out_path)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description='Bake Cyrillic support into any single-variant Win98 '
                    'QuickInstall ISO (version-independent).',
        epilog='Example: build.sh <input.iso>  ->  <stem>_cyr.iso. '
               'See README.md for the recipe and pipeline.')
    ap.add_argument('--iso', help='input ISO (build) or output ISO (--verify)')
    ap.add_argument('--out', help='output ISO path (build)')
    ap.add_argument('--verify', action='store_true', help='validate an output ISO')
    ap.add_argument('--smoke-test', action='store_true',
                    help='only run the toolchain/registry-editor smoke test and exit')
    ap.add_argument('--rebuild', choices=['inplace', 'makeiso'], default='inplace',
                    help='ISO rebuild method (default: inplace, preserves all bytes)')
    ap.add_argument('--strict-hashes', action='store_true',
                    help='verify ALL pinned hashes (default: only inputs this run '
                         'consumes; unused donor/other ISOs are ignored)')
    args = ap.parse_args()

    cp = load_recipe()

    if args.smoke_test:
        if not args.iso:
            die('--smoke-test needs --iso')
        iso_path = resolve(args.iso)
        check(os.path.isfile(iso_path), f'input ISO exists: {iso_path}')
        d = make_workdir('smoke')
        try:
            smoke_test(cp, iso_path, d, strict_hashes=args.strict_hashes)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        return

    if args.verify:
        if not args.iso:
            die('--verify needs --iso')
        verify(cp, args)
        return

    if not args.iso or not args.out:
        die('build mode needs --iso and --out')
    build(cp, args)


if __name__ == '__main__':
    main()
