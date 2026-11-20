# Cyrillic QuickInstall fork — how it works

## Get started

Minimal layout — put everything in one directory:

```
my-build/
├── win98-quickinstall/          # the fork (git repo)
│   └── sysprep/cyrillic/        #   this tool: build.sh, cyrillize.py, recipe.ini
├── win98ru/
│   └── BASE4.CAB                # the only donor file you need
└── any-quickinstall.iso         # any single-variant QuickInstall ISO
```

```bash
git clone <your-fork-url> win98-quickinstall   # fork containing sysprep/cyrillic/
pip3 install pycdlib
./win98-quickinstall/sysprep/cyrillic/build.sh any-quickinstall.iso
# -> any-quickinstall_cyr.iso, written next to the input
```

That's it: the fork, `win98ru/BASE4.CAB`, and the ISO to convert. No other ISOs,
no wine, no submodules, no previous outputs. The input's name/version does not
matter. Requires `git`, `python3`, `cabextract`, `7z`, `file`, `unzip` and Python
`pycdlib`. Everything below explains the recipe and pipeline.

Bake Cyrillic support (cp1251 ANSI / cp866 OEM) into **any single-variant**
Windows 98 SE QuickInstall ISO at **image build time**, keeping the English UI.
The fonts, NLS files, INI edits and codepage/locale registry values come
verbatim from Microsoft's own Russian Windows 98 SE `[CP866]` / `[CopyDat866]`
recipe. Nothing in the shell / Explorer resources is changed.

`build.sh` takes the source ISO(s) as arguments and derives the output name:

```bash
./build.sh win98qi_v1.1.0_stock.iso                 # -> win98qi_v1.1.0_stock_cyr.iso
./build.sh /path/to/any-quickinstall.iso            # -> any-quickinstall_cyr.iso
./build.sh stock.iso micro.iso                      # builds both
```

**Nothing is tied to a release version.** The two `win98qi_v1.1.0_*.iso` files
are simply the reference images used for development/validation; the tool only
assumes the ISO is a single-variant QuickInstall image (`osroots/1`) with the
usual Windows 9x tree. Windows ME is skipped. There is no variant-dropping
logic.

## Goals and constraints

* Cyrillic support is applied to the **image**, before any target filesystem
  exists — `ACP`/`OEMCP` are never changed on a running install.
* **English UI is preserved**: `HKCU\Control Panel\International\Locale` stays
  `00000409`, so date/number formats and menus remain English. Only the HKLM
  codepage/locale keys change.
* English stays the default keyboard; a Russian secondary keyboard is a
  deliberately deferred phase-2 item.
* No upstream code is modified, no Microsoft binaries are committed, no game
  data is edited.
* **No wine / `msdos.exe` / `regedit.exe`** — the registry is patched by a
  pure-Python Win9x CREG editor.

## Why this fork starts from the release ISOs

