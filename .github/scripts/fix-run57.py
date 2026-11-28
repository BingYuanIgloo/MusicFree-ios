#!/usr/bin/env python3
"""fix-run57: make lyrics + Dynamic Island lifecycle reliable.

User report 2026-11-28: lyrics and the island "fight", sometimes the
island/lock-screen shows nothing, sometimes lyrics appear but never go
away, sometimes they disappear and never come back, lyrics finish but
the banner stays on the lock screen. A mess of inconsistent states.

Root causes (verified in code at 1689e5e):
1. endActivity uses dismissalPolicy .default: iOS keeps the lock-screen
   banner visible after the activity ends (it lingers as a notification).
   -> use .immediate so the lock screen clears the moment we end it.
2. startActivity updates an existing activity but title/artist live in
   the activity ATTRIBUTES, which update() cannot change. After a song
   change the island keeps showing the PREVIOUS song's title/artist
   with the new song's lyrics -> the two surfaces "fight".
   -> if the existing activity's title/artist differ, end it
   (immediate) and request a fresh activity with the new attributes.
3. headlessSyncLyric returns early when the MMKV lyric key is gone or
   the item list is empty, without ending the activity. When the
   foreground clears the lyrics (track change / no-lyric song) the
   background service leaves the old lyrics stuck on the island.
   -> when there is no lyric data AND this context previously pushed a
   line, end the activity. Guarded by lastHeadlessLyricLine so we do
   not spam end() on every progress tick for lyric-less songs.

Files (all LF): ios/MusicFreeWidgets/Module.swift,
src/service/index.ts. Run from repo root: python3 fix-run57.py .
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    n = text.count(old)
    if n != count:
        raise SystemExit(
            f"{path}: expected {count} occurrence(s) of pattern, found {n}\n---\n{old}\n---"
        )
    p.write_text(text.replace(old, new), encoding="utf-8")
    print(f"{path}: replaced {n} occurrence(s)")


# --- 1. Module.swift: endActivity .default -> .immediate ---
replace(
    "ios/MusicFreeWidgets/Module.swift",
    """        Function("endActivity") { () -> Void in
            if #available(iOS 16.2, *) {
                Task {
                    for activity in Activity<LyricsLiveActivityAttributes>.activities {
                        await activity.end(nil, dismissalPolicy: .default)
                    }
                }
            }
        }""",
    """        Function("endActivity") { () -> Void in
            if #available(iOS 16.2, *) {
                Task {
                    for activity in Activity<LyricsLiveActivityAttributes>.activities {
                        // .immediate：结束时锁屏横幅立刻消失。.default 会把
                        // 锁屏横幅留下来当通知，用户看到的就是“歌词放完了
                        // 还显示在锁屏上，关不掉”。
                        await activity.end(nil, dismissalPolicy: .immediate)
                    }
                }
            }
        }""",
)

# --- 2. Module.swift: startActivity re-requests when the song changes ---
replace(
    "ios/MusicFreeWidgets/Module.swift",
    """                // 同一时间只保留一个歌词活动：如果已存在，先更新它而不是再开一个。
                let existing = Activity<LyricsLiveActivityAttributes>.activities
                if let activity = existing.first {
                    Task {
                        await activity.update(activityContent)
                    }
                    return true
                }""",
    """                // 同一时间只保留一个歌词活动：如果已存在且是同一首歌，
                // 直接更新它；换歌了则结束旧活动重开（歌名/歌手存在活动
                // 属性里，update 改不了，不重开岛上一直是上一首的歌，
                // 歌词却是新歌的，岛和锁屏就“打架”）。
                let existing = Activity<LyricsLiveActivityAttributes>.activities
                if let activity = existing.first {
                    if activity.attributes.title == title &&
                        activity.attributes.artist == artist {
                        Task {
                            await activity.update(activityContent)
                        }
                        return true
                    }
                    Task {
                        await activity.end(nil, dismissalPolicy: .immediate)
                    }
                }""",
)

# --- 3. service/index.ts: headless ends the island when lyric data is gone ---
replace(
    "src/service/index.ts",
    """            const raw = headlessLyricStore.getString("current");
            if (!raw) {
                return;
            }""",
    """            const raw = headlessLyricStore.getString("current");
            if (!raw) {
                // 歌词数据没了（切歌时主线程刚删了旧 key、新歌词还没写进来，
                // 或这首歌本来就没歌词）：如果后台之前推过歌词，主动把岛收掉，
                // 不然旧歌词会一直卡在岛上/锁屏上，直到下一行歌词才刷新。
                // lastHeadlessLyricLine 为空说明本上下文没推过歌，不用重复 end。
                if (lastHeadlessLyricLine) {
                    lastHeadlessLyricLine = "";
                    lastHeadlessPushTime = 0;
                    endLyricsLiveActivity();
                }
                return;
            }""",
)

replace(
    "src/service/index.ts",
    """            const items = data.items ?? [];
            if (!items.length) {
                return;
            }""",
    """            const items = data.items ?? [];
            if (!items.length) {
                if (lastHeadlessLyricLine) {
                    lastHeadlessLyricLine = "";
                    lastHeadlessPushTime = 0;
                    endLyricsLiveActivity();
                }
                return;
            }""",
)

print("fix-run57 applied OK")
