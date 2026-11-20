# Cyrillic QuickInstall Fork — Implementation Plan (v2, simplified)

## 1. Goal

Two **single-variant** QuickInstall ISOs with Cyrillic support baked in at image build
time, **English UI preserved**.

| Order | Input | Output |
|---|---|---|
| 1 (primary) | `win98qi_v1.1.0_stock.iso` | `win98qi_v1.1.0_stock_cyr.iso` |
| 2 (second) | `win98qi_v1.1.0_micro_directx81.iso` | `win98qi_v1.1.0_micro_directx81_cyr.iso` |
| — | Windows ME | skipped |

Both use the **same script**. The 98Lite image is second only because 98Lite stripped
`COUNTRY.SYS` (and some auxiliaries), so the overlay needs insert-or-replace rather
than replace-only — one `if` branch, no separate implementation.

Constraints: never change `ACP`/`OEMCP` on a running install (here it is image-time,
before any target filesystem exists); shell resources untouched; English default
keyboard, Russian secondary; no Microsoft binaries committed; no game data edits.

---

## 2. Pinned inputs (all hashed locally, all match upstream release digests)

| File | SHA-256 |
|---|---|
| `win98qi_v1.1.0_stock.iso` | `7df4d4ccc3bee09303f42eb4d02da22911b4c6f2b4b6f97d928202017b5aad7e` |
| `win98qi_v1.1.0_micro_directx81.iso` | `1357e7228024dead2b03e6960c865db162eb1c4ac4becd0f471b4f04e5a8631b` |
| `win98se_2222.ru.iso` (donor, label `WINDOWS 98 SE RUS`) | `e8003f0810e9739164dbf1802b31bd37b4523a282f52af982f13a8bd74724765` |
| `win98ru/BASE4.CAB` (donor payload) | `eca5e1f43c26db0e81031d608cf09db4735ea7dff0a357736b4bcba27d50f2d5` |

`cyrillize.py` refuses to run if any hash differs. Toolchain verified present:
`git` 2.53, `cabextract`, `7z`, `python3`, `wine` 10.0, `winepath`, `unzip`.
Missing Python deps: `FATtools`, `wininfparser`, `cabarchive`, `pycdlib`.

---

## 3. Verified facts that constrain the design

- Both ISOs are **already single-variant**, `osroots/1` only. No variant-dropping logic.
- `FULL.866` is MercyPak **V2** (`MRCY`): stock 146 dirs / 2046 files / 281,955,135 B;
  98Lite 81 dirs / 1602 files / 223,909,632 B.
- `SLOWPNP.866` / `FASTPNP.866` are MercyPak **V1** (`ZIEG`), `dirCount=1`,
  `fileCount=1`, one entry `WINDOWS/SYSTEM.DAT`. Same header in both images.
- `WINDOWS/USER.DAT` lives **inside `FULL.866`** (94,240 B stock / 24,608 B 98Lite).
- **`WINDOWS/SYSTEM/UNICODE.BIN` is byte-identical to the Russian CD's**, 56,057 B,
  sha256 `fa7d22bb…`, 30 codepages **including 1251 and 866**. No replacement needed —
  the IFSMGR fallback that corrupted filenames on the live install is already absent.
- All `cp_*.nls` (incl. `cp_1251`, `cp_1252`, `cp_855`, `cp_866`, `cp_20866`,
  `cp_28595`), `locale.nls`, `unicode.nls`, `intl.cpl`, `keybrd3.sys`, `ega.cpi` are
  already present.
- **Only 4 files are missing in both**: `xlat866.bin`, `charset.dat`, `kbdru.kbd`,
  `ega3.cpi`. 98Lite additionally lacks `country.sys`.
- All 15 `.FON` destinations exist as Western fonts under `WINDOWS/FONTS/`.
- `WIN.INI` has `[FontSubstitutes]` with 5 name-only aliases and no charset rules;
  `SYSTEM.INI [keyboard]` has `oemansi.bin=` empty.