The two `win98qi_v1.1.0_*.iso` files are **not** reproducible from the git repo
alone. They are the prebuilt reference images published on
[upstream's GitHub Releases](https://github.com/oerg866/win98-quickinstall/releases/latest),
and they bundle two things the repo does not contain:

1. **The compiled framework.** Upstream's root `build.sh` compiles the Linux
   kernel (two variants), busybox, syslinux, dosfstools, util-linux,
   tiny-floppy-bootloader, the installer and mercypak, then zips `__BIN__` —
   a *sysprep environment*. Its last line is literally
   "Run sysprep.py to build an image." It produces tools, not an ISO.
   Building it needs every submodule (`.gitmodules` uses SSH URLs and includes
   the Linux kernel), a cross toolchain (`i486-linux-musl-cross`), `nasm`,
   `sudo`, and wine (per `BUILDING.md`).
2. **The Windows 98 installation itself.** `sysprep.py` requires
   `--osroot <IMG/RAW/VHD/VMDK/VDI>` — a hard disk image containing a *fully
   set up, patched Windows 9x installation*, prepared by hand in a VM
   (`IMAGE_CREATION.md`). That disk image is where `FULL.866`,
   `SLOWPNP.866`, `FASTPNP.866` and `DRIVER.866` come from. It is **not** in
   the repo (the largest tracked file is 2.8 MB; there are no `*.866` files,
   no `osroots/`, no disk images) and it cannot be committed — it is
   Microsoft-covered content.

So this fork is deliberately a **post-processor**: it opens the finished,
pinned release ISO and replaces exactly four files
(`FULL.866`, `SLOWPNP.866`, `FASTPNP.866`, `win98qi.inf`), preserving every
other byte — the compiled kernel, `cdrom.img`, El Torito, `bin/`,
`driver.ex/`, `extras/`. The pinned hashes and the `--verify` diff are defined
against those exact release bytes, which is what makes the result reproducible
without shipping any Windows binaries.

Building from source would trade the two ISOs for **two raw Win98 disk images
plus a full cross-compilation toolchain** — strictly more work, not less, and
still dependent on a pre-installed Windows 98 system. That is why
"full framework rebuild" and "`--cyrillic` in `sysprep.py` for builds from a
raw OSRoot disk image" are listed as out of scope / deferred.

## Files

```
win98-quickinstall/sysprep/cyrillic/
├── recipe.ini     # all data: font map, added files, reference .reg, CREG edits,
│                  # INI snippets, pinned hashes, verify constants
├── cyrillize.py   # the tool (MercyPak V1/V2, donor extraction, CREG editor,
│                  # ISO rebuild, --verify)
├── build.sh       # one-command reproduction
├── .gitignore     # Python cache rules
└── README.md      # this file
```

`build.sh` lives in the fork. It takes the source ISO(s) as arguments and
resolves them relative to the current directory, then the **workspace root**
(the parent of `win98-quickinstall/`). Outputs are written next to each input.

## Requirements

### Toolchain

`git` (to clone upstream), `cabextract`, `7z`, `python3`, `unzip`, and `file`
(used by `--verify`). Python dependency: **`pycdlib`** only. The full
`sysprep/requirements.txt` also installs `FATtools`, `wininfparser`,
`cabarchive` and `xattr`, but those are only used by upstream's `sysprep.py`
and are **not needed here**. No wine, no wineprefix, no DOS emulator.

```bash
git clone <your-fork-url> win98-quickinstall   # fork containing sysprep/cyrillic/
pip3 install -r win98-quickinstall/sysprep/requirements.txt   # or just: pip3 install pycdlib
```

(Cloning bare upstream does **not** include `sysprep/cyrillic/` — either clone
your fork or copy that directory into an upstream clone.)

On PEP 668 ("externally managed") systems add `--break-system-packages`.
A plain clone is enough — **do not** use `--recurse-submodules`
(`.gitmodules` uses SSH URLs and pulls in the Linux kernel; none of it is used).

### Files outside the git repo

These live in the workspace root (or under `win98ru/`).

| File | Purpose | Actually read? |
|---|---|---|
| any single-variant QuickInstall `*.iso` | the image you pass to `build.sh` | **yes** |
| `win98ru/BASE4.CAB` | donor fonts / NLS payloads (20 files) | **yes** |
| `win98se_2222.ru.iso` | donor Russian Win98 SE CD (provenance only) | **no** — never opened |

The `win98qi_v1.1.0_*.iso` files are just the two reference images used for
development/validation — the build has **no dependency on their names or
version**. Any single-variant QuickInstall ISO can be passed.

**The hash gate is relaxed and version-independent.** `cyrillize.py` only
verifies the inputs the current run actually consumes: `win98ru/BASE4.CAB`
always, plus `--iso` if its basename happens to be a known release listed in
`[hashes]`. An unlisted ISO (any version, any name) is used without a hash.
Unused pinned files are ignored entirely — they need not be present and cannot
block a build with a stale hash. A file that *is* checked and is missing or
mismatched is still a hard error.

Pass `--strict-hashes` to restore the original behaviour (verify the whole
`[hashes]` table, requiring all four). `--verify` never runs the hash gate —
it validates the output ISO directly.

**Not needed:**

* The other 93 files in `win98ru/` — only `BASE4.CAB` is used.
* `win98se_2222.ru.iso` — never read; optional (checked only with
  `--strict-hashes`).
* The generated `*_cyr.iso` outputs — they are *products*, never build inputs.
  The build always starts from the source ISO you pass; delete the outputs and
  rebuild any time (they are ~1.3 GB and gitignored).
* Wine, a wineprefix, or `sysprep/registry/*`.
* `README.md` / `.gitignore` in the workspace root — documentation only.

`--verify` optionally uses the matching original input ISO (auto-derived from
`*_cyr.iso` → `*.iso`) for its full data diff; if it is missing, all other
checks still run and verification still passes (a note is printed).

**Do I still need all the ISOs?** No. To build one image you need only that
one source ISO plus `win98ru/BASE4.CAB` — and you do **not** need the
`*_cyr.iso` outputs. Pass several ISOs to `build.sh` to build them all in one
run.

## Quickstart

```bash
cd /home/igor/win98-qi-cyrillic
./win98-quickinstall/sysprep/cyrillic/build.sh <input.iso> [<input2.iso> ...]
# e.g.
./win98-quickinstall/sysprep/cyrillic/build.sh win98qi_v1.1.0_stock.iso
./win98-quickinstall/sysprep/cyrillic/build.sh win98qi_v1.1.0_stock.iso win98qi_v1.1.0_micro_directx81.iso
./win98-quickinstall/sysprep/cyrillic/build.sh /mnt/isos/my-custom-build.iso
```

Each input produces `<stem>_cyr.iso` next to it. `build.sh --help` lists the
options (`--strict-hashes`, `--rebuild=inplace|makeiso`).

`build.sh` runs, in order:

1. `--smoke-test` — validates the toolchain and proves the CREG editor can
   patch a real `SYSTEM.DAT` (on the first input).
2. build each input ISO → 3. `--verify` each output.

Manual invocation (use this for a custom output name):

```bash
python3 win98-quickinstall/sysprep/cyrillic/cyrillize.py --smoke-test --iso <input.iso>
python3 win98-quickinstall/sysprep/cyrillic/cyrillize.py --iso <input.iso> --out <output>_cyr.iso
python3 win98-quickinstall/sysprep/cyrillic/cyrillize.py --verify --iso <output>_cyr.iso
python3 win98-quickinstall/sysprep/cyrillic/cyrillize.py --help
python3 win98-quickinstall/sysprep/cyrillic/cyrillize.py --strict-hashes --iso <input.iso> --out <output>_cyr.iso
```

`--iso`/`--out` resolve relative to the current directory, falling back to the
workspace root. Scratch files go to `/tmp/opencode` (or the system temp dir);
source ISOs are opened read-only and never modified.

### Version independence

Nothing in the code or recipe is tied to `v1.1.0`. `build.sh` takes the ISO as
an argument, derives `<stem>_cyr.iso`, and `cyrillize.py` works purely on the
ISO's contents (`osroots/1/*.866`, `win98qi.inf`). The pinned `[hashes]`
entries are only reference digests for the known release images: in the default
relaxed mode an unlisted ISO is accepted without a hash. The recipe's font,
NLS and CREG edits target structural Windows 9x paths (WINDOWS/FONTS, WIN.INI,
SYSTEM.INI, `Nls\Codepage`, `Nls\Locale`), which are stable across QuickInstall
releases; `--verify` still checks every expected value on the output.

## Verified facts that constrain the design

These were established by parsing the two `v1.1.0` reference images read-only,
and they are why the implementation looks the way it does:

* Both ISOs are already single-variant (`osroots/1` only).
* `FULL.866` is MercyPak **V2** (`MRCY`): stock 146 dirs / 2046 files /
  281,955,135 B; 98Lite 81 dirs / 1602 files / 223,909,632 B.
* `SLOWPNP.866` / `FASTPNP.866` are MercyPak **V1** (`ZIEG`), `dirCount=1`,
  `fileCount=1`, one entry `WINDOWS\SYSTEM.DAT`.
* `WINDOWS\USER.DAT` lives **inside `FULL.866`** (94,240 B stock /
  24,608 B 98Lite).
* `WINDOWS\SYSTEM\UNICODE.BIN` is already byte-identical to the Russian CD's
  (56,057 B, sha256 `fa7d22bb…`, 30 codepages incl. 1251 and 866) — **no
  replacement needed**; the IFSMGR fallback that corrupted filenames on a live
  install is already absent.
* All `cp_*.nls`, `locale.nls`, `unicode.nls`, `intl.cpl`, `keybrd3.sys`,
  `ega.cpi` are already present.
* Only 4 files are missing in both images (`xlat866.bin`, `charset.dat`,
  `kbdru.kbd`, `ega3.cpi`); 98Lite additionally lacks `country.sys`.
* All 15 `.FON` destinations exist as Western fonts.
* `WIN.INI` has `[FontSubstitutes]` with 5 name-only aliases; `SYSTEM.INI
  [keyboard]` has `oemansi.bin=` empty.
* `cdrom.img` (2,949,120 B), `boot.cat` and `[BOOT]/Boot-2.88M.img` are at the
  ISO root (the `[BOOT]` entry is 7-Zip's synthetic view of El Torito, not a
  real directory record).
* **76 files carry DOS hidden/system attributes** (stock; 28 in 98Lite),
  including `MSDOS.SYS` (`0x07`), `USER.DAT` (`0x03`) and every `.FON`
  (`0x02`). This is the decisive constraint: repacking from a plain Linux
  directory would lose them.
* 98Lite's `FULL.866` contains two **duplicate paths** (`oeminfo.ini`,
  `oemlogo.bmp`), so entries cannot be collapsed into a dict keyed by path.

