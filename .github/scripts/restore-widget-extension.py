#!/usr/bin/env python3
"""Restore the MusicFreeWidgets Live Activity extension target from the master
branch into the dev-0.6.3 branch of the MusicFree iOS repo.

Upstream dev 0.6.3-beta.1 deleted the whole widget extension, so a build of
dev-0.6.3 produces an app with no MusicFreeWidgets.appex and fails the
"Verify app and Live Activity extension" step. This script transplants the
extension back from master:

  * ios/MusicFree.xcodeproj/project.pbxproj — transplant the 23 extension
    objects (PBXNativeTarget, its 3 build phases, its 2 build configs + config
    list, the 5 PBXBuildFiles, the 7 PBXFileReferences, the PBXGroup, the
    PBXTargetDependency + PBXContainerItemProxy, and the app target's
    "Embed Foundation Extensions" PBXCopyFilesBuildPhase), then wire them
    into the dev project (targets list, Products group, main group, app
    target buildPhases + dependencies). Text-level surgery only: the rest
    of the file is left byte-identical, so the diff shows only additions.
  * package.json — add "react-native-widget-extension": "^0.3.0".
  * yarn.lock — add the widget-extension entry plus the transitive closure
    of lockfile entries it needs (computed from master's lockfile; dev's
    lockfile lacks the whole @expo/config-plugins ~56 tree).
  * ios/Podfile — append master's "target 'MusicFreeWidgets'" block.
  * The 4 missing extension source files (Attributes.swift, Info.plist,
    LyricsLiveActivity.swift, MusicFreeWidgets.entitlements) are restored
    by the caller with `git checkout master -- <paths>` BEFORE running this
    script; the script asserts they exist and aborts otherwise.

Master files are read with `git show master:<path>` (the caller must have
fetched master). For local testing, --master-pbx / --master-podfile /
--master-yarn / --master-package can point at local copies.

Usage:
  python3 restore-widget-extension.py [--repo ROOT] [--dry-run] [--out FILE]
  python3 restore-widget-extension.py --repo testrepo --master-pbx master-pbx.txt \
      --master-podfile master-Podfile --master-yarn master-yarn.lock \
      --master-package master-package.json --dry-run

Exit code 0 on success (all verifications passed), non-zero on any failure.
Only stdlib is used.
"""

import argparse
import json
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# Constants (verified against the real repo 2026-11-26)
# ---------------------------------------------------------------------------

EXT_TARGET_NAME = "MusicFreeWidgets"
APP_TARGET_NAME = "MusicFree"
EXT_FILES = [
    "Attributes.swift",
    "Info.plist",
    "LyricsLiveActivity.swift",
    "MusicFreeWidgets.entitlements",
]
WIDGET_PKG = "react-native-widget-extension"

# The 23 pbxproj objects that belong to the extension, derived from master
# and asserted by the script (aborts if the derivation disagrees).
EXPECTED_UUIDS = {
    "471244459E820CCB8E65DCFF",  # PBXNativeTarget MusicFreeWidgets
    "DD57E1D2EF2FBD38B4590572",  # XCConfigurationList (extension target)
    "F84F9C1D9B48E9A9C4BAC96B",  # XCBuildConfiguration Debug (extension)
    "B1FD25EFF2842C24A0898028",  # XCBuildConfiguration Release (extension)
    "91AEBC4DA6478B06070EB6CD",  # PBXSourcesBuildPhase (extension)
    "BC5272F032E8B3C150EF5944",  # PBXFrameworksBuildPhase (extension)
    "2C1513E01950608659D1869D",  # PBXResourcesBuildPhase (extension)
    "B6470F3532D0D441904088D5",  # PBXCopyFilesBuildPhase "Embed Foundation Extensions"
    "70CA75E5F93A26A007B9CB25",  # PBXBuildFile Attributes.swift in Sources
    "507D93FFB55B67EF63DF05AD",  # PBXBuildFile LyricsLiveActivity.swift in Sources
    "257F849B17C615900F1B3FBE",  # PBXBuildFile WidgetKit.framework in Frameworks
    "5E92A867DAC4726476940DC4",  # PBXBuildFile SwiftUI.framework in Frameworks
    "F6285BB940F8458733D55EC8",  # PBXBuildFile MusicFreeWidgets.appex in Embed
    "6D63F87ABFBD56DC48AD8980",  # PBXFileReference MusicFreeWidgets.appex
    "3E2C272D652AFE779C308AB2",  # PBXFileReference Attributes.swift
    "619BB34F28A92E63EC73C0D8",  # PBXFileReference LyricsLiveActivity.swift
    "5860D3A96E47ED1301E06E95",  # PBXFileReference Info.plist
    "2116570C8A44DB6B7F73E39A",  # PBXFileReference MusicFreeWidgets.entitlements
    "A2AB8534423A167F807F1AAA",  # PBXFileReference WidgetKit.framework
    "A9E22CBB0E0AA97F1E3F32E4",  # PBXFileReference SwiftUI.framework
    "4D6D4470E8ACD2B454884C37",  # PBXGroup MusicFreeWidgets
    "0B8D08998BB8F6C8AB4ACE01",  # PBXTargetDependency (app -> extension)
    "0D8D78B13D0332C402843D93",  # PBXContainerItemProxy (for the dependency)
}

