#!/usr/bin/env python3
"""wowbuild - fetch and install any WoW client build's macOS app bundle from Blizzard's CDN.

  wowbuild status                    what's installed vs what Battle.net expects
  wowbuild list [-p wowt] [-n 20]    builds available on the CDN
  wowbuild fetch 12.1.0.69404        download a build into the local library
  wowbuild install 12.1.0.69404      fetch + swap it into the game folder
  wowbuild revert                    restore the build Battle.net expects
  wowbuild library                   what's in the local library
  wowbuild clean [--library]         drop cached index data (and the library)
"""
import argparse, bisect, glob, json, os, plistlib, shutil, struct, subprocess, sys
import urllib.error, urllib.request, zlib
from concurrent.futures import ThreadPoolExecutor

HOME = os.path.expanduser("~/wow-build-fetch")
CACHE = f"{HOME}/cache"
LIB = f"{HOME}/library"
GAME_DIRS = ["/Applications/World of Warcraft",
             os.path.expanduser("~/Applications/World of Warcraft")]
UA = {"User-Agent": "wowbuild/1.0"}


def die(msg):
    sys.exit(f"error: {msg}")


def http(url, dest=None, rng=None):
    if dest and os.path.exists(dest) and os.path.getsize(dest) > 0:
        return open(dest, "rb").read()
    headers = dict(UA)
    if rng:
        headers["Range"] = f"bytes={rng[0]}-{rng[0] + rng[1] - 1}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=180) as r:
        data = r.read()
    if dest:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, "wb").write(data)
    return data


def blte(d):
    if d[:4] != b"BLTE":
        raise ValueError("not a BLTE stream")
    hdr = struct.unpack(">I", d[4:8])[0]
    if hdr == 0:
        blocks = [d[8:]]
    else:
        cnt = int.from_bytes(d[9:12], "big")
        off, sizes = 12, []
        for _ in range(cnt):
            cs, _ = struct.unpack(">II", d[off:off + 8]); off += 24
            sizes.append(cs)
        blocks, pos = [], hdr
        for cs in sizes:
            blocks.append(d[pos:pos + cs]); pos += cs
    out = bytearray()
    for b in blocks:
        m = b[:1]
        if m == b"Z":   out += zlib.decompress(b[1:])
        elif m == b"N": out += b[1:]
        else: raise ValueError(f"unsupported BLTE mode {m!r}")
    return bytes(out)


def parse_config(text):
    cfg = {}
    for line in text.splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().split()
    return cfg


def parse_psv(text):
    rows, cols = [], None
    for line in text.splitlines():
        if not line or line.startswith("##"):
            continue
        parts = line.split("|")
        if cols is None:
            cols = [p.split("!")[0] for p in parts]
        else:
            rows.append(dict(zip(cols, parts)))
    return rows


def parse_tags(text):
    return {t.rstrip("?") for g in text.split(":") for t in g.split()}


def pb_varint(buf, i):
    r = s = 0
    while True:
        b = buf[i]
        r |= (b & 0x7F) << s
        i += 1
        if not b & 0x80:
            return r, i
        s += 7


def pb_fields(buf):
    i = 0
    while i < len(buf):
        try:
            tag, i = pb_varint(buf, i)
            wt = tag & 7
            if wt == 0:
                v, i = pb_varint(buf, i)
            elif wt == 2:
                n, i = pb_varint(buf, i)
                v, i = buf[i:i + n], i + n
                if len(v) < n:
                    return
            elif wt in (1, 5):
                n = 8 if wt == 1 else 4
                v, i = buf[i:i + n], i + n
                if len(v) < n:
                    return
            else:
                return
        except IndexError:
            return
        yield tag >> 3, wt, v


def pb_get(buf, *path):
    for fn in path:
        buf = next((v for f, wt, v in pb_fields(buf) if f == fn and wt == 2), None)
        if buf is None:
            return ""
    return buf.decode("utf-8", "replace")


