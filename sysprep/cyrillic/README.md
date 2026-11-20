# Cyrillic QuickInstall fork — build notes

Two **single-variant**, **English-UI** QuickInstall ISOs with Cyrillic support
(cp1251 ANSI / cp866 OEM) baked in at image build time. The 15 system bitmap
fonts, four missing DOS/NLS files, `[FontSubstitutes]`, the `oemansi.bin=`
translation table and the `HKLM\...\Nls` codepage/locale registry values are
taken verbatim from Microsoft's own Russian Windows 98 SE `[CP866]` /
`[CopyDat866]` recipe. Nothing in the shell / Explorer resources is changed.

| Input | Output |
|---|---|
| `win98qi_v1.1.0_stock.iso` | `win98qi_v1.1.0_stock_cyr.iso` |
| `win98qi_v1.1.0_micro_directx81.iso` | `win98qi_v1.1.0_micro_directx81_cyr.iso` |

Windows ME is skipped. Both inputs are already single-variant (`osroots/1`).

## Files

```
sysprep/cyrillic/
├── recipe.ini     # all data: §4.1 font map, §4.2 adds, §4.3 reg, §4.4/.5 INI
│                  # snippets, §2 pinned hashes, §8 verify constants
├── cyrillize.py   # the tool: MercyPak V1/V2 reader+writer, donor extraction,
│                  # pure-Python Win9x CREG registry editor, ISO rebuild,
│                  # --verify
├── build.sh       # one-command reproduction (both builds + both verifies)
└── README.md      # this file
```

No upstream code is modified, no Microsoft binaries are committed, and **the
pipeline is completely wine-free** (no `wine` / `msdos.exe` / `regedit.exe`).

## Requirements / reproduction

Toolchain (verified present): `git`, `cabextract`, `7z`, `python3`, `unzip`.
Python deps from upstream:

```bash
cd /home/igor/win98-qi-cyrillic
git clone https://github.com/oerg866/win98-quickinstall.git win98-quickinstall
pip3 install -r win98-quickinstall/sysprep/requirements.txt   # pycdlib, FATtools, ...
./win98-quickinstall/sysprep/cyrillic/build.sh
```

On PEP 668 ("externally managed") systems, add `--break-system-packages` to
`pip3 install`. A plain clone is enough — **do not** use
`--recurse-submodules` (`.gitmodules` uses SSH URLs and includes the Linux
kernel; nothing here needs them).

Required inputs, all in the workspace root and hash-pinned in `recipe.ini`
(`cyrillize.py` refuses to run on a mismatch):

| File | Role |
|---|---|
| `win98qi_v1.1.0_stock.iso`, `win98qi_v1.1.0_micro_directx81.iso` | source ISOs (never modified) |
| `win98se_2222.ru.iso` (label `WINDOWS 98 SE RUS`) | donor reference |
| `win98ru/BASE4.CAB` | donor fonts / NLS payloads |

`build.sh` runs, in order:

1. `--smoke-test` — validates the toolchain and proves the pure-Python CREG
   editor can patch a real Win9x `SYSTEM.DAT` before anything else (PLAN.md §6
   step 0, wine-free).
2. build stock, 3. build 98Lite, 4. `--verify` stock, 5. `--verify` 98Lite.

Manual invocation:

```bash
python3 sysprep/cyrillic/cyrillize.py --smoke-test --iso win98qi_v1.1.0_stock.iso
python3 sysprep/cyrillic/cyrillize.py --iso <input>.iso --out <output>_cyr.iso
python3 sysprep/cyrillic/cyrillize.py --verify --iso <output>_cyr.iso
```

`cyrillize.py` resolves `--iso`/`--out` relative to the current directory,
falling back to the workspace root. Scratch files live under `/tmp/opencode`
(or the system temp dir); source ISOs are opened read-only.

## What the tool does (PLAN.md §7)

1. Verifies the four pinned SHA-256 hashes.
2. Streams the 20 donor files out of `win98ru/BASE4.CAB` with
   `cabextract -p -F`, renaming per §4.1/§4.2 and checking each size. Nothing
   is written into the repo.
3. Reads `FULL.866`, `SLOWPNP.866`, `FASTPNP.866`, `win98qi.inf` directly from
   the source ISO with pycdlib (equivalent to the §7 step 3 `7z x` extraction,
   but avoids unpacking 700 MB we do not need).
