#!/usr/bin/env python3
"""Fix run #50 (master @ 2e87115).

User report (2026-11-28, run #48 phone test, screenshots):
1. Lock-screen audio progress (1:41) and lyric Live Activity progress (2:25)
   are completely different. Root cause: syncLiveActivity() computes
   startedAt from the CACHED lastProgress.position, which is only updated
   on PlaybackProgressUpdated events -- stale after pause/seek/background,
   while the widget's ProgressView is a wall-clock timer from startedAt.
   Fix: fetch fresh progress (RNTrackPlayer.getProgress()) inside
   syncLiveActivity (async, falls back to cache on error).
2. Lyric island lingers after the audio is turned off. Root cause: there is
   NO playback-state listener anywhere in src/ -- sync only runs when a
   lyric line changes, so pause/stop never ends the activity.
   Fix: Event.PlaybackState listener -- end on Paused/Stopped, re-sync on
   Playing. (User wants BOTH islands kept: lyric island + audio island.)
3. Lyrics don't refresh when the app is opened. Root cause: sync only runs
   on line change; foregrounding with the same line never pushes.
   Fix: AppState "active" listener re-syncs with the fresh position.
4. Detail/lyric page background is a muddy gray-brown in light theme
   (user: "like color inversion"). Root cause: the blurred album art at
   opacity 0.5 over #fafafa. Fix: opacity is theme-dependent --
   0.5 in dark (looks right there), 0.15 in light (clean background).
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
    # 1. imports: AppState (foreground re-sync) + State (pause/stop test).
    replace(
        lm,
        'import { unlink, writeFile } from "react-native-fs";\n'
        'import RNTrackPlayer, { Event } from "react-native-track-player";',
        'import { unlink, writeFile } from "react-native-fs";\n'
        'import { AppState } from "react-native";\n'
        'import RNTrackPlayer, { Event, State } from "react-native-track-player";',
        label="imports",
    )
    # 2. setup(): playback-state + foreground listeners.
    replace(
        lm,
        "        getDefaultStore().sub(currentLyricItemAtom, () => {\n"
        "            this.syncLiveActivity();\n"
        "        });\n"
        "\n"
        "        this.refreshLyric(true);",
        "        getDefaultStore().sub(currentLyricItemAtom, () => {\n"
        "            this.syncLiveActivity();\n"
        "        });\n"
        "\n"
        "        // 播放状态一变就处理灵动岛：暂停/停止时结束活动（否则歌词岛\n"
        "        // 在音频关掉后还一直挂着），恢复播放时用最新进度重新同步\n"
        "        // （纠正进度条漂移）。没有这个监听，歌词岛只在行变化时才动。\n"
        "        RNTrackPlayer.addEventListener(Event.PlaybackState, ({ state }) => {\n"
        "            if (state === State.Paused || state === State.Stopped) {\n"
        "                endLyricsLiveActivity();\n"
        "            } else if (state === State.Playing) {\n"
        "                this.syncLiveActivity();\n"
        "            }\n"
        "        });\n"
        "\n"
        "        // 回到前台时用最新进度重新同步一次（打开软件歌词不刷新的根因：\n"
        "        // 之前只有行变化才推，切回来时行没变就不推，显示就停在旧进度）。\n"
        "        AppState.addEventListener(\"change\", (nextState) => {\n"
        "            if (nextState === \"active\") {\n"
        "                this.syncLiveActivity();\n"
        "            }\n"
        "        });\n"
        "\n"
        "        this.refreshLyric(true);",
        label="listeners",
    )
    # 3. syncLiveActivity(): async + fresh progress for startedAt.
    replace(
        lm,
        "    syncLiveActivity() {",
        "    async syncLiveActivity() {",
        label="async",
    )
    replace(
        lm,
        "        const startedAtMs =\n"
        "            Date.now() - (this.lastProgress.position || 0) * 1000;\n"
        "        const durationSec = this.lastProgress.duration || 0;",
        "        // 用实时进度算 startedAt，不要用缓存的 lastProgress：缓存只在\n"
        "        // 进度事件里更新，暂停/切歌/切后台后就 stale，歌词进度条会和\n"
        "        // 音频进度条对不上（锁屏上一个 1:41 一个 2:25 就是这么来的）。\n"
        "        let position = this.lastProgress.position || 0;\n"
        "        let durationSec = this.lastProgress.duration || 0;\n"
        "        try {\n"
        "            const progress = await RNTrackPlayer.getProgress();\n"
        "            if (typeof progress?.position === \"number\") {\n"
        "                position = progress.position;\n"
        "            }\n"
        "            if (typeof progress?.duration === \"number\") {\n"
        "                durationSec = progress.duration;\n"
        "            }\n"
        "        } catch {\n"
        "            // 拿不到实时进度就用缓存，不阻塞歌词显示。\n"
        "        }\n"
        "        const startedAtMs = Date.now() - position * 1000;",
        label="fresh progress",
    )

    # 4. Detail-page background: blur opacity follows the theme.
    bg = os.path.join(
        ROOT, "src/pages/musicDetail/components/background.tsx"
    )
    replace(
        bg,
        'import { ImgAsset } from "@/constants/assetsConst";\n'
        'import { useCurrentMusic } from "@/core/trackPlayer";',
        'import { ImgAsset } from "@/constants/assetsConst";\n'
        'import Theme from "@/core/theme";\n'
        'import { useCurrentMusic } from "@/core/trackPlayer";',
        label="theme import",
    )
    replace(
        bg,
        "    const musicItem = useCurrentMusic();\n"
        "    const colors = useColors();",
        "    const musicItem = useCurrentMusic();\n"
        "    const colors = useColors();\n"
        "    const theme = Theme.useTheme();",
        label="theme hook",
    )
    replace(
        bg,
        "            <Image style={style.blur} blurRadius={50} source={artworkSource} />",
        "            <Image\n"
        "                style={[style.blur, { opacity: theme.dark ? 0.5 : 0.15 }]}\n"
        "                blurRadius={50}\n"
        "                source={artworkSource}\n"
        "            />",
        label="blur opacity",
    )
    replace(
        bg,
        "        right: 0,\n"
        "        bottom: 0,\n"
        "        opacity: 0.5,\n"
        "    },\n"
        "});",
        "        right: 0,\n"
        "        bottom: 0,\n"
        "    },\n"
        "});",
        label="drop static opacity",
    )


if __name__ == "__main__":
    main()
