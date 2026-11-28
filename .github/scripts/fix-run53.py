#!/usr/bin/env python3
"""Fix run53 (corrected): detail page theme-aware + lyric cleaning + headless sync.

User correction (2026-11-28): detail page must stay theme-aware, NOT forced dark.
  - Dark mode: blur + white text (already correct, do not change).
  - Light mode: blur ALSO present + text REVERSED to dark.
The previous run50 change (light blur 0.15) made light mode all white.
Fix: light blur 0.35 (visible, not muddy like 0.5, not invisible like 0.15).
Text/icons already use colors.text (theme-aware: dark in light mode,
white in dark mode) -- navBar, lyric lines, operations, playControl,
heartIcon, lyricOperations -- so do NOT touch them.

1. background.tsx: light blur 0.15 -> 0.35 (dark stays 0.5).
2. Lyric symbol cleaning (lrcParser.ts): strip symbols that do not appear
   in English or Chinese grammar. Keep letters, numbers, spaces and
   EN+ZH punctuation (apostrophe ' is kept: don't/it's).
   Remove ^ ` | \\ < > { } control chars, zero-width chars, music notes.
3. Headless lyric sync (lyricManager + service): main thread writes the
   parsed lyric items to a shared MMKV store; the headless playback
   service reads it on PlaybackProgressUpdated and pushes the current
   line to the Live Activity (fixes lyrics freezing in background).
   Also ends the Live Activity reliably when the queue ends
   (PlaybackQueueEnded) so a finished song does not linger on the
   lock screen and replay can start clean.
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."

def patch(path, old, new, must=True):
    p = os.path.join(ROOT, path)
    with open(p, "r", encoding="utf-8") as f:
        s = f.read()
    if old not in s:
        msg = f"  !! NOT FOUND in {path}: {old[:70]!r}"
        print(msg)
        if must:
            raise SystemExit(msg)
        return False
    s = s.replace(old, new, 1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"  ok {path}")
    return True

# ---------------------------------------------------------------- 1. background
print("== background.tsx (light blur visible again) ==")
patch(
    "src/pages/musicDetail/components/background.tsx",
    "style={[style.blur, { opacity: theme.dark ? 0.5 : 0.15 }]}",
    "style={[style.blur, { opacity: theme.dark ? 0.5 : 0.35 }]}",
)

# ---------------------------------------------------------------- 2. lyric cleaning
print("== lrcParser.ts (clean junk symbols) ==")
clean_fn = '''
// 歌词杂符号清理：只保留中英文语法里出现的字符。
// 保留：所有字母、变音符号、数字、空白，以及下面这些歌词里有意义的标点。
// 用户白名单（2026-11-28）：撇号 '、逗号 ,、句号 .、感叹号 !、问号 ?、
// 星号 *（歌词打码靠它，删掉就半句看不懂）。用户又补了一句让我自己
// 定：再留几个歌词里确实有用的——省略号 …（拖尾）、破折号 — –（停顿）、
// 中圆点 ·（外国人名里的分隔，如约翰·列侬）、顿号 、（中文并列）。
// 其余一律删：^ ` | \\ < > { } 引号、冒号、分号、括号、斜杠、
// @ # $ % & + = _ ~ 等。
const LYRIC_PUNCT = "'\\u2019,\\uff0c\\u3001.\\u3002\\uff0e!\\uff01?\\uff1f*\\uff0a\\u2026\\u2014\\u2013\\u00b7";

let LYRIC_CLEAN_RE: RegExp | null = null;
try {
    const punct = LYRIC_PUNCT.replace(/([\\]\\\\^-])/g, "\\\\$1");
    LYRIC_CLEAN_RE = new RegExp(
        `[^\\\\p{L}\\\\p{M}\\\\p{N}\\\\p{Z}${punct}]`,
        "gu",
    );
} catch {
    LYRIC_CLEAN_RE = null;
}

export function cleanLyricLine(line: string): string {
    if (!line) {
        return line;
    }
    // 先去掉控制字符和零宽字符
    let s = line.replace(/[\\u0000-\\u001F\\u007F\\u200B\\u200C\\u200D\\uFEFF]/g, "");
    if (LYRIC_CLEAN_RE) {
        s = s.replace(LYRIC_CLEAN_RE, "");
    } else {
        // 旧引擎不支持 \\\\p{...} 时的兜底：只删已知的杂符号
        s = s.replace(/[\\^`|\\\\<>{}\\u266a\\u266b]/g, "");
    }
    return s;
}
'''
patch(
    "src/utils/lrcParser.ts",
    "const timeReg = /\\[[\\d:.]+\\]/g;",
    "const timeReg = /\\[[\\d:.]+\\]/g;" + clean_fn,
)
patch(
    "src/utils/lrcParser.ts",
    '            lrc = rawLrcs[0]?.trim?.() ?? "";\n',
    '            lrc = cleanLyricLine(rawLrcs[0]?.trim?.() ?? "");\n',
)
patch(
    "src/utils/lrcParser.ts",
    """        if (lrcItems.length === 0 && raw.length) {
            lrcItems = raw.split("\\n").map((_, index) => ({
                time: 0,
                lrc: _,
                index,
            }));
        }""",
    """        if (lrcItems.length === 0 && raw.length) {
            lrcItems = raw.split("\\n").map((_, index) => ({
                time: 0,
                lrc: cleanLyricLine(_),
                index,
            }));
        }""",
)

# ---------------------------------------------------------------- 3. lyricManager: MMKV + queue-ended
print("== lyricManager.ts (write lyric data for headless service) ==")
patch(
    "src/core/lyricManager.ts",
    'const fallbackLyricStore = getOrCreateMMKV("lyric.fallbackCache");',
    '''const fallbackLyricStore = getOrCreateMMKV("lyric.fallbackCache");

// 灵动岛后台同步用的歌词数据（MMKV，headless service 也能读）。
// 主线程在歌词解析好后把当前歌的 items + 标题/作者/偏移写进来，
// 后台 service 按进度算当前行推给灵动岛（主线程切后台会被挂起，
// 歌词行就停在原地不动）。无歌词时清掉，避免后台推旧歌词。
const liveActivityLyricStore = getOrCreateMMKV("lyric.liveActivity");''',
)
patch(
    "src/core/lyricManager.ts",
    """    private setLyricAsNoLyricState() {
        getDefaultStore().set(lyricStateAtom, {
            loading: false,
            lyrics: [],
            hasTranslation: false,
        });
        getDefaultStore().set(currentLyricItemAtom, null);
    }""",
    """    private setLyricAsNoLyricState() {
        getDefaultStore().set(lyricStateAtom, {
            loading: false,
            lyrics: [],
            hasTranslation: false,
        });
        getDefaultStore().set(currentLyricItemAtom, null);
        try {
            liveActivityLyricStore.delete("current");
        } catch {
            // 清不掉也不影响主流程
        }
    }""",
)
patch(
    "src/core/lyricManager.ts",
    """            const currentLyric = ignoreProgress ? (this.lyricParser.getLyricItems()?.[0] ?? null) : this.lyricParser.getPosition((await this.trackPlayer.getProgress()).position);
            getDefaultStore().set(currentLyricItemAtom, currentLyric || null);""",
    """            const currentLyric = ignoreProgress ? (this.lyricParser.getLyricItems()?.[0] ?? null) : this.lyricParser.getPosition((await this.trackPlayer.getProgress()).position);
            getDefaultStore().set(currentLyricItemAtom, currentLyric || null);

            // 写一份给后台 service：歌词行 + 标题/作者/偏移，
            // 供后台按进度推灵动岛。
            try {
                liveActivityLyricStore.set(
                    "current",
                    JSON.stringify({
                        title: currentMusicItem.title,
                        artist: currentMusicItem.artist,
                        offset: this.lyricParser.getMeta()?.offset ?? 0,
                        items: this.lyricParser.getLyricItems().map((it) => ({
                            time: it.time,
                            lrc: it.lrc,
                            translation: it.translation ?? "",
                        })),
                    }),
                );
            } catch {
                // 写失败不影响主流程
            }""",
)
patch(
    "src/core/lyricManager.ts",
    """        // 回到前台时用最新进度重新同步一次（打开软件歌词不刷新的根因：
        // 之前只有行变化才推，切回来时行没变就不推，显示就停在旧进度）。
        AppState.addEventListener("change", (nextState) => {""",
    """        // 播完最后一首（队列结束）也要收掉灵动岛，不然锁屏会留一首
        // 卡在最后的歌；再重播时旧活动还占着，歌词就推不出来了。
        RNTrackPlayer.addEventListener(Event.PlaybackQueueEnded, () => {
            endLyricsLiveActivity();
        });

        // 回到前台时用最新进度重新同步一次（打开软件歌词不刷新的根因：
        // 之前只有行变化才推，切回来时行没变就不推，显示就停在旧进度）。
        AppState.addEventListener("change", (nextState) => {""",
)

# ---------------------------------------------------------------- 4. headless service
print("== service/index.ts (headless lyric sync) ==")
patch(
    "src/service/index.ts",
    'import PersistStatus from "@/utils/persistStatus";',
    '''import PersistStatus from "@/utils/persistStatus";
import getOrCreateMMKV from "@/utils/getOrCreateMMKV";
import {
    endLyricsLiveActivity,
    startLyricsLiveActivity,
} from "@/core/liveActivityLyrics";''',
)
patch(
    "src/service/index.ts",
    """    RNTrackPlayer.addEventListener(Event.PlaybackProgressUpdated, evt => {
        PersistStatus.set("music.progress", evt.position);
    });""",
    """    // 后台歌词同步：主线程切后台会被挂起，歌词行就停在原地。
    // 这里是 headless service，后台也能收到进度事件，按进度算当前
    // 行推给灵动岛。歌词数据由主线程写进 lyric.liveActivity MMKV。
    // 行没变就不推，省更新预算。
    const headlessLyricStore = getOrCreateMMKV("lyric.liveActivity");
    let lastHeadlessLyricLine = "";
    const headlessSyncLyric = (position: number, duration: number) => {
        try {
            const raw = headlessLyricStore.getString("current");
            if (!raw) {
                return;
            }
            const data = JSON.parse(raw) as {
                title?: string;
                artist?: string;
                offset?: number;
                items?: Array<{
                    time: number;
                    lrc: string;
                    translation?: string;
                }>;
            };
            const items = data.items ?? [];
            if (!items.length) {
                return;
            }
            const pos = position - (data.offset ?? 0);
            if (pos < items[0].time) {
                return;
            }
            let current = items[0];
            for (let i = 0; i < items.length; i++) {
                if (items[i].time <= pos) {
                    current = items[i];
                } else {
                    break;
                }
            }
            const line = current.lrc ?? "";
            if (!line || line === lastHeadlessLyricLine) {
                return;
            }
            lastHeadlessLyricLine = line;
            const idx = items.indexOf(current);
            const next = items[idx + 1]?.lrc ?? "";
            // 走 start：原生侧已有活动就更新，没有就新建，
            // 后台也能把岛拉起来，不依赖主线程。
            startLyricsLiveActivity(
                data.title ?? "",
                data.artist ?? "",
                line,
                next,
                Date.now() - position * 1000,
                duration,
                true,
            );
        } catch {
            // 解析失败就跳过，不影响播放。
        }
    };

    RNTrackPlayer.addEventListener(Event.PlaybackProgressUpdated, evt => {
        PersistStatus.set("music.progress", evt.position);
        headlessSyncLyric(evt.position ?? 0, evt.duration ?? 0);
    });

    // 播完 / 队列结束：后台也收掉灵动岛，不然锁屏留一首卡在最后的歌。
    RNTrackPlayer.addEventListener(Event.PlaybackState, ({ state }) => {
        if (state === State.Stopped) {
            lastHeadlessLyricLine = "";
            endLyricsLiveActivity();
        }
    });
    RNTrackPlayer.addEventListener(Event.PlaybackQueueEnded, () => {
        lastHeadlessLyricLine = "";
        endLyricsLiveActivity();
    });""",
)

print("ALL DONE")