- `cdrom.img` (2,949,120 B), `boot.cat` and `[BOOT]/Boot-2.88M.img` present at ISO root.
- **`wine` 10.0 and `winepath` work** on this machine.
- **76 files carry DOS hidden/system attributes**, including `MSDOS.SYS` (`0x07`),
  `USER.DAT` (`0x03`), `SYSTEM.1ST`, `desktop.ini`, `folder.htt`, and **every `.FON`**
  (`0x02`). This is the decisive design constraint: repacking a payload from a plain
  Linux directory via `mercypak_pack(local_files=…)` would lose those attributes
  (`getfatattr()` falls back to permission-derived values). **The reader/writer must
  preserve `attr`, `dosDate` and `dosTime` from the parsed entries.** It also makes the
  output deterministic.

---

## 4. The complete recipe (verbatim from `win98ru/BASE4.CAB` → `locale.inf` / `fonts.inf`)

### 4.1 Replace 15 fonts — `[CP866]`, destination `WINDOWS/FONTS` (LDID 20)

| Destination | Source in `BASE4.CAB` | Size |
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

`SYMBOLE.FON` / `SYMBOLF.FON` unchanged. `MODERN.FON`, `VGA850.FON` unchanged.

### 4.2 Add — `[CopyDat866]` (LDID 11 = SYSTEM), `[CyrillicKbds]`, `CopyDOSIntl` (13 = COMMAND)

| Destination | Source | Size |
|---|---|---|
| `WINDOWS/SYSTEM/CHARSET.DAT` | `866.dat` | 524 |
| `WINDOWS/SYSTEM/XLAT866.BIN` | `xlat866.bin` | 324 |
| `WINDOWS/SYSTEM/KBDRU.KBD` | `kbdru.kbd` | 473 |
| `WINDOWS/COMMAND/EGA3.CPI` | `ega3.cpi` | 58,753 |
| `WINDOWS/COMMAND/COUNTRY.SYS` | `country.sys` | 30,742 — **98Lite only** (stock has it) |

### 4.3 `cyrillic.reg` — `[RegCP866]` + `[SysLocale_0419]` (HKLM only)

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

**Deliberately omitted**: `HKCU\Control Panel\International\Locale=00000419`
(would switch date/number formats to Russian — this is what keeps the UI English),
QuickViewer's `CurrentFontCharSet`, and the `fontsize\96\System` aliases (optional).

### 4.4 `WIN.INI` — append `[CyrSubs]` lines inside the existing `[FontSubstitutes]`

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

Keep the 5 existing aliases; dedupe. Note Microsoft's recipe has **no**
`Arial,0=Arial,204` — with `ACP=1251` the WGL4 TTFs resolve cp1251 bytes to
U+0410-range codepoints, so it is unnecessary.

### 4.5 `SYSTEM.INI` — `[XLAT866]`

`[keyboard] oemansi.bin=xlat866.bin` (currently empty).

### 4.6 Optional phase 2 (not in the first build)

- Russian keyboard entry in `USER.DAT`: `HKCU\Keyboard Layout\Preload` →
  `"1"="00000409"`, `"2"="00000419"` (English stays default).
- DOS cp866: `[Config007]` / `[Auto866]` edits to `CONFIG.SYS` / `AUTOEXEC.BAT`.

Both are the only steps that touch `USER.DAT` or boot files; deferring them keeps the
first build small and reversible.

---

## 5. Minimal file layout — 4 new files, no upstream code changes

```
win98-quickinstall/sysprep/cyrillic/
├── recipe.ini     # all data: §4.1 map, §4.2 adds, §4.3 reg, §4.4/.5 INI snippets,
│                  # pinned hashes from §2
├── cyrillize.py   # the tool: MercyPak V1/V2 reader+writer, donor extraction,
│                  # regedit wrapper, ISO rebuild, --verify mode
├── build.sh       # runs both conversions in the required order
└── README.md      # usage, donor requirements, rollback
```

**Dropped from v1** (they added scope without helping reproducibility):

- modifying `sysprep/sysprep.py` with `--cyrillic` — not used by this pipeline; can be
  added later for builds from a real OSRoot disk image
- separate `cp866.map`, `files.manifest`, `*.reg`, `*.snippet`, `extract_cyrillic.py`
  files — folded into `recipe.ini` + `cyrillize.py`