## The complete recipe

### 15 font replacements — `[CP866]`, `WINDOWS/FONTS` (LDID 20)

| Destination | Source in BASE4.CAB | Size |
|---|---|---|
| `DOSAPP.FON` | `app866.fon` | 37,328 |
| `VGAOEM.FON` | `vga866.fon` | 5,152 |
| `VGASYS.FON` | `vgas1251.fon` | 6,912 |
| `VGAFIX.FON` | `vgaf1251.fon` | 5,600 |
| `SSERIFE.FON` | `ssee1251.fon` | 68,848 |
| `SERIFE.FON` | `sere1251.fon` | 63,296 |
| `COURE.FON` | `coue1251.fon` | 23,440 |
| `SMALLE.FON` | `smae1251.fon` | 24,832 |
| `8514SYS.FON` | `85s1251.fon` | 10,064 |
| `8514FIX.FON` | `85f1251.fon` | 10,976 |
| `8514OEM.FON` | `85866.fon` | 12,288 |
| `SSERIFF.FON` | `ssef1251.fon` | 98,256 |
| `SERIFF.FON` | `serf1251.fon` | 90,736 |
| `COURF.FON` | `couf1251.fon` | 31,808 |
| `SMALLF.FON` | `smaf1251.fon` | 19,760 |

