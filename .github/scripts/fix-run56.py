#!/usr/bin/env python3
"""Fix run56: lyric stale-data on song change + island drops + panel gap.

User tested run #53 and reported (2026-11-28 ~06:38 EST):
1. Progress bars don't match: lock-screen Now Playing says 0:26 while the
   lyric banner says 0:54.
2. Switch from a song WITH lyrics to a lyric-less source (e.g. Bilibili
   video): the audio progress moves, but the lyric progress never resets
   to zero -- it keeps following the previous song. And lyrics appear for
   a source that has no lyrics at all ("where did these lyrics come
   from?").
3. The horizontal black bar / playlist panel: the list is placed in the
   middle of the screen instead of spanning bottom-to-top, leaving a
   dimmed gap at the bottom (mini player showing through the mask).
4. In #53 the Dynamic Island shows NO lyrics at all; the lock screen
   has them, the island has nothing.

Root causes (all verified in code):
1+2. Stale lyric data race. setLyricAsLoadingState() (called the instant
   a song changes, before the new lyric fetch) cleared the in-memory
   lyric atoms but did NOT delete the MMKV "current" key that the
   headless service reads. So while the new song's lyric fetch was still
   in flight, the headless PlaybackProgressUpdated handler kept pushing
   the OLD song's lyric items against the NEW song's position -- the
   lyric progress followed the previous song, and a lyric-less song
   kept showing the old lyrics. The headless service also had no
   track-change listener and no reset of lastHeadlessLyricLine, so the
   stale line could linger.
4. Same root cause, plus the 2-minute staleDate from run54. When the
   lyric line stops advancing (stale data / long instrumental gap), no
   update is pushed for 2 minutes, the activity goes stale, and iOS
   removes it from the Dynamic Island while the lock-screen banner
   (a notification) lingers -- exactly "lock screen has it, island
   has nothing". Fix: push a heartbeat update at least every 45s
   while music plays so the staleDate is always refreshed, and clear
   the stale data on track change so lines advance again.
3. Bottom-sheet panels used `bottom: 0` to anchor. If the parent chain
   is inset (safe area / mini-player reservation), bottom: 0 leaves the
   panel floating above the screen bottom. Anchor bottom panels by an
   explicit top computed from the window height instead, so the panel
   bottom edge is the window bottom edge.

Applies to master (d986cbc, after fix-run55). Run from repo root.
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
        print(f"FAIL: pattern not found in {path}:\n{old[:300]}")
        sys.exit(1)
    content = content.replace(old, new, count)
    write(path, content)
    print(f"OK: {path}")

# ---------------------------------------------------------------- 1. lyricManager
# setLyricAsLoadingState: also delete the headless-sync MMKV key the
# instant a song change starts, so the headless service has no stale
# lyric items to push against the new song's position.
replace(
    "src/core/lyricManager.ts",
    """    private setLyricAsLoadingState() {
        getDefaultStore().set(lyricStateAtom, {
            loading: true,
            lyrics: [],
            hasTranslation: false,
        });
        getDefaultStore().set(currentLyricItemAtom, null);
    }""",
    """    private setLyricAsLoadingState() {
        getDefaultStore().set(lyricStateAtom, {
            loading: true,
            lyrics: [],
            hasTranslation: false,
        });
        getDefaultStore().set(currentLyricItemAtom, null);
        // 切歌瞬间就清掉后台同步用的歌词数据：不然 headless service
        // 在新歌词还没取回来之前，会拿着旧歌的 items 按新歌的进度
        // 继续推灵动岛，歌词进度条就跟着上一首走、切到无歌词的源
        // 时旧歌词也赖着不走。
        try {
            liveActivityLyricStore.delete("current");
        } catch {
            // 清不掉也不影响主流程
        }
    }""",
)

# ---------------------------------------------------------------- 2. headless service
# (a) Heartbeat: push at least every 45s even when the lyric line has
# not changed, so the 2-minute staleDate is always refreshed while
# music plays and iOS never drops the island mid-song.
# (b) PlaybackActiveTrackChanged: reset the line tracker and end the
# old activity the moment the track changes, so no stale lyric or
# progress survives into the new song (even in background).
replace(
    "src/service/index.ts",
    """    const headlessLyricStore = getOrCreateMMKV("lyric.liveActivity");
    let lastHeadlessLyricLine = "";
    const headlessSyncLyric = (position: number, duration: number) => {""",
    """    const headlessLyricStore = getOrCreateMMKV("lyric.liveActivity");
    let lastHeadlessLyricLine = "";
    // 上次成功推岛的时间。歌词行很久不变（前奏/间奏长）时也要定期
    // 推一次，只为把活动的过期时间往后推，不然 2 分钟无更新活动
    // 就过期，灵动岛会把岛收掉，只剩锁屏横幅。
    let lastHeadlessPushTime = 0;
    const HEADLESS_HEARTBEAT_MS = 45000;
    const headlessSyncLyric = (position: number, duration: number) => {""",
)

replace(
    "src/service/index.ts",
    """            const line = current.lrc ?? "";
            if (!line || line === lastHeadlessLyricLine) {
                return;
            }
            lastHeadlessLyricLine = line;""",
    """            const line = current.lrc ?? "";
            const now = Date.now();
            const lineChanged = !!line && line !== lastHeadlessLyricLine;
            const heartbeatDue =
                now - lastHeadlessPushTime >= HEADLESS_HEARTBEAT_MS;
            if (!line || (!lineChanged && !heartbeatDue)) {
                return;
            }
            lastHeadlessLyricLine = line;
            lastHeadlessPushTime = now;""",
)

replace(
    "src/service/index.ts",
    """    RNTrackPlayer.addEventListener(Event.PlaybackProgressUpdated, evt => {
        PersistStatus.set("music.progress", evt.position);
        headlessSyncLyric(evt.position ?? 0, evt.duration ?? 0);
    });""",
    """    // 切歌：后台也立即收掉旧歌的岛、清掉行记录，不然新歌还没取到
    // 歌词之前，后台会拿着旧歌的 items 按新歌进度继续推，歌词和
    // 进度条都跟着上一首走；切到无歌词的源时旧歌词也会赖着不走。
    RNTrackPlayer.addEventListener(Event.PlaybackActiveTrackChanged, () => {
        lastHeadlessLyricLine = "";
        lastHeadlessPushTime = 0;
        endLyricsLiveActivity();
    });

    RNTrackPlayer.addEventListener(Event.PlaybackProgressUpdated, evt => {
        PersistStatus.set("music.progress", evt.position);
        headlessSyncLyric(evt.position ?? 0, evt.duration ?? 0);
    });""",
)

# ---------------------------------------------------------------- 3. panelBase
# Bottom-anchored panels: anchor by an explicit top computed from the
# window height, so the panel bottom edge is the window bottom edge
# even if the parent chain is inset (safe area / mini-player area).
# bottom: 0 is relative to the parent; if the parent ends above the
# screen bottom, the panel floats in the middle and the dimmed page
# shows through underneath (the "horizontal black bar" / list in the
# middle).
replace(
    "src/components/panels/base/panelBase.tsx",
    """                orientation === "horizontal" ? {
                    height: vh(100) - safeAreaInsets.top,
                    bottom: 0,
                } : {
                    top: positionMethod === "top" ? (Dimensions.get("window").height + safeAreaInsets.top) - height - safeAreaInsets.bottom : undefined,
                    bottom: positionMethod === "bottom" ? 0 : undefined,
                    height: height,
                },""",
    """                orientation === "horizontal" ? {
                    height: vh(100) - safeAreaInsets.top,
                    bottom: 0,
                } : {
                    // 底部弹层直接按窗口高度算 top，让面板底边贴着屏幕
                    // 底边，不依赖父容器的 bottom: 0。父容器若被安全区
                    // 或迷你播放条垫高，bottom: 0 会让面板悬在半空，
                    // 底下露出被遮罩变暗的页面（“列表放到了屏幕中间”、
                    // 横向黑条）。
                    top: positionMethod === "top" ? (Dimensions.get("window").height + safeAreaInsets.top) - height - safeAreaInsets.bottom : Dimensions.get("window").height - height,
                    bottom: undefined,
                    height: height,
                },""",
)

print("All run56 fixes applied.")