def product_db(game_dir):
    """Battle.net's own install database, and the only local source for products that
    .build.info no longer lists. It is schemaless protobuf, so pb_fields walks the wire
    format by field number and never raises: a truncated field or an unknown wire type
    ends that message, costing one skipped record rather than the whole tool. Paths into
    a ProductInstall record are 2 product code, 3.1 install path, 3.2 region, 4.1.7
    version, 4.1.12 build config (absent on some products, 4.1.14 carries it then) and
    4.1.17 tags. Battle.net writes the records either as a repeated field 1 or, for a
    single product, as one bare record at the top level, so raw is tried as a record too:
    a repeated-field file has no top-level field 2 and contributes nothing that way."""
    try:
        raw = open(os.path.join(game_dir, ".product.db"), "rb").read()
    except OSError:
        return {}
    out = {}
    for rec in [r for fn, wt, r in pb_fields(raw) if fn == 1 and wt == 2] + [raw]:
        code = pb_get(rec, 2)
        version = pb_get(rec, 4, 1, 7)
        region = pb_get(rec, 3, 2)
        path = pb_get(rec, 3, 1)
        if not (code and version and region):
            continue
        try:
            if path and not os.path.samefile(path, game_dir):
                continue
        except OSError:
            continue
        out[code] = {"region": region, "version": version,
                     "build_config": pb_get(rec, 4, 1, 12) or pb_get(rec, 4, 1, 14),
                     "tags": pb_get(rec, 4, 1, 17)}
    return out


def find_game_dir(override=None):
    for d in ([override] if override else GAME_DIRS):
        if d and any(os.path.exists(os.path.join(d, n))
                     for n in (".build.info", ".product.db")):
            return d
    die("no WoW install found; pass --game-dir")


def flavors(game_dir):
    out = {}
    for name in sorted(os.listdir(game_dir)):
        fi = os.path.join(game_dir, name, ".flavor.info")
        if os.path.exists(fi):
            lines = [l.strip() for l in open(fi).read().splitlines() if l.strip()]
            if len(lines) > 1:
                out[lines[1]] = os.path.join(game_dir, name)
    return out


def branches(game_dir):
    out = {}
    try:
        info = open(os.path.join(game_dir, ".build.info")).read()
    except OSError:
        info = ""
    for r in parse_psv(info):
        if r.get("Active") != "1":
            continue
        out[r["Product"]] = {
            "product": r["Product"],
            "region": r.get("Branch", "us").upper(),
            "version": r.get("Version", ""),
            "build_config": r.get("Build Key", ""),
            "cdn_config": r.get("CDN Key", ""),
            "cdn_path": r.get("CDN Path", "tpr/wow"),
            "hosts": r.get("CDN Hosts", "level3.blizzard.com").split(),
            "tags": parse_tags(r.get("Tags", "")),
        }
    for product, p in product_db(game_dir).items():
        if product in out:
            continue
        out[product] = {
            "product": product,
            "region": p["region"].upper(),
            "version": p["version"],
            "build_config": p["build_config"],
            "cdn_config": "",
            "cdn_path": "",
            "hosts": [],
            "tags": parse_tags(p["tags"]),
        }
    return out


CDN_RESOLVED = {}


def cdn_ready(branch):
    if branch["cdn_path"] and branch["hosts"]:
        return branch
    product, region = branch["product"], branch["region"].lower()
    if not region:
        die(f"{product}: no region recorded for this install")
    if (product, region) not in CDN_RESOLVED:
        base = f"https://{region}.version.battle.net/v2/products/{product}"
        try:
            cdns = parse_psv(http(f"{base}/cdns").decode())
            vers = parse_psv(http(f"{base}/versions").decode())
        except Exception as e:
            die(f"{product}: CDN hosts unknown and {base} is unreachable ({e})")
        usable = [r for r in cdns if r.get("Path") and r.get("Hosts")]
        cdn = next((r for r in usable if r.get("Name") == region),
                   usable[0] if usable else None)
        if not cdn:
            die(f"{product}: {base}/cdns lists no usable CDN for region {region}")
        CDN_RESOLVED[(product, region)] = (cdn, next(
            (r for r in vers if r.get("Region") == region), None))
    cdn, ver = CDN_RESOLVED[(product, region)]
    branch["cdn_path"] = branch["cdn_path"] or cdn["Path"]
    branch["hosts"] = branch["hosts"] or cdn["Hosts"].split()
    if ver and ver.get("VersionsName") == branch["version"]:
        branch["build_config"] = branch["build_config"] or ver.get("BuildConfig", "")
        branch["cdn_config"] = branch["cdn_config"] or ver.get("CDNConfig", "")
    return branch