`SYMBOLE.FON` / `SYMBOLF.FON`, `MODERN.FON`, `VGA850.FON` are untouched.

### Added files — `[CopyDat866]`, `[CyrillicKbds]`, `CopyDOSIntl`

| Destination | Source | Size |
|---|---|---|
| `WINDOWS/SYSTEM/CHARSET.DAT` | `866.dat` | 524 |
| `WINDOWS/SYSTEM/XLAT866.BIN` | `xlat866.bin` | 324 |
| `WINDOWS/SYSTEM/KBDRU.KBD` | `kbdru.kbd` | 473 |
| `WINDOWS/COMMAND/EGA3.CPI` | `ega3.cpi` | 58,753 |
| `WINDOWS/COMMAND/COUNTRY.SYS` | `country.sys` | 30,742 |

`COUNTRY.SYS` is present (and byte-identical to the donor) in the stock image
and was stripped by 98Lite — insert-or-replace handles both with one branch.

### Registry — HKLM only

Reference `.reg` (kept in `recipe.ini` for documentation):

```reg
REGEDIT4
[HKEY_LOCAL_MACHINE\System\CurrentControlSet\Control\Nls\Codepage]
"ACP"="1251"
"OEMCP"="866"
"1251"="cp_1251.nls"
"866"="cp_866.nls"
"20866"="cp_20866.nls"
"28595"="cp_28595.nls"
[HKEY_LOCAL_MACHINE\System\CurrentControlSet\Control\Nls\Locale]
@="00000419"
"SystemLocale"="00000419"
```