- `unmercy.exe` + `mercypak_pack(local_files=…)` as the repack path — **rejected**,
  it loses the 76 hidden/system attributes (§3)
- no `installer/install.c` changes — its `.866` filename list is hardcoded

---

## 6. One-command reproduction

```bash
cd /home/igor/win98-qi-cyrillic
git clone https://github.com/oerg866/win98-quickinstall.git win98-quickinstall
pip3 install -r win98-quickinstall/sysprep/requirements.txt

# Step 0 — smoke-test the one fragile dependency before anything else:
#   wine win98-quickinstall/sysprep/registry/msdos.exe \
#        -e <winpath of regedit.exe> /L:SYSTEM.DAT /R:SYSTEM.DAT <winpath of a test .reg>
# Must succeed on a scratch SYSTEM.DAT. If it fails, stop and fix the toolchain.

./win98-quickinstall/sysprep/cyrillic/build.sh
```

`build.sh` runs, in order:

```bash
python3 .../cyrillize.py --iso win98qi_v1.1.0_stock.iso           --out win98qi_v1.1.0_stock_cyr.iso
python3 .../cyrillize.py --iso win98qi_v1.1.0_micro_directx81.iso --out win98qi_v1.1.0_micro_directx81_cyr.iso
python3 .../cyrillize.py --verify --iso win98qi_v1.1.0_stock_cyr.iso
python3 .../cyrillize.py --verify --iso win98qi_v1.1.0_micro_directx81_cyr.iso
```

Plain clone, **no** `--recurse-submodules` (`.gitmodules` uses `git@github.com:` SSH
URLs and includes the Linux kernel; nothing here needs them).

---

## 7. `cyrillize.py` pipeline

1. **Check** the four pinned hashes (§2); refuse on mismatch.
2. **Extract donor** from `win98ru/BASE4.CAB` with `cabextract -p -F <name>`; rename
   per §4.1/§4.2; verify each size. No Microsoft binaries are written into the repo.
3. **Extract ISO** to a scratch dir under `/tmp/opencode` with `7z x` (source ISO
   never modified).