# Canonical Xcode section order (alphabetical); used when a section must be
# created (dev has no PBXCopyFilesBuildPhase section at all).
SECTION_ORDER = [
    "PBXAggregateTarget", "PBXBuildFile", "PBXContainerItemProxy",
    "PBXCopyFilesBuildPhase", "PBXFileReference", "PBXFrameworksBuildPhase",
    "PBXGroup", "PBXNativeTarget", "PBXProject", "PBXResourcesBuildPhase",
    "PBXShellScriptBuildPhase", "PBXSourcesBuildPhase", "PBXTargetDependency",
    "XCBuildConfiguration", "XCConfigurationList", "XCVersionGroup",
]

UUID_RE = re.compile(r"^[0-9A-F]{24}$")


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# OpenStep plist (pbxproj) parser — tokenizer + recursive descent
# ---------------------------------------------------------------------------

class Tok:
    def __init__(self, kind, val):
        self.kind = kind
        self.val = val

    def __repr__(self):
        return f"Tok({self.kind},{self.val!r})"


def tokenize(s):
    toks = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            j = s.find("*/", i + 2)
            if j < 0:
                raise ValueError("unterminated comment")
            i = j + 2
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            j = s.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c in "{}()=;,":
            toks.append(Tok(c, c))
            i += 1
            continue
        if c == '"':
            j = i + 1
            out = []
            while j < n:
                if s[j] == "\\" and j + 1 < n:
                    out.append(s[j + 1])
                    j += 2
                    continue
                if s[j] == '"':
                    break
                out.append(s[j])
                j += 1
            toks.append(Tok("str", "".join(out)))
            i = j + 1
            continue
        # bare word (may contain '/' as in paths; stop before '/*' comments)
        j = i
        while j < n and s[j] not in ' \t\r\n{}()=;,"':
            if s[j] == "/" and j + 1 < n and s[j + 1] == "*":
                break
            j += 1
        toks.append(Tok("str", s[i:j]))
        i = j
    return toks


class Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, kind):
        t = self.next()
        assert t.kind == kind, f"expected {kind}, got {t}"
        return t

    def parse_value(self):
        t = self.peek()
        if t.kind == "{":
            return self.parse_dict()
        if t.kind == "(":
            return self.parse_array()
        if t.kind == "str":
            self.next()
            return t.val
        raise ValueError(f"unexpected token {t}")

    def parse_dict(self):
        self.expect("{")
        d = {}
        while self.peek() and self.peek().kind != "}":
            k = self.expect("str").val
            self.expect("=")
            d[k] = self.parse_value()
            self.expect(";")
        self.expect("}")
        return d

    def parse_array(self):
        self.expect("(")
        a = []
        while self.peek() and self.peek().kind != ")":
            a.append(self.parse_value())
            if self.peek() and self.peek().kind == ",":
                self.next()
        self.expect(")")
        return a


def parse_pbxproj_text(text):
    return Parser(tokenize(text)).parse_dict()


def find_refs(v, acc=None):
    acc = set() if acc is None else acc
    if isinstance(v, str):
        if UUID_RE.match(v):
            acc.add(v)
    elif isinstance(v, list):
        for x in v:
            find_refs(x, acc)
    elif isinstance(v, dict):
        for x in v.values():
            find_refs(x, acc)
    return acc


# ---------------------------------------------------------------------------
# pbxproj text surgery (line based; the file is left byte-identical except
# for the inserted lines)
# ---------------------------------------------------------------------------

OBJ_START_RE = re.compile(r"^(\t\t)([0-9A-F]{24})\s+/\*.*?\*/\s*=\s*\{")
OBJ_START_NOCOMMENT_RE = re.compile(r"^(\t\t)([0-9A-F]{24})\s*=\s*\{")


def find_object_span(lines, uuid):
    """Return (start, end) line indices (inclusive) of the object with uuid.
    Objects are at 2-tab indent; single-line objects end with '};' on the
    same line, multi-line ones end at a line that is exactly '\\t\\t};'."""
    for i, line in enumerate(lines):
        m = OBJ_START_RE.match(line) or OBJ_START_NOCOMMENT_RE.match(line)
        if m and m.group(2) == uuid:
            if line.rstrip().endswith("};"):
                return (i, i)
            for j in range(i + 1, len(lines)):
                if lines[j].rstrip("\n") == "\t\t};":
                    return (i, j)
            fail(f"object {uuid}: no closing '\\t\\t}};' found")
    fail(f"object {uuid} not found in pbxproj text")


