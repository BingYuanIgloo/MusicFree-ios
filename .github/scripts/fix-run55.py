#!/usr/bin/env python3
"""Fix run55: auto highest quality for playback + download.

The user has to switch every song from the default (standard) to super
by hand, and pick a quality on every download. The app already tries
qualities in order (getQualityOrder) and takes the first that returns a
source, so making the default "super" with order "asc" means it tries
[super, high, standard, low] -- always the highest the source offers,
falling back when a source only has standard/high.

Applies to master (9f6f962, after fix-run54). Run from repo root.
Edits are exact-string replacements; the script fails loudly if a
pattern is not found (so a silent no-op never ships as a 'fix').
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
# When run by the GitHub workflow the script lives at repo root.
if not os.path.exists(os.path.join(ROOT, "package.json")):
    ROOT = os.getcwd()

def read(path):
    with open(os.path.join(ROOT, path), "r", encoding="utf-8", newline="") as f:
        return f.read()

def write(path, content, newline=None):
    full = os.path.join(ROOT, path)
    with open(full, "w", encoding="utf-8", newline=newline) as f:
        f.write(content)

def replace(path, old, new, count=1):
    content = read(path)
    if old not in content:
        print(f"FAIL: pattern not found in {path}:\n{old[:200]}")
        sys.exit(1)
    content = content.replace(old, new, count)
    write(path, content)
    print(f"OK: {path}")

def replace_crlf(path, old, new, count=1):
    """Edit a CRLF file, preserving CRLF line endings."""
    content = read(path)
    normalized = content.replace("\r\n", "\n")
    if old not in normalized:
        print(f"FAIL: pattern not found in {path}:\n{old[:200]}")
        sys.exit(1)
    normalized = normalized.replace(old, new, count)
    content = normalized.replace("\n", "\r\n")
    write(path, content, newline="")
    print(f"OK: {path} (CRLF preserved)")

# ---------------------------------------------------------------- 1. trackPlayer
# Playback default standard -> super, so play() tries
# [super, high, standard, low] and always picks the highest available.
# (a) initial quality atom; (b) restore-on-start fallback;
# (c) the defaultPlayQuality fallback used by play().
# ----------------------------------------------------------------
replace(
    "src/core/trackPlayer/index.ts",
    'const qualityAtom = atom<IMusic.IQualityKey>("standard");',
    'const qualityAtom = atom<IMusic.IQualityKey>("super");',
)
replace(
    "src/core/trackPlayer/index.ts",
    '        const quality =\n            PersistStatus.get("music.quality") ||\n            this.configService.getConfig("basic.defaultPlayQuality") ||\n            "standard";',
    '        const quality =\n            PersistStatus.get("music.quality") ||\n            this.configService.getConfig("basic.defaultPlayQuality") ||\n            "super";',
)
replace(
    "src/core/trackPlayer/index.ts",
    '            const qualityOrder = getQualityOrder(\n                this.configService.getConfig("basic.defaultPlayQuality") ?? "standard",',
    '            const qualityOrder = getQualityOrder(\n                this.configService.getConfig("basic.defaultPlayQuality") ?? "super",',
)

# ---------------------------------------------------------------- 2. downloader
# Download default standard -> super, same fallback chain
# [super, high, standard, low].
# ----------------------------------------------------------------
replace(
    "src/core/downloader.ts",
    '                const qualityOrder = getQualityOrder(\n                    nextTask.quality ??\n                    this.configService.getConfig("basic.defaultDownloadQuality") ??\n                    "standard",',
    '                const qualityOrder = getQualityOrder(\n                    nextTask.quality ??\n                    this.configService.getConfig("basic.defaultDownloadQuality") ??\n                    "super",',
)

# ---------------------------------------------------------------- 3. basicSetting
# Settings radio defaults must match the new code defaults, otherwise
# the Settings page would still show "standard" as selected.
# ----------------------------------------------------------------
replace(
    "src/pages/setting/settingTypes/basicSetting.tsx",
    '                    defaultPlayQuality ?? "standard",',
    '                    defaultPlayQuality ?? "super",',
)
replace(
    "src/pages/setting/settingTypes/basicSetting.tsx",
    '                    defaultDownloadQuality ?? "standard",',
    '                    defaultDownloadQuality ?? "super",',
)

# ---------------------------------------------------------------- 4. musicItemOptions
# Download from the song options panel: skip the quality picker and
# download directly. downloader.download with no quality falls back to
# basic.defaultDownloadQuality (now super), so it picks the highest
# the source offers. Close the options panel afterwards (the picker
# used to close itself on pick).
# ----------------------------------------------------------------
replace_crlf(
    "src/components/panels/types/musicItemOptions.tsx",
    '        {\n            icon: "arrow-down-tray",\n            title: t("common.download"),\n            show: !downloaded,\n            onPress: async () => {\n                showPanel("MusicQuality", {\n                    musicItem,\n                    type: "download",\n                    async onQualityPress(quality) {\n                        downloader.download(musicItem, quality);\n                    },\n                });\n            },\n        },',
    '        {\n            icon: "arrow-down-tray",\n            title: t("common.download"),\n            show: !downloaded,\n            onPress: async () => {\n                downloader.download(musicItem);\n                hidePanel();\n            },\n        },',
)

# ---------------------------------------------------------------- 5. operations.tsx
# Download from the detail-page download icon: same as above -- skip
# the quality picker, download directly at the highest available.
# (The play-quality badge panel above it is untouched: the user can
# still switch quality for the current song by tapping the badge.)
# ----------------------------------------------------------------
replace_crlf(
    "src/pages/musicDetail/components/content/albumCover/operations.tsx",
    '            <Icon\n                name={isDownloaded ? "check-circle-outline" : "arrow-down-tray"}\n                size={iconSizeConst.normal}\n                color={colors.text}\n                onPress={() => {\n                    if (musicItem && !isDownloaded) {\n                        showPanel("MusicQuality", {\n                            type: "download",\n                            musicItem,\n                            async onQualityPress(quality) {\n                                downloader.download(musicItem, quality);\n                            },\n                        });\n                    }\n                }}\n            />',
    '            <Icon\n                name={isDownloaded ? "check-circle-outline" : "arrow-down-tray"}\n                size={iconSizeConst.normal}\n                color={colors.text}\n                onPress={() => {\n                    if (musicItem && !isDownloaded) {\n                        downloader.download(musicItem);\n                    }\n                }}\n            />',
)

print("ALL FIX-RUN55 EDITS APPLIED")