4. **Read payloads** with one generic MercyPak reader (V1 `ZIEG` and V2 `MRCY`), per
   `installer/install.c`:
   - V2: `identicalCount` u8 → that many (`len` u8, name, `attr` u8, `dosDate` u16,
     `dosTime` u16) → `size` u32 + blob; `fileCount += identicalCount`
   - V1: one (`len` u8, name, `attr` u8, `dosDate` u16, `dosTime` u16, `size` u32,
     blob) per file
   - normalise `\`→`/`, key by lowercase path, retain `{path, attr, date, time, data}`
5. **Overlay into `FULL.866`** (insert-or-replace): 15 font replacements + 4/5 adds,
   preserving each replaced entry's `attr`/`date`/`time`. Patch `WIN.INI` and
   `SYSTEM.INI` bytes (CRLF, cp1252 — all inserted text is ASCII).
6. **Patch `SYSTEM.DAT` in both `SLOWPNP.866` and `FASTPNP.866`**: unpack the single
   entry into a temp dir, `chdir` there, then reuse upstream's exact invocation from
   `sysprep.py:run_regedit()`:
   `wine <msdos.exe> -e <winepath regedit.exe> /L:SYSTEM.DAT /R:SYSTEM.DAT <winepath cyrillic.reg>`
   (`winepath -w` conversion of the `.reg` and `regedit.exe` paths is required on
   Linux; cwd must contain `SYSTEM.DAT`). Both payloads must be patched separately —
   `fastpnp.reg`/`slowpnp.reg` produce different registries.
7. **Write payloads back** with one generic writer: V2 for `FULL.866` with dedup
   groups regenerated by hashing, capped at **8** (`mercypak.py`'s
   `MAX_FILES_PER_KNOWN_DATA`; `install.c` asserts ≤16); V1 for the two registry
   payloads. Preserve `attr`/`date`/`time` everywhere.
8. **Update `osroots/1/win98qi.inf`** label (append ` [RU fonts, EN UI]`).
9. **Rebuild ISO** with upstream `makeiso.py`'s `makeIso(tree, out, 'cdrom.img',
   'QuickInstall')` — the proven path; it re-adds El Torito 2.88M emulation from
   `cdrom.img`. Verify `boot.cat` + `[BOOT]/Boot-2.88M.img` afterwards. Fallback:
   `pycdlib` in-place `rm_file`/`add_fp` on the original ISO to preserve all other
   bytes exactly.

`--verify` re-parses an output ISO and asserts every item in §8.

### Determinism

The tool never reads filesystem mtimes for payload metadata — all `attr`/`date`/`time`
come from the input payload, and donor file timestamps are irrelevant. `os.walk`
order in `makeiso.py` may vary, so the ISO byte stream is not guaranteed identical
across runs, but the payload contents are; `--verify` is the reproducibility check,
not an output hash.

---

## 8. Validation (`--verify`, static, before any boot test)

- `file` → ISO 9660 bootable; `boot.cat`, `cdrom.img`, `[BOOT]/Boot-2.88M.img` present
- `FULL.866` magic `MRCY`, `fileCount` equals parsed entries
- all 15 fonts now have the Cyrillic sizes from §4.1; `SYMBOLE.FON`/`SYMBOLF.FON`
  unchanged (hash matches input)
- the 4/5 added files present with expected sizes
- `UNICODE.BIN` still sha256 `fa7d22bb…`
- `WIN.INI` contains `MS Sans Serif,0=MS Sans Serif,204`; `SYSTEM.INI` contains
  `oemansi.bin=xlat866.bin`
- `SLOWPNP.866`/`FASTPNP.866` still V1, one `WINDOWS/SYSTEM.DAT`; registry shows
  `ACP=1251`, `OEMCP=866`, `Locale=00000419`
- `HKCU\Control Panel\International\Locale` still `00000409`
- DOS attribute of `MSDOS.SYS` still `0x07`; all `.FON` still `0x02` — **the attr
  regression check**
- diff of file lists against the input ISO shows only the intended entries

### Boot test (stock first, then 98Lite)

English desktop/menus → Notepad cp1251 `.txt` readable **without** manually choosing
Script=Cyrillic → one Russian installer/UI → one font-using game → create/read/delete
a **Cyrillic-named file and shortcut** in Explorer (the regression check for the
earlier live-install breakage) → taskbar EN/RU with EN default.

Rollback: source ISOs are never modified; delete the generated `_cyr.iso`.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| `wine`/`msdos.exe`/`regedit.exe` cannot patch a Win9x `SYSTEM.DAT` | Step 0 smoke test; upstream `run_regedit()` proves it works on Linux+wine |
| Losing DOS hidden/system attrs on repack | Dedicated reader/writer preserves `attr`/`date`/`time`; verified in §8 |
| V2 dedup group >16 breaks `install.c` assertion | Cap at 8, as upstream `mercypak.py` does |
| 98Lite missing `COUNTRY.SYS` etc. | Insert-or-replace |
| `makeiso.py` loses El Torito | Verify `boot.cat` + `[BOOT]`; pycdlib fallback |
| `HKCU Locale` accidentally 0419 → Russian date/month names | Excluded from `cyrillic.reg`; verified |
| Western accented text renders as Cyrillic | Accepted trade-off; ASCII unaffected |
| Apps with a hardcoded cp1252 decoder | Cannot be fixed globally; documented |

---

## 10. Out of scope / deferred

- Fork of `win98-driver-lib-extra`: NVIDIA 82.69 (MDGx), ATI Catalyst 6.2 Win9x/ME,
  CMI8738 VxD+WDM; validate with `drivercopy.py --check <dir>`. Separate commit.
- `--cyrillic` support in `sysprep.py` for builds from a raw OSRoot disk image.
- Phase 2 items in §4.6 (USER.DAT keyboard, DOS cp866).
- Multi-variant menu, "RU games" OS variant, standalone `.txt` conversion, full
  framework rebuild (`build.sh`, Linux kernel, syslinux).

---

## 11. Current status

- All inputs present, hash-verified, and structurally parsed read-only.
- Only `PLAN.md` has been created. Upstream has **not** been cloned; step 0 of §6 is
  the first executable action.