4. Generic MercyPak V1 (`ZIEG`) / V2 (`MRCY`) reader, per
   `installer/install.c`. Entries are kept as an **ordered list** retaining
   `attr`, `dosDate`, `dosTime`. This preserves the 76 hidden/system DOS
   attributes (incl. `MSDOS.SYS` `0x07`, all `.FON` `0x02`) and the two
   duplicate paths (`oeminfo.ini` / `oemlogo.bmp`) present in the 98Lite
   `FULL.866` — a plain dict keyed by lowercase path would silently drop them.
5. **Insert-or-replace** overlay into `FULL.866`: 15 font replacements + 5 data
   files. Replaced entries keep their `attr`/`date`/`time`; inserted entries get
   the fixed `[meta]` values (never filesystem mtimes). `COUNTRY.SYS` is
   byte-identical to the donor in the stock image and is inserted only into
   98Lite. `WIN.INI` gains the `[CyrSubs]` lines inside `[FontSubstitutes]`
   (the 5 existing aliases are kept, exact duplicates de-duped); `SYSTEM.INI`
   `[keyboard] oemansi.bin=xlat866.bin`.
6. Patches `SYSTEM.DAT` inside **both** `SLOWPNP.866` and `FASTPNP.866`
   separately with a **pure-Python Win9x CREG value editor** (no wine). Win9x
   registry files start with `CREG` and store `REG_SZ` values as compact
   `[u16 name_len][u16 data_len][name][data]` records. The three functional
   values (`ACP` `1252`->`1251`, `OEMCP` `437`->`866`, `Nls\Locale` default
   `00000409`->`00000419`) are all **same-length ASCII**, so they are edited
   in place: no key node, pointer, value-count or free-space chain is touched.
   This is byte-identical to what `regedit` does for those fields (confirmed
   by diffing its output). `HKCU\Control Panel\International\Locale` is
   deliberately left at `00000409`, which keeps date/number formats and the
   UI English. See "Registry patch without wine" below for the one value we
   intentionally do not add.
7. Writes payloads back with a generic writer: V2 for `FULL.866` (dedup groups
   regenerated by hashing, capped at **8** = `mercypak.py`'s
   `MAX_FILES_PER_KNOWN_DATA`; `install.c` asserts ≤16), V1 for the two
   registry payloads. `attr`/`date`/`time` are preserved everywhere.
8. Appends ` [RU fonts, EN UI]` to the `osroots/1/win98qi.inf` label.
9. Rebuilds the ISO.

### ISO rebuild: default `inplace`, optional `makeiso`

`PLAN.md` §7 step 9 names upstream `makeiso.py:makeIso()` as the primary and
pycdlib in-place `rm_file`/`add_fp` as the fallback. **`--rebuild inplace` is
the default here** because it is strictly safer and byte-preserving:

* Only the 4 target files are replaced. Every other byte of the ISO — El
  Torito boot catalog, `boot.cat` (byte-identical), `cdrom.img`, the `[BOOT]/
  Boot-2.88M.img` 2.88M emulation, all of `bin/`, `driver.ex/`, ... — is kept
  exactly as in the source. No `os.walk` reordering; every file keeps its
  original DOS/ISO timestamp (only the volume-descriptor modification time
  reflects the build time — see Determinism).
* A `makeiso.py` round-trip was tested: it is bootable, but re-walking the
  extracted tree re-adds `boot.cat` as a *second* regular file next to the
  El-Torito-generated one and resets every file's timestamp, so output bytes
  are not reproducible.

`--rebuild makeiso` is still available and reproduces the literal step 9 (full
`7z x` extraction, patched `.866`/`.inf` written into the tree, then
`makeiso.makeIso(tree, out, 'cdrom.img', 'QuickInstall')`; it deletes the
extracted `boot.cat` first so `add_eltorito()` creates the only catalog). Both
methods are validated by the same `--verify`.

### Determinism

The tool never reads filesystem mtimes for payload metadata — all
`attr`/`date`/`time` come from the parsed input payload, donor timestamps are
irrelevant, and the ISO is rewritten in place from the source. All four patched
payloads (`FULL.866`, `SLOWPNP.866`, `FASTPNP.866`, `win98qi.inf`) are
byte-for-byte identical across runs.

The ISO *byte stream* is not guaranteed identical across runs, though: pycdlib
stamps the volume descriptor's modification time with the build time (a handful
of bytes in the PVD, all other bytes including every file's data and timestamps
are preserved). This is exactly why `--verify` — which re-parses payload
contents — is the reproducibility check, not an output hash, as stated in
PLAN.md §7.

## `--verify` (PLAN.md §8, static, before any boot test)

Re-parses an output ISO and asserts:

* `file` → ISO 9660 **bootable**; `boot.cat`, `cdrom.img`,
  `[BOOT]/Boot-2.88M.img` present; pycdlib sees an El Torito catalog.