def extract_object_raw(lines, uuid):
    s, e = find_object_span(lines, uuid)
    return "".join(lines[s:e + 1])


def object_comment(lines, uuid):
    """The /* comment */ after the UUID on the object's start line."""
    s, _ = find_object_span(lines, uuid)
    m = re.search(r"/\*(.*?)\*/", lines[s])
    return m.group(1).strip() if m else ""


def insert_object_into_section(lines, isa, raw_text):
    """Insert a raw object into its /* Begin <isa> section */ block, just
    before the /* End <isa> section */ line. Creates the section (in
    canonical alphabetical position) if it does not exist."""
    begin = f"/* Begin {isa} section */"
    end = f"/* End {isa} section */"
    end_idx = None
    for i, line in enumerate(lines):
        if line.strip() == end:
            end_idx = i
            break
    if end_idx is not None:
        block = raw_text if raw_text.endswith("\n") else raw_text + "\n"
        lines[end_idx:end_idx] = [block]
        return
    # Section missing: create it after the section that precedes it
    # alphabetically (Xcode's canonical order).
    pos = SECTION_ORDER.index(isa) if isa in SECTION_ORDER else len(SECTION_ORDER)
    insert_at = None
    for i, line in enumerate(lines):
        m = re.match(r"/\* Begin (\w+) section \*/", line.strip())
        if m and SECTION_ORDER.index(m.group(1)) > pos:
            insert_at = i
            break
    if insert_at is None:
        fail(f"cannot place new section {isa}: no later section found")
    # The line before insert_at should be blank; keep the layout
    # "...\n\n/* Begin ... */".
    new_block = [f"/* Begin {isa} section */\n", raw_text if raw_text.endswith("\n") else raw_text + "\n",
                 f"/* End {isa} section */\n", "\n"]
    lines[insert_at:insert_at] = new_block


def insert_into_array(lines, obj_uuid, key, entry, index=None):
    """Insert `entry` (a full line without trailing newline) into the
    `key = ( ... );` array of the object obj_uuid. Appends at the end
    unless index is given (0-based among existing items)."""
    s, e = find_object_span(lines, obj_uuid)
    key_re = re.compile(r"^(\t\t\t)" + re.escape(key) + r" = \($")
    key_idx = None
    for i in range(s, e + 1):
        if key_re.match(lines[i]):
            key_idx = i
            break
    if key_idx is None:
        fail(f"object {obj_uuid}: array '{key}' not found")
    close_idx = None
    for j in range(key_idx + 1, e + 1):
        if lines[j].rstrip("\n") == "\t\t\t);":
            close_idx = j
            break
    if close_idx is None:
        fail(f"object {obj_uuid}: closing of array '{key}' not found")
    items = [k for k in range(key_idx + 1, close_idx)
             if re.match(r"^\t\t\t\t[0-9A-F]{24} ", lines[k])]
    if index is None:
        at = close_idx
    else:
        at = close_idx if index >= len(items) else items[index]
    lines[at:at] = [entry + "\n"]


# ---------------------------------------------------------------------------
# yarn.lock helpers
# ---------------------------------------------------------------------------

def parse_lock_text(text):
    """Return (entries, order): entries maps each individual key string to
    {'version': str, 'deps': {name: range}, 'raw': block_text}."""
    entries = {}
    order = []
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("#"):
            # yarn.lock header comment ("# THIS IS AN AUTOGENERATED FILE...")
            i += 1
            continue
        if line[0] in " \t":
            i += 1
            continue
        # entry header line, ends with ':'
        hdr = line.rstrip("\n").rstrip(":")
        parts = re.findall(r'"([^"]+)"|([^",\s]+)', hdr)
        keys = [a or b for a, b in parts]
        start = i
        i += 1
        version = None
        deps = {}
        while i < len(lines) and (not lines[i].strip() or lines[i][0] in " \t"):
            m = re.match(r'\s+version "([^"]+)"', lines[i])
            if m:
                version = m.group(1)
            if re.match(r"\s+dependencies:", lines[i]):
                i += 1
                while i < len(lines) and re.match(r'\s{4,}"?[^"\s]', lines[i]):
                    dm = re.match(r'\s+"?([^"\s]+)"?\s+"([^"]+)"', lines[i])
                    if dm:
                        deps[dm.group(1)] = dm.group(2)
                    i += 1
                continue
            i += 1
        # block ends at first blank line; keep raw block without trailing blanks
        end = i
        while end > start and not lines[end - 1].strip():
            end -= 1
        raw = "".join(lines[start:end])
        header = lines[start].rstrip("\n").rstrip(":")
        for k in keys:
            entries[k] = {"version": version, "deps": deps, "raw": raw,
                          "keys": list(keys), "header": header}
            order.append(k)
    return entries, order


