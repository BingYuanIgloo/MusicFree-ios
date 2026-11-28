#!/usr/bin/env python3
"""Fix run #51 (master @ ce4714d).

User report (2026-11-28): same song, same source -- lyrics showed the
first time, then NEVER again on replay. Root cause class: a transient
plugin fetch failure (or a cleared parser) wipes the lyric, and nothing
brings it back, because refreshLyric() sets lyricParser=null + no-lyric
state whenever the fetch returns null, even if this exact song had a
good lyric before.

Fix -- a persistent fallback lyric cache in lyricManager:
1. Whenever a lyric loads successfully, persist its rawLrc + translation
   to MMKV ("lyric.fallbackCache"), keyed by platform@id.
2. When the plugin fetch + auto-search both return null, try the
   fallback first; only if there is no fallback either, fall back to
   the no-lyric state.
3. If a forced re-fetch fails but a good lyric for this exact song is
   still in memory, keep showing it instead of blanking it.

Also records the user's decision: keep TWO Dynamic Islands (lyric
island + audio island) -- the user said whichever is simpler, and two
is simpler because it is already implemented; one island would need
playback controls rebuilt into the lyric activity.
"""
import io
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."


def replace(path, old, new, count=1, label=""):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        content = f.read()
    n = content.count(old)
    assert n == count, (
        "%s: expected %d occurrence(s) of %r, found %d"
        % (path, count, old[:80], n)
    )
    content = content.replace(old, new)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print("OK %s %s" % (path, label))


def main():
    lm = os.path.join(ROOT, "src/core/lyricManager.ts")
    # 1. imports: MMKV fallback store + stable song key.
    replace(
        lm,
        'import { isSameMediaItem } from "@/utils/mediaUtils";',
        'import { getMediaUniqueKey, isSameMediaItem } from "@/utils/mediaUtils";\n'
        'import getOrCreateMMKV from "@/utils/getOrCreateMMKV";',
        label="imports",
    )
    # 2. fallback helpers (module level, after the atoms).
    replace(
        lm,
        "const lyricStateAtom = atom<ILyricState>(defaultLyricState);\n"
        "const currentLyricItemAtom = atom<IParsedLrcItem | null>(null);",
        "const lyricStateAtom = atom<ILyricState>(defaultLyricState);\n"
        "const currentLyricItemAtom = atom<IParsedLrcItem | null>(null);\n"
        "\n"
        "// 歌词兜底缓存：某首歌一旦成功加载过歌词，就把 rawLrc + 翻译\n"
        "// 持久化在这里（MMKV，key 是 platform@id）。以后插件偶尔取不到\n"
        "// 歌词时，用这个兜底顶上，不让已经显示过的歌词凭空消失。\n"
        "const fallbackLyricStore = getOrCreateMMKV(\"lyric.fallbackCache\");\n"
        "\n"
        "function loadFallbackLyric(\n"
        "    musicItem: IMusic.IMusicItem,\n"
        "): ILyric.ILyricSource | null {\n"
        "    try {\n"
        "        const raw = fallbackLyricStore.getString(\n"
        "            getMediaUniqueKey(musicItem),\n"
        "        );\n"
        "        if (!raw) {\n"
        "            return null;\n"
        "        }\n"
        "        const parsed = JSON.parse(raw) as {\n"
        "            rawLrc?: string;\n"
        "            translation?: string;\n"
        "        };\n"
        "        if (!parsed.rawLrc && !parsed.translation) {\n"
        "            return null;\n"
        "        }\n"
        "        return {\n"
        "            rawLrc: parsed.rawLrc,\n"
        "            translation: parsed.translation,\n"
        "        };\n"
        "    } catch {\n"
        "        return null;\n"
        "    }\n"
        "}\n"
        "\n"
        "function saveFallbackLyric(\n"
        "    musicItem: IMusic.IMusicItem,\n"
        "    rawLrc?: string | null,\n"
        "    translation?: string | null,\n"
        "): void {\n"
        "    try {\n"
        "        if (!rawLrc && !translation) {\n"
        "            return;\n"
        "        }\n"
        "        fallbackLyricStore.set(\n"
        "            getMediaUniqueKey(musicItem),\n"
        "            JSON.stringify({\n"
        "                rawLrc: rawLrc ?? null,\n"
        "                translation: translation ?? null,\n"
        "            }),\n"
        "        );\n"
        "    } catch {\n"
        "        // 兜底缓存写失败不影响歌词显示。\n"
        "    }\n"
        "}",
        label="fallback helpers",
    )
    # 3. !lrcSource branch: fallback, then keep in-memory lyric, then no-lyric.
    replace(
        lm,
        "            // 如果源不存在，恢复默认设置\n"
        "            if (!lrcSource) {\n"
        "                this.setLyricAsNoLyricState();\n"
        "                this.lyricParser = null;\n"
        "                return;\n"
        "            }",
        "            // 如果源不存在，先试试兜底：这首歌上次成功加载过的歌词。\n"
        "            // 插件偶尔取不到歌词时，不要把已经显示过的歌词清掉；\n"
        "            // 只有兜底也没有时，才恢复成无歌词状态。\n"
        "            if (!lrcSource) {\n"
        "                const fallback = loadFallbackLyric(currentMusicItem);\n"
        "                if (fallback) {\n"
        "                    lrcSource = fallback;\n"
        "                } else if (\n"
        "                    this.lyricParser &&\n"
        "                    this.trackPlayer.isCurrentMusic(\n"
        "                        this.lyricParser.musicItem,\n"
        "                    ) &&\n"
        "                    this.lyricParser.getLyricItems().length > 0\n"
        "                ) {\n"
        "                    // 内存里还有这首歌的好歌词（强制重取失败时），留着继续显示。\n"
        "                    return;\n"
        "                } else {\n"
        "                    this.setLyricAsNoLyricState();\n"
        "                    this.lyricParser = null;\n"
        "                    return;\n"
        "                }\n"
        "            }",
        label="fallback on empty source",
    )
    # 4. Save the lyric after a successful load.
    replace(
        lm,
        "            getDefaultStore().set(lyricStateAtom, {\n"
        "                loading: false,\n"
        "                lyrics: this.lyricParser.getLyricItems(),\n"
        "                hasTranslation: !!lrcSource.translation,\n"
        "                meta: this.lyricParser.getMeta(),\n"
        "            });",
        "            getDefaultStore().set(lyricStateAtom, {\n"
        "                loading: false,\n"
        "                lyrics: this.lyricParser.getLyricItems(),\n"
        "                hasTranslation: !!lrcSource.translation,\n"
        "                meta: this.lyricParser.getMeta(),\n"
        "            });\n"
        "\n"
        "            // 记下来：这首歌的歌词成功加载过。以后插件取不到时，\n"
        "            // 用这个兜底顶上，不让歌词凭空消失。\n"
        "            saveFallbackLyric(\n"
        "                currentMusicItem,\n"
        "                lrcSource.rawLrc,\n"
        "                lrcSource.translation,\n"
        "            );",
        label="save on success",
    )


if __name__ == "__main__":
    main()