* `FULL.866` magic `MRCY`; `fileCount` equals parsed entries.
* all 15 fonts have the Cyrillic sizes; `SYMBOLE.FON`/`SYMBOLF.FON` unchanged
  (hash matches input).
* the 4/5 added files present with expected sizes;
  `UNICODE.BIN` still sha256 `fa7d22bb…`.
* `WIN.INI` contains `MS Sans Serif,0=MS Sans Serif,204`;
  `SYSTEM.INI` contains `oemansi.bin=xlat866.bin`.
* `SLOWPNP.866`/`FASTPNP.866` still V1 with one `WINDOWS/SYSTEM.DAT`;
  the CREG records show `ACP=1251`, `OEMCP=866`, `Locale=00000419`
  (old values absent). When the input ISO is available, each `SYSTEM.DAT`
  must equal the deterministic pure-Python CREG patch of the input.
* `HKCU\Control Panel\International\Locale` still `00000409` (USER.DAT
  byte-identical to input; the value block `\x06\x00\x08\x00Locale00000409`
  is checked directly).
* `MSDOS.SYS` DOS attr still `0x07`; all `.FON` still `0x02` — the attr
  regression check.
* diff of file lists against the input ISO (`*_cyr.iso` → `*.iso`, auto-derived)
  shows only the intended added entries; every unchanged entry keeps identical
  data **and** `attr`/`date`/`time`.

### Registry patch without wine

The original PLAN.md §4.3 recipe is a `.reg` file imported with Win98's
`regedit.exe` under a DOS emulator (wine). That dependency is removed. Win9x
`SYSTEM.DAT`/`USER.DAT` are `CREG` hives storing `REG_SZ` values as
`[u16 name_len][u16 data_len][name][data]`. `cyrillize.py` applies the three
functional values as same-length in-place byte edits (see `[creg]` in
`recipe.ini`), which is byte-identical to `regedit`'s own in-place changes:

| value | from | to |
|---|---|---|
| `HKLM\...\Nls\Codepage` `ACP` | `1252` | `1251` |
| `HKLM\...\Nls\Codepage` `OEMCP` | `437` | `866` |
| `HKLM\...\Nls\Locale` default (`@`) | `00000409` | `00000419` |

Everything else in `SYSTEM.DAT` is left untouched (file size unchanged, 5 bytes
differ). The `Nls\Locale` default record is disambiguated from other
`00000409` default values by taking the occurrence immediately preceding the
unique `ACP` record (the Locale key's values precede Codepage's) — verified on
both stock and 98Lite hives.

**Deliberate difference:** the recipe's `"SystemLocale"="00000419"` is *not*
written. It is a Win9x-ignored marker (the real system locale is the `Locale`
key's default value, which we do set), and adding a new value would require
growing the CREG hive (free-space chain + pointer surgery) — the one part of
`regedit`'s output that is not a safe in-place edit. PLAN.md §8 only requires
`Locale=00000419`, which is satisfied. `--verify` therefore checks the three
functional values, not `SystemLocale`.

### Boot test (stock first, then 98Lite)

English desktop/menus → Notepad cp1251 `.txt` readable without manually
choosing Script=Cyrillic → one Russian installer/UI → one font-using game →
create/read/delete a Cyrillic-named file and shortcut in Explorer (regression
check for the earlier live-install filename corruption) → taskbar EN/RU with EN
default.

## Rollback

Source ISOs are never modified. Delete the generated `*_cyr.iso` files.

## Risks / accepted trade-offs (PLAN.md §9)

* Corrupting `SYSTEM.DAT` — eliminated: the pure-Python editor only makes
  same-length in-place edits, and the step-0 smoke test + `--verify` check
  the exact byte transformation. No wine / DOS emulator involved.
* Losing hidden/system attrs on repack — prevented by the dedicated
  reader/writer, verified above.
* V2 dedup group >16 breaks `install.c` — capped at 8.
* 98Lite missing `COUNTRY.SYS` etc. — insert-or-replace.
* `HKCU Locale` accidentally `0419` → excluded from `cyrillic.reg`, verified.
* Western accented text renders as Cyrillic; apps with a hardcoded cp1252
  decoder cannot be fixed globally — accepted/documented.

## Deferred / out of scope (PLAN.md §10)

`--cyrillic` in `sysprep.py` for raw OSRoot disk images; USER.DAT keyboard
preload (`2=00000419`) and DOS cp866 `CONFIG.SYS`/`AUTOEXEC.BAT` edits
(phase 2); driver-lib-extra fork; multi-variant menu; full framework rebuild.