def pkg_of_key(key):
    if key.startswith("@"):
        idx = key.rfind("@")
        return key[:idx], key[idx + 1:]
    idx = key.rfind("@")
    return key[:idx], key[idx + 1:]


def _semver_tuple(s):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", s)
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def satisfies(version, rng):
    """Minimal semver range check. Returns True/False; raises ValueError
    for ranges it cannot interpret (fail loudly, never silently pass)."""
    rng = rng.strip()
    if rng in ("*", "latest", ""):
        return True
    # OR groups
    if "||" in rng:
        return any(satisfies(version, part) for part in rng.split("||"))
    v = _semver_tuple(version)
    if v is None:
        raise ValueError(f"cannot parse version {version!r}")
    if rng.startswith("^"):
        b = _semver_tuple(rng[1:])
        if b is None:
            raise ValueError(f"cannot parse range {rng!r}")
        if b[0] > 0:
            return v[0] == b[0] and v >= b
        if b[1] > 0:
            return v[0] == 0 and v[1] == b[1] and v >= b
        return v == b
    if rng.startswith("~"):
        b = _semver_tuple(rng[1:])
        if b is None:
            raise ValueError(f"cannot parse range {rng!r}")
        return v[0] == b[0] and v[1] == b[1] and v >= b
    m = re.match(r"^(>=|<=|>|<|=)?\s*(.+)$", rng)
    if m and m.group(1):
        op, base = m.group(1), m.group(2)
        b = _semver_tuple(base)
        if b is None:
            raise ValueError(f"cannot parse range {rng!r}")
        return {">=": v >= b, "<=": v <= b, ">": v > b, "<": v < b, "=": v == b}[op]
    if re.match(r"^\d+\.(\d+|[xX\*])\.(\d+|[xX\*])$", rng) or re.match(r"^\d+\.[xX\*]$", rng):
        # wildcard: 1.x, 1.2.x
        parts = rng.split(".")
        for idx, part in enumerate(parts):
            if part in ("x", "X", "*"):
                return True
            if v[idx] != int(part):
                return False
        return True
    b = _semver_tuple(rng)
    if b is not None:
        return v == b
    raise ValueError(f"cannot parse range {rng!r}")


def lock_satisfies(entries, pkg, rng):
    """True if the lockfile has an entry for pkg whose version satisfies rng."""
    for k, e in entries.items():
        p, _r = pkg_of_key(k)
        if p == pkg and e["version"]:
            try:
                if satisfies(e["version"], rng):
                    return True
            except ValueError:
                continue
    return False


def lock_entry_for(entries, pkg, rng):
    """First master entry (key, entry) for pkg whose version satisfies rng."""
    for k, e in entries.items():
        p, _r = pkg_of_key(k)
        if p == pkg and e["version"]:
            try:
                if satisfies(e["version"], rng):
                    return k, e
            except ValueError:
                continue
    return None, None


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------

def git_show(repo, ref, path):
    r = subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        fail(f"git show {ref}:{path} failed: {r.stderr.strip()}")
    return r.stdout