def cdn_get(branch, key, kind="data", suffix="", dest=None, rng=None):
    cdn_ready(branch)
    last = None
    for host in branch["hosts"]:
        url = f"http://{host}/{branch['cdn_path']}/{kind}/{key[0:2]}/{key[2:4]}/{key}{suffix}"
        try:
            return http(url, dest=dest, rng=rng)
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (403, 404):
                raise
    if last:
        raise last
    die(f"{branch['product']}: no CDN host served {key}")


def parse_install(buf):
    ntags = int.from_bytes(buf[4:6], "big")
    nent = int.from_bytes(buf[6:10], "big")
    pos, mb, tags = 10, (nent + 7) // 8, []
    for _ in range(ntags):
        e = buf.index(b"\0", pos); name = buf[pos:e].decode(); pos = e + 1
        ttype = int.from_bytes(buf[pos:pos + 2], "big"); pos += 2
        tags.append((name, ttype, buf[pos:pos + mb])); pos += mb
    has = lambda m, i: (m[i // 8] >> (7 - (i % 8))) & 1
    entries = []
    for i in range(nent):
        e = buf.index(b"\0", pos); name = buf[pos:e].decode(); pos = e + 1
        ck = buf[pos:pos + 16].hex(); pos += 16
        sz = int.from_bytes(buf[pos:pos + 4], "big"); pos += 4
        entries.append((name, ck, sz, [(n, t) for (n, t, m) in tags if has(m, i)]))
    return entries


def parse_index(d):
    f = d[-28:]
    blk_kb, off_b, size_b, key_b = f[11], f[12], f[13], f[14]
    n = struct.unpack("<I", f[16:20])[0]
    es, bs = key_b + size_b + off_b, blk_kb * 1024
    per, out = bs // es, {}
    for b in range((n + per - 1) // per):
        blk = d[b * bs:(b + 1) * bs]
        for i in range(per):
            e = blk[i * es:(i + 1) * es]
            if len(e) < es or e[:key_b] == b"\0" * key_b:
                break
            q = key_b
            sz = int.from_bytes(e[q:q + size_b], "big"); q += size_b
            off = int.from_bytes(e[q:q + off_b], "big") if off_b else None
            out[e[:key_b].hex()] = (sz, off)
            if len(out) >= n:
                return out
    return out


class Encoding:
    def __init__(self, path):
        self.f = open(path, "rb")
        h = self.f.read(22)
        if h[:2] != b"EN":
            raise ValueError("not an encoding table")
        self.hcs, self.hes = h[3], h[4]
        self.pkb = struct.unpack(">H", h[5:7])[0]
        npages = struct.unpack(">I", h[9:13])[0]
        self.f.seek(22 + struct.unpack(">I", h[18:22])[0])
        tbl = self.f.read(npages * (self.hcs + 16))
        self.pages_off = self.f.tell()
        w = self.hcs + 16
        self.first = [tbl[i * w:i * w + self.hcs] for i in range(npages)]

    def ekey(self, ckey_hex):
        target = bytes.fromhex(ckey_hex)
        idx = bisect.bisect_right(self.first, target) - 1
        if idx < 0:
            return None
        self.f.seek(self.pages_off + idx * self.pkb * 1024)
        page, pos = self.f.read(self.pkb * 1024), 0
        while pos + 6 + self.hcs <= len(page):
            kc = page[pos]
            if kc == 0:
                return None
            q = pos + 6 + self.hcs
            if page[pos + 6:q] == target:
                return page[q:q + self.hes].hex()
            pos = q + kc * self.hes


class Archives:
    def __init__(self, branch, cdn_cfg):
        self.branch, self.map = branch, {}
        names = cdn_cfg["archives"]
        print(f"  indexing {len(names)} archives (one-time, ~110 MB cached)...")

        def fetch(a):
            return a, parse_index(cdn_get(branch, a, suffix=".index",
                                          dest=f"{CACHE}/idx/{a}.index"))
        with ThreadPoolExecutor(max_workers=16) as ex:
            for n, (a, entries) in enumerate(ex.map(fetch, names), 1):
                for k, (sz, off) in entries.items():
                    self.map[k] = (a, off, sz)
                if n % 400 == 0:
                    print(f"    {n}/{len(names)}")

    def get(self, ekey):
        hit = self.map.get(ekey)
        if not hit:
            return None
        a, off, sz = hit
        return cdn_get(self.branch, a, rng=(off, sz))


def wants(entry_tags, selected):
    groups = {}
    for name, ttype in entry_tags:
        groups.setdefault(ttype, []).append(name)
    return all(any(n in selected for n in names)
               for ttype, names in groups.items() if ttype != 16384)


def live_versions(product, region):
    """Blizzard's own version endpoint - authoritative, and ahead of third-party lists."""
    try:
        txt = http(f"https://{region.lower()}.version.battle.net/v2/products/{product}/versions").decode()
        return [{"version": r.get("VersionsName", ""), "build_config": r.get("BuildConfig", ""),
                 "cdn_config": r.get("CDNConfig", ""), "created_at": "(live)",
                 "region": r.get("Region", "")} for r in parse_psv(txt)]
    except Exception:
        return []


def wago_builds(product):
    try:
        rows = json.loads(http("https://wago.tools/api/builds").decode()).get(product, [])
        return [{"version": r.get("version", ""), "build_config": r.get("build_config", ""),
                 "cdn_config": r.get("cdn_config", ""), "created_at": r.get("created_at", "")}
                for r in rows]
    except Exception:
        return []


def known_builds(product, branch):
    """Merge the live build, the installed build, and wago.tools history. The installed
    build keeps its place near the top but borrows any hash the local files did not have,
    and an entry missing either hash is dropped: nothing is listed that cannot be fetched."""
    seen, out = set(), []
    region = branch["region"].lower()
    installed = {"version": branch["version"], "build_config": branch["build_config"],
                 "cdn_config": branch["cdn_config"], "created_at": "(installed)"}
    live = live_versions(product, region)
    mine = [b for b in live if b["region"] == region]
    for b in (mine or live):
        if b["version"] and b["version"] not in seen:
            seen.add(b["version"]); out.append(b)
    if installed["version"] and installed["version"] not in seen:
        seen.add(installed["version"]); out.append(installed)
    for b in wago_builds(product):
        if b["version"] == installed["version"]:
            installed["build_config"] = installed["build_config"] or b["build_config"]
            installed["cdn_config"] = installed["cdn_config"] or b["cdn_config"]
        if b["version"] and b["version"] not in seen:
            seen.add(b["version"]); out.append(b)
    return [b for b in out if b["build_config"] and b["cdn_config"]]


def app_version(app):
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
            return plistlib.load(f).get("CFBundleVersion", "?")
    except Exception:
        return None


def live_app(flavor_dir):
    apps = [p for p in glob.glob(os.path.join(flavor_dir, "*.app"))
            if os.path.exists(os.path.join(p, "Contents", "MacOS"))]
    if len(apps) > 1:
        die(f"{flavor_dir} has more than one app bundle:\n  " + "\n  ".join(apps))
    return apps[0] if apps else None


def lib_dir(product, version):
    return os.path.join(LIB, product, version)


def lib_app(product, version):
    d = lib_dir(product, version)
    if not os.path.isdir(d):
        return None
    apps = glob.glob(os.path.join(d, "*.app"))
    return apps[0] if apps else None


def resolve(args):
    game = find_game_dir(args.game_dir)
    br = branches(game)
    if args.product not in br:
        die(f"product '{args.product}' is not installed here; have: {', '.join(sorted(br))}")
    return game, br[args.product], flavors(game).get(args.product)


def do_fetch(product, version, branch, force=False):
    have = lib_app(product, version)
    if have and not force:
        return have

    entry = next((b for b in known_builds(product, branch) if b["version"] == version), None)
    if not entry:
        die(f"build {version} not found for {product} (try: wowbuild list -p {product})")

    print(f"fetching {product} {version}  [{branch['region']} / "
          f"{' '.join(sorted(branch['tags'] & {'enUS','deDE','frFR','esES','ruRU','koKR','zhCN','zhTW','ptBR','itIT','esMX'}))}]")
    cfg = parse_config(cdn_get(branch, entry["build_config"], "config",
                               dest=f"{CACHE}/{entry['build_config']}").decode())

    selected = set(branch["tags"]) | {"OSX", "arm64", "x86_64", "speech", "text"}
    inst = parse_install(blte(cdn_get(branch, cfg["install"][1],
                                      dest=f"{CACHE}/{cfg['install'][1]}")))
    roots = {e[0].split("\\")[0] for e in inst if e[0].split("\\")[0].endswith(".app")}
    if len(roots) != 1:
        die(f"could not identify the game bundle in this manifest: {sorted(roots)}")
    root = roots.pop()

    files = [e for e in inst if e[0].startswith(root + "\\") and wants(e[3], selected)]
    if not files:
        die("no macOS files matched this build's manifest")
    print(f"  {root} - {len(files)} files, {sum(e[2] for e in files) / 1048576:.1f} MB")

    enc_path = f"{CACHE}/{cfg['encoding'][1]}.bin"
    if not os.path.exists(enc_path):
        print("  downloading encoding table (~180 MB, cached per build)...")
        os.makedirs(CACHE, exist_ok=True)
        open(enc_path, "wb").write(blte(cdn_get(branch, cfg["encoding"][1])))
    enc = Encoding(enc_path)

    cdn_cfg = parse_config(cdn_get(branch, entry["cdn_config"], "config",
                                   dest=f"{CACHE}/{entry['cdn_config']}").decode())
    archives = None
    dest = lib_dir(product, version)
    tmp = dest + ".partial"
    shutil.rmtree(tmp, ignore_errors=True)

    for i, (name, ck, sz, _) in enumerate(sorted(files, key=lambda e: -e[2]), 1):
        rel = name.replace("\\", "/")
        target = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        ek = enc.ekey(ck)
        if not ek:
            die(f"no encoding entry for {rel}")
        try:
            data = blte(cdn_get(branch, ek))
        except urllib.error.HTTPError:
            if archives is None:
                archives = Archives(branch, cdn_cfg)
            raw = archives.get(ek)
            if raw is None:
                die(f"{rel} is neither a loose CDN file nor in any archive")
            data = blte(raw)
        open(target, "wb").write(data)
        if "/MacOS/" in rel or "/Helpers/" in rel:
            os.chmod(target, 0o755)
        print(f"  [{i}/{len(files)}] {sz / 1048576:7.2f} MB  {rel}")

    app = os.path.join(tmp, root)
    if subprocess.run(["codesign", "--verify", "--deep", "--strict", app],
                      capture_output=True).returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        die("code signature did not verify - refusing to keep this build")
    print("  signature: valid (Blizzard Developer ID)")

    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.rename(tmp, dest)
    return os.path.join(dest, root)


def archive_live(product, flavor_dir, branch):
    """Copy whatever is currently installed into the library so revert never needs the CDN."""
    app = live_app(flavor_dir)
    if not app:
        return
    ver = app_version(app)
    if not ver or lib_app(product, ver):
        return
    dest = os.path.join(lib_dir(product, ver), os.path.basename(app))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"archiving current {ver} into the library...")
    subprocess.run(["ditto", app, dest], check=True)


def running_in(flavor_dir):
    out = subprocess.run(["pgrep", "-fl", ".app/Contents/MacOS/"],
                         capture_output=True, text=True).stdout
    root = os.path.abspath(flavor_dir) + os.sep
    return [l for l in out.splitlines() if root in l]


def swap_in(src_app, flavor_dir):
    busy = running_in(flavor_dir)
    if busy:
        die(f"a client from {flavor_dir} is running - quit it first:\n  "
            + "\n  ".join(busy))
    live = live_app(flavor_dir)
    target = os.path.join(flavor_dir, os.path.basename(src_app))
    if live and os.path.abspath(live) != os.path.abspath(target):
        shutil.rmtree(live, ignore_errors=True)
    shutil.rmtree(target, ignore_errors=True)
    subprocess.run(["ditto", src_app, target], check=True)
    subprocess.run(["xattr", "-dr", "com.apple.quarantine", target], capture_output=True)
    return target


def cmd_fetch(args):
    _, branch, _ = resolve(args)
    print("done -> " + do_fetch(args.product, args.version, branch, args.force))


def cmd_install(args):
    _, branch, flavor_dir = resolve(args)
    if not flavor_dir:
        die(f"no game folder for '{args.product}'")
    current = app_version(live_app(flavor_dir) or "")
    if current == args.version and not args.force:
        print(f"{args.version} is already active in {flavor_dir}")
        return
    if not args.yes:
        print(f"  {flavor_dir}")
        print(f"  {current or '(none)'} -> {args.version}")
        if input("  proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            sys.exit("aborted")
    archive_live(args.product, flavor_dir, branch)
    src = do_fetch(args.product, args.version, branch, args.force)
    target = swap_in(src, flavor_dir)
    print(f"\ninstalled {app_version(target)} into {flavor_dir}")
    if args.version != branch["version"]:
        print("\nlaunch it directly - Battle.net's Scan and Repair will put "
              f"{branch['version']} back:")
        print(f'  open "{target}"')


def cmd_revert(args):
    _, branch, flavor_dir = resolve(args)
    if not flavor_dir:
        die(f"no game folder for '{args.product}'")
    version = args.version or branch["version"]
    if not version:
        die("nothing to revert to")
    src = lib_app(args.product, version)
    if not src:
        print(f"{version} is not in the library, fetching it...")
        src = do_fetch(args.product, version, branch)
    target = swap_in(src, flavor_dir)
    print(f"restored {app_version(target)} into {flavor_dir}")


def dir_size(path):
    if not os.path.isdir(path):
        return 0
    return sum(os.path.getsize(os.path.join(r, f))
               for r, _, fs in os.walk(path) for f in fs)


def status_data(args):
    game = find_game_dir(args.game_dir)
    br, fl = branches(game), flavors(game)
    out = {"game_dir": game, "flavors": [], "cache_bytes": dir_size(CACHE),
           "library_bytes": dir_size(LIB)}
    for product, d in sorted(fl.items()):
        app = live_app(d)
        libd = os.path.join(LIB, product)
        out["flavors"].append({
            "product": product,
            "dir": d,
            "folder": os.path.basename(d),
            "expected": br.get(product, {}).get("version") or "",
            "installed": (app_version(app) if app else "") or "",
            "bundle": os.path.basename(app) if app else "",
            "region": br.get(product, {}).get("region", ""),
            "library": sorted(os.listdir(libd)) if os.path.isdir(libd) else [],
            "running": bool(running_in(d)),
        })
    return out


def list_data(args):
    _, branch, _ = resolve(args)
    return {"product": args.product, "region": branch["region"],
            "builds": [{"version": b["version"], "created_at": b["created_at"],
                        "current": b["version"] == branch["version"],
                        "in_library": bool(lib_app(args.product, b["version"]))}
                       for b in known_builds(args.product, branch)[:args.number]]}


def cmd_status(args):
    if getattr(args, "json", False):
        return print(json.dumps(status_data(args)))
    game = find_game_dir(args.game_dir)
    br, fl = branches(game), flavors(game)
    print(game)
    for product, d in sorted(fl.items()):
        app = live_app(d)
        actual = app_version(app) if app else None
        expected = br.get(product, {}).get("version")
        note = ""
        if actual and expected and actual != expected:
            note = "   <- swapped"
        print(f"\n  {os.path.basename(d):<16} [{product}]")
        print(f"    battle.net expects : {expected or '?'}")
        print(f"    installed bundle   : {actual or '(none)'}{note}")
        if app:
            print(f"                         {os.path.basename(app)}")
        have = sorted(os.listdir(os.path.join(LIB, product))) if os.path.isdir(os.path.join(LIB, product)) else []
        if have:
            print(f"    in library         : {', '.join(have)}")
    for label, path in (("cache", CACHE), ("library", LIB)):
        if os.path.isdir(path):
            sz = sum(os.path.getsize(os.path.join(r, f))
                     for r, _, fs in os.walk(path) for f in fs)
            print(f"\n  {label}: {sz / 1073741824:.2f} GB  {path}")


def cmd_list(args):
    if getattr(args, "json", False):
        return print(json.dumps(list_data(args)))
    _, branch, _ = resolve(args)
    print(f"{args.product}  (region {branch['region']})")
    for b in known_builds(args.product, branch)[:args.number]:
        marks = []
        if b["version"] == branch["version"]:
            marks.append("battle.net current")
        if lib_app(args.product, b["version"]):
            marks.append("in library")
        tail = ("   <- " + ", ".join(marks)) if marks else ""
        print(f"  {b['version']:<18} {b['created_at']}{tail}")


def cmd_library(args):
    if not os.path.isdir(LIB):
        return print("library is empty")
    for product in sorted(os.listdir(LIB)):
        for version in sorted(os.listdir(os.path.join(LIB, product))):
            app = lib_app(product, version)
            sz = sum(os.path.getsize(os.path.join(r, f))
                     for r, _, fs in os.walk(lib_dir(product, version)) for f in fs)
            print(f"  {product:<18} {version:<18} {sz / 1048576:6.0f} MB  {os.path.basename(app or '?')}")


def cmd_clean(args):
    shutil.rmtree(CACHE, ignore_errors=True)
    print(f"removed {CACHE}")
    if args.library:
        shutil.rmtree(LIB, ignore_errors=True)
        print(f"removed {LIB}")


def interactive():
    ns = argparse.Namespace(game_dir=None, product="wow", number=12)
    cmd_status(ns)
    print()
    cmd_list(ns)
    v = input("\nversion to install (blank to quit): ").strip()
    if v:
        cmd_install(argparse.Namespace(game_dir=None, product="wow", version=v,
                                       force=False, yes=False))
    input("\npress return to close ")


def main():
    ap = argparse.ArgumentParser(prog="wowbuild",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description=__doc__)
    sub = ap.add_subparsers(dest="cmd")

    def add(name, fn, ver=None):
        p = sub.add_parser(name)
        p.add_argument("--game-dir")
        p.add_argument("-p", "--product", default="wow")
        if ver == "required":
            p.add_argument("version")
        elif ver == "optional":
            p.add_argument("version", nargs="?")
        p.set_defaults(func=fn)
        return p

    add("status", cmd_status).add_argument("--json", action="store_true")
    p = add("list", cmd_list)
    p.add_argument("-n", "--number", type=int, default=20)
    p.add_argument("--json", action="store_true")
    add("fetch", cmd_fetch, "required").add_argument("-f", "--force", action="store_true")
    p = add("install", cmd_install, "required")
    p.add_argument("-f", "--force", action="store_true")
    p.add_argument("-y", "--yes", action="store_true")
    add("revert", cmd_revert, "optional")
    add("library", cmd_library)
    add("clean", cmd_clean).add_argument("--library", action="store_true")

    if len(sys.argv) == 1:
        return interactive()
    args = ap.parse_args()
    if not getattr(args, "func", None):
        return ap.print_help()
    args.func(args)


if __name__ == "__main__":
    main()