`HKCU\Control Panel\International\Locale` is deliberately **not** touched —
that is what keeps the UI English. The four `cp_*.nls` mappings already exist
in the stock registry. See "Registry patch without wine" for what is actually
applied.

### `WIN.INI` — `[CyrSubs]` inside `[FontSubstitutes]`

The 5 existing aliases are kept and exact duplicates de-duped; the following
are appended (`MS Shell Dlg=MS Sans Serif` already exists and is skipped):

```
MS Shell Dlg=MS Sans Serif
System,0=System,204
Fixedsys,0=Fixedsys,204
Small Fonts,0=Small Fonts,204
MS Sans Serif,0=MS Sans Serif,204
MS Shell Dlg,204=MS Sans Serif,204
MS Serif,0=MS Serif,204
Arial Cyr,204=Arial,204
Arial Cyr,0=Arial,204
Arial CE,238=Arial,238
Courier New Cyr,204=Courier New,204
Courier New Cyr,0=Courier New,204
Courier,0=Courier New,204
Courier New CE,238=Courier New,238
Times New Roman Cyr,204=Times New Roman,204
Times New Roman Cyr,0=Times New Roman,204
Times New Roman CE,238=Times New Roman,238
Helvetica,204=Arial,204
Helvetica,0=Arial,204
Times,204=Times New Roman,204
Times,0=Times New Roman,204
```

There is deliberately **no** `Arial,0=Arial,204`: with `ACP=1251` the WGL4
TTFs resolve cp1251 bytes to U+0410-range codepoints, so it is unnecessary.

### `SYSTEM.INI` — `[XLAT866]`

`[keyboard] oemansi.bin=xlat866.bin` (was empty).

### Label

` [RU fonts, EN UI]` is appended to `osroots/1/win98qi.inf`.

## How the pipeline works

`cyrillize.py` runs these stages. Everything is deterministic and driven by
`recipe.ini`.

### 1. Pinned hashes

SHA-256 of the inputs this run consumes (`win98ru/BASE4.CAB` and `--iso` if
listed in `[hashes]`) is checked; a mismatch aborts. An unlisted ISO is
accepted without a hash, so the build is version-independent.
`--strict-hashes` checks all four entries. `--out` must differ from `--iso`.

### 2. Donor extraction

The 20 donor files are streamed out of `win98ru/BASE4.CAB` with
`cabextract -p -F <name>`, renamed per the tables above, and each size is
verified. Nothing is written into the repository.

### 3. Reading the ISO

`FULL.866`, `SLOWPNP.866`, `FASTPNP.866` and `win98qi.inf` are read directly
from the source ISO with `pycdlib` (`get_file_from_iso`, Joliet paths). This is
equivalent to extracting the ISO with `7z x`, but avoids unpacking 700 MB we
do not need. `--rebuild makeiso` performs the full `7z x` instead.

### 4. MercyPak V1 / V2 format

Per `installer/install.c`:

```
FILE HEADER:  4-byte magic ("ZIEG" V1 / "MRCY" V2)
              UINT32 dirCount, UINT32 fileCount

Per directory:  BYTE attr, BYTE nameLen, name bytes (not NUL terminated)

V1, per file:   BYTE nameLen, name bytes, BYTE attr,
                UINT16 dosDate, UINT16 dosTime, UINT32 size, data blob

V2, per group:  BYTE identicalCount,
                then identicalCount x (nameLen, name, attr, dosDate, dosTime),
                then UINT32 size, ONE shared data blob
```

`install.c` asserts `identicalCount <= 16`; the writer caps groups at **8**
(`mercypak.py`'s `MAX_FILES_PER_KNOWN_DATA`).

### 5. Reader / writer — metadata preservation

Entries are kept as an **ordered list** of `{path, attr, date, time, data}`,
not a dict keyed by lowercase path. This:

* preserves every DOS `attr`/`dosDate`/`dosTime` (the 76 hidden/system flags),
* preserves 98Lite's two duplicate paths,
* keeps the build deterministic — no filesystem mtimes are read for payload
  metadata; new files get the fixed `[meta]` values.

The V2 writer regenerates dedup groups by hashing data, capped at 8.

### 6. Insert-or-replace overlay into `FULL.866`

One branch, no per-image implementation: for each of the 15 fonts + 5 data
files, if the normalized path exists, replace its `data` **keeping
attr/date/time**; otherwise append a new entry with the fixed `[meta]`
metadata (uppercase `\`-separated DOS path). `WIN.INI` and `SYSTEM.INI` bytes
are patched in place (CRLF, cp1252 — all inserted text is ASCII).

### 7. Registry patch without wine

`SLOWPNP.866` and `FASTPNP.866` are patched **separately** (they produce
different registries). Each holds one `WINDOWS\SYSTEM.DAT`.

Win9x `SYSTEM.DAT`/`USER.DAT` are `CREG` hives storing `REG_SZ` values as
`[u16 name_len][u16 data_len][name][data]`. The three functional values are
all **same-length ASCII**, so they are edited in place:

| value | from | to |
|---|---|---|
| `HKLM\...\Nls\Codepage` `ACP` | `1252` | `1251` |
| `HKLM\...\Nls\Codepage` `OEMCP` | `437` | `866` |
| `HKLM\...\Nls\Locale` default (`@`) | `00000409` | `00000419` |

No key node, pointer, value-count or free-space chain is touched — exactly
**5 bytes differ**, file size unchanged. This is byte-identical to what
`regedit` does for those fields (confirmed by diffing its output). The
`Nls\Locale` default record is disambiguated from other `00000409` defaults by
taking the occurrence immediately preceding the unique `ACP` record (the
Locale key's values precede Codepage's) — verified on both stock and 98Lite
hives.

**Deliberate difference:** the recipe's `"SystemLocale"="00000419"` is *not*
written. It is a Win9x-ignored marker (the real system locale is the `Locale`
key's default value, which we do set), and adding a new value would require
growing the CREG hive (free-space chain + pointer surgery) — the one part of
`regedit`'s output that is not a safe in-place edit. The validation checklist
only requires `Locale=00000419`, which is satisfied.

### 8. ISO rebuild

**`--rebuild inplace` (default):** `pycdlib` `rm_file` / `add_fp` replaces
exactly the 4 target files. Every other byte — El Torito boot catalog,
`boot.cat` (byte-identical), `cdrom.img`, the `[BOOT]/Boot-2.88M.img` 2.88M
emulation, all of `bin/`, `driver.ex/`, ... — is kept exactly as in the source.
No `os.walk` reordering, no per-file timestamp churn.

**`--rebuild makeiso`:** reproduces the upstream path — full `7z x`
extraction, patched `.866`/`.inf` written into the tree, then
`makeiso.makeIso(tree, out, 'cdrom.img', 'QuickInstall')`. It deletes the
extracted `boot.cat` so `add_eltorito()` creates the only catalog. This method
is bootable but re-walking the tree resets timestamps and is not byte-stable,
so `inplace` is the default. Both methods pass the same `--verify`.

### Determinism

The tool never reads filesystem mtimes for payload metadata; all
`attr`/`date`/`time` come from the parsed input payload and donor timestamps
are irrelevant. All four patched payloads are byte-for-byte identical across
runs. The ISO *byte stream* is not guaranteed identical: pycdlib stamps the
volume descriptor's modification time with the build time (a handful of bytes
in the PVD). That is why `--verify` — which re-parses payload contents — is the
reproducibility check, not an output hash.

## `--verify` (static, before any boot test)

Re-parses an output ISO and asserts:

* `file` → ISO 9660 **bootable**; `boot.cat`, `cdrom.img`,
  `[BOOT]/Boot-2.88M.img` present; pycdlib sees an El Torito catalog.
* `FULL.866` magic `MRCY`; `fileCount` equals parsed entries.
* all 15 fonts have the Cyrillic sizes; `SYMBOLE.FON`/`SYMBOLF.FON` unchanged.
* the 4/5 added files present with expected sizes; `UNICODE.BIN` still
  sha256 `fa7d22bb…`.
* `WIN.INI` contains `MS Sans Serif,0=MS Sans Serif,204`; `SYSTEM.INI`
  contains `oemansi.bin=xlat866.bin`.
* `SLOWPNP.866`/`FASTPNP.866` still V1 with one `WINDOWS/SYSTEM.DAT`; the
  CREG records show `ACP=1251`, `OEMCP=866`, `Locale=00000419` (old values
  absent), and each `SYSTEM.DAT` equals the deterministic pure-Python CREG
  patch of the input.
* `HKCU\Control Panel\International\Locale` still `00000409` (USER.DAT
  byte-identical to input).
* `MSDOS.SYS` DOS attr still `0x07`; all 15 Cyrillic font destinations still
  `0x02` — the attr regression check.
* diff of file lists against the input ISO shows only the intended added
  entries; every unchanged entry keeps identical data **and** `attr`/`date`/`time`.

## Boot test (stock first, then 98Lite)

English desktop/menus → Notepad cp1251 `.txt` readable without manually
choosing Script=Cyrillic → one Russian installer/UI → one font-using game →
create/read/delete a Cyrillic-named file and shortcut in Explorer (regression
check for the earlier live-install filename corruption) → taskbar EN/RU with EN
default.

## Rollback

Source ISOs are never modified. Delete the generated `*_cyr.iso` files.

## Risks / accepted trade-offs

* Corrupting `SYSTEM.DAT` — eliminated: the pure-Python editor only makes
  same-length in-place edits, and the step-0 smoke test + `--verify` check the
  exact byte transformation.
* Losing hidden/system attrs on repack — prevented by the dedicated
  reader/writer, verified above.
* V2 dedup group >16 breaks `install.c` — capped at 8.
* 98Lite missing `COUNTRY.SYS` etc. — insert-or-replace.
* `HKCU Locale` accidentally `0419` — excluded, verified.
* `makeiso.py` losing El Torito — verified `boot.cat` + `[BOOT]`; inplace is
  the default.
* Western accented text renders as Cyrillic; apps with a hardcoded cp1252
  decoder cannot be fixed globally — accepted/documented.

## Deferred / out of scope

* `--cyrillic` in `sysprep.py` for builds from a raw OSRoot disk image.
* Phase 2: Russian keyboard entry in `USER.DAT` (`HKCU\Keyboard Layout\Preload`
  `"2"="00000419"`, EN stays default) and DOS cp866 `CONFIG.SYS` /
  `AUTOEXEC.BAT` edits — the only steps that would touch `USER.DAT` or boot
  files; deferring keeps this build small and reversible.
* Fork of `win98-driver-lib-extra` (NVIDIA 82.69, ATI Catalyst 6.2, CMI8738);
  multi-variant menu; full framework rebuild (Linux kernel, syslinux, etc.).