# ---------------------------------------------------------------------------
# Main restore
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=".", help="repo root (default: .)")
    ap.add_argument("--master-ref", default="master")
    ap.add_argument("--master-pbx", help="local master project.pbxproj (overrides git show)")
    ap.add_argument("--master-podfile", help="local master ios/Podfile (overrides git show)")
    ap.add_argument("--master-yarn", help="local master yarn.lock (overrides git show)")
    ap.add_argument("--master-package", help="local master package.json (overrides git show)")
    ap.add_argument("--dry-run", action="store_true",
                    help="do not write files; print what would change")
    ap.add_argument("--out", help="dry-run pbxproj output path (default: no file)")
    args = ap.parse_args()
    repo = args.repo

    import os
    pbx_path = os.path.join(repo, "ios", "MusicFree.xcodeproj", "project.pbxproj")
    pkg_path = os.path.join(repo, "package.json")
    lock_path = os.path.join(repo, "yarn.lock")
    pod_path = os.path.join(repo, "ios", "Podfile")
    widgets_dir = os.path.join(repo, "ios", "MusicFreeWidgets")

    # 0. The 4 extension source files must already be restored (the caller
    #    runs `git checkout master -- <paths>` first).
    missing_files = [f for f in EXT_FILES
                     if not os.path.isfile(os.path.join(widgets_dir, f))]
    if missing_files:
        fail("missing extension files in ios/MusicFreeWidgets/: "
             + ", ".join(missing_files)
             + " — restore them first with "
             + "git checkout master -- " + " ".join(
                 "ios/MusicFreeWidgets/" + f for f in EXT_FILES))

    # Load master + dev files.
    if args.master_pbx:
        master_pbx_text = open(args.master_pbx, encoding="utf-8").read()
    else:
        master_pbx_text = git_show(repo, args.master_ref,
                                   "ios/MusicFree.xcodeproj/project.pbxproj")
    if args.master_podfile:
        master_pod_text = open(args.master_podfile, encoding="utf-8").read()
    else:
        master_pod_text = git_show(repo, args.master_ref, "ios/Podfile")
    if args.master_yarn:
        master_lock_text = open(args.master_yarn, encoding="utf-8").read()
    else:
        master_lock_text = git_show(repo, args.master_ref, "yarn.lock")
    if args.master_package:
        master_pkg = json.loads(open(args.master_package, encoding="utf-8").read())
    else:
        master_pkg = json.loads(git_show(repo, args.master_ref, "package.json"))

    dev_pbx_text = open(pbx_path, encoding="utf-8").read()
    dev_pkg_text = open(pkg_path, encoding="utf-8").read()
    dev_lock_text = open(lock_path, encoding="utf-8").read()
    dev_pod_text = open(pod_path, encoding="utf-8").read()

    # ------------------------------------------------------------------
    # 1. Derive the pbxproj transplant set from master.
    # ------------------------------------------------------------------
    mtop = parse_pbxproj_text(master_pbx_text)
    dtop = parse_pbxproj_text(dev_pbx_text)
    mo, do = mtop["objects"], dtop["objects"]

    def find_target(objs, name):
        for u, o in objs.items():
            if o.get("isa") == "PBXNativeTarget" and o.get("name") == name:
                return u, o
        return None, None

    ext_uuid, ext_target = find_target(mo, EXT_TARGET_NAME)
    if not ext_uuid:
        fail(f"master has no PBXNativeTarget named {EXT_TARGET_NAME}")
    app_uuid_m, app_target_m = find_target(mo, APP_TARGET_NAME)
    app_uuid_d, app_target_d = find_target(do, APP_TARGET_NAME)
    if not app_uuid_m or not app_uuid_d:
        fail("app target not found in master or dev pbxproj")
    if app_uuid_m != app_uuid_d:
        print(f"NOTE: app target UUID differs master={app_uuid_m} dev={app_uuid_d}; "
              "using dev's for wiring")

    # Follow ONLY the extension target's own references.
    transplant = set()
    work = [ext_uuid]
    while work:
        u = work.pop()
        if u in transplant or u not in mo:
            continue
        transplant.add(u)
        o = mo[u]
        if o.get("isa") == "PBXNativeTarget" and o.get("name") == EXT_TARGET_NAME:
            for k in ("buildConfigurationList", "productReference"):
                if o.get(k):
                    work.append(o[k])
            work.extend(o.get("buildPhases", []))
            work.extend(o.get("dependencies", []))
        elif o.get("isa") == "XCConfigurationList":
            work.extend(o.get("buildConfigurations", []))
        elif o.get("isa") in ("PBXSourcesBuildPhase", "PBXFrameworksBuildPhase",
                              "PBXResourcesBuildPhase", "PBXCopyFilesBuildPhase"):
            for bf in o.get("files", []):
                work.append(bf)
        elif o.get("isa") == "PBXBuildFile":
            if o.get("fileRef"):
                work.append(o["fileRef"])
        elif o.get("isa") == "PBXTargetDependency":
            if o.get("targetProxy"):
                work.append(o["targetProxy"])

    # The extension's PBXGroup + its children file refs.
    group_uuid = None
    for u, o in mo.items():
        if o.get("isa") == "PBXGroup" and o.get("name") == EXT_TARGET_NAME:
            group_uuid = u
            break
    if not group_uuid:
        fail(f"master has no PBXGroup named {EXT_TARGET_NAME}")
    transplant.add(group_uuid)
    for child in mo[group_uuid].get("children", []):
        transplant.add(child)

    # The app target's "Embed Foundation Extensions" phase + the dependency
    # on the extension target (both live in master, both are missing in dev).
    embed_phase = None
    for ph in app_target_m.get("buildPhases", []):
        if mo.get(ph, {}).get("isa") == "PBXCopyFilesBuildPhase" and \
                mo[ph].get("name") == "Embed Foundation Extensions":
            embed_phase = ph
            break
    if not embed_phase:
        fail("master app target has no 'Embed Foundation Extensions' phase")
    transplant.add(embed_phase)
    for bf in mo[embed_phase].get("files", []):
        transplant.add(bf)
        if mo.get(bf, {}).get("fileRef"):
            transplant.add(mo[bf]["fileRef"])
    dep_uuid = None
    for dep in app_target_m.get("dependencies", []):
        if mo.get(dep, {}).get("target") == ext_uuid:
            dep_uuid = dep
            break
    if not dep_uuid:
        fail("master app target has no dependency on the extension target")
    transplant.add(dep_uuid)
    if mo[dep_uuid].get("targetProxy"):
        transplant.add(mo[dep_uuid]["targetProxy"])

    # Sanity: the derived set must be exactly the 23 verified objects.
    if transplant != EXPECTED_UUIDS:
        print("DERIVED SET:", sorted(transplant), file=sys.stderr)
        print("EXPECTED SET:", sorted(EXPECTED_UUIDS), file=sys.stderr)
        print("EXTRA:", sorted(transplant - EXPECTED_UUIDS), file=sys.stderr)
        print("MISSING:", sorted(EXPECTED_UUIDS - transplant), file=sys.stderr)
        fail("derived transplant set differs from the verified 23 objects; "
             "master must have changed — aborting, do not push a partial fix")

    # Collision check: none of the transplanted UUIDs may exist in dev.
    collisions = sorted(transplant & set(do))
    if collisions:
        fail(f"UUID collision with dev pbxproj: {collisions}")

    print(f"pbxproj: transplanting {len(transplant)} objects "
          f"(target {ext_uuid}, group {group_uuid}, embed phase {embed_phase})")

    # ------------------------------------------------------------------
    # 2. Text surgery on the dev pbxproj.
    # ------------------------------------------------------------------
    master_lines = master_pbx_text.splitlines(keepends=True)
    dev_lines = dev_pbx_text.splitlines(keepends=True)

    # Insert each transplanted object into its section (verbatim from master).
    for uuid in sorted(transplant):
        isa = mo[uuid]["isa"]
        raw = extract_object_raw(master_lines, uuid)
        insert_object_into_section(dev_lines, isa, raw)

    # Wiring edits on dev's existing objects.
    def entry_line(uuid, comment):
        return f"\t\t\t\t{uuid} /* {comment} */,"

    # (a) PBXProject targets += extension target.
    proj_uuid = dtop["rootObject"]
    insert_into_array(dev_lines, proj_uuid, "targets",
                      entry_line(ext_uuid, object_comment(master_lines, ext_uuid) or EXT_TARGET_NAME))
    # (b) Products group children += appex product ref.
    prod_uuid = None
    for u, o in do.items():
        if o.get("isa") == "PBXGroup" and o.get("name") == "Products":
            prod_uuid = u
            break
    if not prod_uuid:
        fail("dev has no Products group")
    appex_uuid = ext_target["productReference"]
    insert_into_array(dev_lines, prod_uuid, "children",
                      entry_line(appex_uuid, object_comment(master_lines, appex_uuid)))
    # (c) mainGroup children += extension group, at index 1 (mirrors master,
    #     where it is the 2nd child, right after the MusicFree group).
    main_group = do[proj_uuid]["mainGroup"]
    insert_into_array(dev_lines, main_group, "children",
                      entry_line(group_uuid, object_comment(master_lines, group_uuid) or EXT_TARGET_NAME),
                      index=1)
    # (d) app target: buildPhases += embed phase (appended last, as in master).
    insert_into_array(dev_lines, app_uuid_d, "buildPhases",
                      entry_line(embed_phase, object_comment(master_lines, embed_phase)))
    # (e) app target: dependencies += target dependency.
    insert_into_array(dev_lines, app_uuid_d, "dependencies",
                      entry_line(dep_uuid, object_comment(master_lines, dep_uuid)))

    new_pbx_text = "".join(dev_lines)

    # Verify the new pbxproj.
    ntop = parse_pbxproj_text(new_pbx_text)
    nobj = ntop["objects"]
    all_refs = find_refs(ntop)
    dangling = sorted(r for r in all_refs if r not in nobj)
    if dangling:
        fail(f"new pbxproj has dangling UUID references: {dangling}")
    for label, u in (("extension target", ext_uuid),
                     ("embed phase", embed_phase),
                     ("appex product", appex_uuid),
                     ("extension group", group_uuid)):
        if u not in nobj:
            fail(f"new pbxproj is missing {label} {u}")
    napp = nobj[app_uuid_d]
    if embed_phase not in napp.get("buildPhases", []):
        fail("app target buildPhases does not include the embed phase")
    if dep_uuid not in napp.get("dependencies", []):
        fail("app target dependencies does not include the extension dependency")
    if ext_uuid not in nobj[proj_uuid].get("targets", []):
        fail("project targets does not include the extension target")
    if appex_uuid not in nobj[prod_uuid].get("children", []):
        fail("Products group does not include the appex")
    print("pbxproj verification passed: parses, no dangling refs, "
          "extension target + embed phase + wiring all present")

    # ------------------------------------------------------------------
    # 3. package.json: add the widget-extension dependency.
    # ------------------------------------------------------------------
    dev_pkg = json.loads(dev_pkg_text)
    if WIDGET_PKG in dev_pkg.get("dependencies", {}):
        print(f"package.json already lists {WIDGET_PKG}; skipping")
        new_pkg_text = dev_pkg_text
    else:
        spec = master_pkg.get("dependencies", {}).get(WIDGET_PKG)
        if not spec:
            fail(f"master package.json has no {WIDGET_PKG} dependency")
        pkg_lines = dev_pkg_text.splitlines(keepends=True)
        anchor = None
        in_deps = False
        for i, line in enumerate(pkg_lines):
            if re.match(r'^  "dependencies": \{$', line):
                in_deps = True
            if in_deps and re.search(r'"react-native-webview":', line):
                anchor = i
                break
        if anchor is None:
            fail("package.json: 'react-native-webview' line not found in dependencies")
        indent = re.match(r"^(\s*)", pkg_lines[anchor]).group(1)
        pkg_lines[anchor + 1:anchor + 1] = [
            f'{indent}"{WIDGET_PKG}": "{spec}",\n']
        new_pkg_text = "".join(pkg_lines)
        json.loads(new_pkg_text)  # must still parse
        if json.loads(new_pkg_text)["dependencies"].get(WIDGET_PKG) != spec:
            fail("package.json edit did not take effect")
        print(f"package.json: added \"{WIDGET_PKG}\": \"{spec}\"")

    # ------------------------------------------------------------------
    # 4. yarn.lock: add the widget-extension entry + transitive closure.
    # ------------------------------------------------------------------
    master_entries, _ = parse_lock_text(master_lock_text)
    dev_entries, _ = parse_lock_text(dev_lock_text)
    spec = master_pkg.get("dependencies", {}).get(WIDGET_PKG)
    todo = [(WIDGET_PKG, spec)]
    needed = {}   # (pkg, range) -> master key
    seen = set()
    while todo:
        pkg, rng = todo.pop()
        if (pkg, rng) in seen:
            continue
        seen.add((pkg, rng))
        if lock_satisfies(dev_entries, pkg, rng):
            continue
        key, entry = lock_entry_for(master_entries, pkg, rng)
        if entry is None:
            fail(f"no master lockfile entry satisfies {pkg} {rng}")
        needed[(pkg, rng)] = key
        for dp, dr in entry["deps"].items():
            todo.append((dp, dr))
    print(f"yarn.lock: transplanting {len(needed)} entries: "
          + ", ".join(sorted(k for _, k in needed.items())))

    lock_lines = dev_lock_text.splitlines(keepends=True)
    # Build the list of existing entry key lines (start of each entry block).
    def entry_key_lines(lines):
        out = []
        for i, line in enumerate(lines):
            if line and line[0] not in " \t" and line.rstrip("\n").endswith(":") \
                    and line.strip():
                out.append((i, line.rstrip("\n").rstrip(":")))
        return out

    def find_block_span(lines, header_key):
        """(start, end) line indices of the lockfile entry block whose header
        line is exactly `header_key:` (header_key is the raw key text)."""
        for i, line in enumerate(lines):
            if line.rstrip("\n") == header_key + ":":
                j = i + 1
                while j < len(lines) and (not lines[j].strip() or lines[j][0] in " \t"):
                    j += 1
                end = j
                while end > i + 1 and not lines[end - 1].strip():
                    end -= 1
                return (i, end)
        return None

    for (pkg, rng), key in sorted(needed.items(), key=lambda kv: kv[1]):
        raw = master_entries[key]["raw"]
        if not raw.endswith("\n"):
            raw += "\n"
        if key in dev_entries:
            # The entry key already exists in dev's lockfile. This happens
            # when yarn merged a new range into an existing multi-key entry
            # (e.g. minipass@^7.1.3 appended to the ^5/^6/^7 entry) and
            # bumped the version. Merge: replace dev's block with master's,
            # but only if master's key set is a superset of dev's (so no
            # existing dependent loses its range) and master's version
            # satisfies every range dev's entry served.
            dev_entry = dev_entries[key]
            if dev_entry["version"] and satisfies(dev_entry["version"], rng):
                print(f"yarn.lock: {key} already satisfied; skipping")
                continue
            master_keys = set(master_entries[key].get("keys", [key]))
            dev_keys = set(dev_entry.get("keys", [key]))
            if not master_keys >= dev_keys:
                fail(f"yarn.lock: cannot merge {key}: master's key set "
                     f"{sorted(master_keys)} is not a superset of dev's "
                     f"{sorted(dev_keys)}")
            for dk in dev_keys:
                _p, dr = pkg_of_key(dk)
                if not satisfies(master_entries[key]["version"], dr):
                    fail(f"yarn.lock: master's version "
                         f"{master_entries[key]['version']} does not satisfy "
                         f"existing dev range {dk}")
            span = find_block_span(lock_lines, dev_entry["header"])
            if span is None:
                fail(f"yarn.lock: cannot locate block for {key}")
            s, e = span
            lock_lines[s:e] = [raw + "\n"]
            print(f"yarn.lock: merged {key} (version "
                  f"{dev_entry['version']} -> {master_entries[key]['version']})")
            dev_entries, _ = parse_lock_text("".join(lock_lines))
            continue
        # Insert before the first existing entry whose key sorts after this one.
        keys_now = entry_key_lines(lock_lines)
        at = len(lock_lines)
        for idx, kline in keys_now:
            if kline > key:
                at = idx
                break
        # Keep one blank line between entries.
        block = [raw + "\n"]
        if at < len(lock_lines) and lock_lines[at - 1].strip():
            block = ["\n"] + block
        lock_lines[at:at] = block
        dev_entries, _ = parse_lock_text("".join(lock_lines))
    new_lock_text = "".join(lock_lines)

    # Verify the lockfile now satisfies every required range: all of dev
    # package.json's deps/devDeps plus the whole widget-extension tree.
    final_entries, _ = parse_lock_text(new_lock_text)
    required = []
    for section in ("dependencies", "devDependencies"):
        for pkg, rng in dev_pkg.get(section, {}).items():
            required.append((pkg, rng))
    required.append((WIDGET_PKG, spec))
    # Re-walk the widget tree against the final lockfile.
    todo = [(WIDGET_PKG, spec)]
    seen = set()
    while todo:
        pkg, rng = todo.pop()
        if (pkg, rng) in seen:
            continue
        seen.add((pkg, rng))
        key, entry = lock_entry_for(final_entries, pkg, rng)
        if entry is None:
            fail(f"yarn.lock verification: no entry satisfies {pkg} {rng}")
        for dp, dr in entry["deps"].items():
            todo.append((dp, dr))
    for pkg, rng in required:
        if not lock_satisfies(final_entries, pkg, rng):
            fail(f"yarn.lock verification: {pkg} {rng} still unsatisfied")
    print("yarn.lock verification passed: every required range resolves")

    # ------------------------------------------------------------------
    # 5. Podfile: append master's MusicFreeWidgets target block.
    # ------------------------------------------------------------------
    if "MusicFreeWidgets" in dev_pod_text:
        print("Podfile already mentions MusicFreeWidgets; skipping")
        new_pod_text = dev_pod_text
    else:
        mlines = master_pod_text.splitlines()
        tgt = next((i for i, l in enumerate(mlines)
                    if l == "target 'MusicFreeWidgets' do"), None)
        if tgt is None:
            fail("master Podfile has no target 'MusicFreeWidgets' block")
        start = tgt
        while start > 0 and mlines[start - 1].startswith("#"):
            start -= 1
        end = next((i for i in range(tgt + 1, len(mlines)) if mlines[i] == "end"), None)
        if end is None:
            fail("master Podfile: target block has no closing 'end'")
        block_lines = mlines[start:end + 1]
        j = end + 1
        while j < len(mlines) and not mlines[j].strip():
            j += 1
        if j < len(mlines) and mlines[j].startswith("# >>> Inserted"):
            block_lines.append(mlines[j])
        block = "\n".join(block_lines)
        if "target 'MusicFreeWidgets' do" not in block or \
                block.count("use_frameworks!") != 2:
            fail("extracted Podfile block does not look like the widget target")
        new_pod_text = dev_pod_text
        if not new_pod_text.endswith("\n"):
            new_pod_text += "\n"
        new_pod_text += "\n" + block + "\n"
        print("Podfile: appended the MusicFreeWidgets target block")

    # ------------------------------------------------------------------
    # 6. Write (or report in dry-run mode).
    # ------------------------------------------------------------------
    def diff_stat(old, new):
        import difflib
        sm = difflib.SequenceMatcher(None, old.splitlines(), new.splitlines())
        add = sum(j2 - j1 for tag, _i1, _i2, j1, j2 in sm.get_opcodes()
                  if tag in ("insert", "replace"))
        dele = sum(i2 - i1 for tag, i1, i2, _j1, _j2 in sm.get_opcodes()
                   if tag in ("delete", "replace"))
        return add, dele

    stats = []
    for label, old, new in (("project.pbxproj", dev_pbx_text, new_pbx_text),
                            ("package.json", dev_pkg_text, new_pkg_text),
                            ("yarn.lock", dev_lock_text, new_lock_text),
                            ("ios/Podfile", dev_pod_text, new_pod_text)):
        a, d = diff_stat(old, new)
        stats.append((label, a, d))
        print(f"  {label}: +{a} lines / -{d} lines")
    if args.dry_run:
        print("DRY RUN: no files written")
        if args.out:
            open(args.out, "w", encoding="utf-8").write(new_pbx_text)
            print(f"dry-run pbxproj written to {args.out}")
        return 0
    open(pbx_path, "w", encoding="utf-8").write(new_pbx_text)
    open(pkg_path, "w", encoding="utf-8").write(new_pkg_text)
    open(lock_path, "w", encoding="utf-8").write(new_lock_text)
    open(pod_path, "w", encoding="utf-8").write(new_pod_text)
    print("All files written. Re-verify by re-running with --dry-run "
          "or by inspecting the diff.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
