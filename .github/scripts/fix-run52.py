#!/usr/bin/env python3
"""Fix run #52 (master @ 497adda) -- single Dynamic Island.

User decision (2026-11-28): ONE island, long-press shows lyrics AND
playback controls (play/pause, next, previous) -- like QQ / NetEase.
The lyric island becomes the player; the separate system audio island
goes away.

Changes:
1. Attributes.swift: ContentState gains isPlaying (play/pause icon).
2. LyricsLiveActivity.swift: playback buttons (previous / play-pause /
   next) in the island expanded view and in the lock-screen banner,
   via Link to the app URL scheme com.anonymous.musicfree://liveactivity/<action>.
   (URL scheme + AppDelegate RCTLinkingManager wiring already exist.)
3. Module.swift: startActivity/updateActivity take isPlaying; new
   clearNowPlayingInfo() clears MPNowPlayingInfoCenter so the system
   stops showing its own separate audio island. Lock screen keeps
   working through the lyric Live Activity banner (with buttons).
4. liveActivityLyrics.ts: isPlaying plumbed through; clearNowPlayingInfo
   exported; dedup also tracks isPlaying (a pure play/pause flip must
   still push).
5. lyricManager.ts: tracks playback state; passes isPlaying when
   syncing; clears NowPlayingInfo when the lyric activity syncs.
   Pause KEEPS the island (paused state, tap play to resume -- it is
   the player now); Stop ENDS it.
6. New src/core/liveActivityLinking.ts: handles
   com.anonymous.musicfree://liveactivity/<action> URLs (play, pause,
   playpause, next, previous) by driving TrackPlayer; registered in
   bootstrap.
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


CONTROL_BUTTONS = """                // 播放控制：上一首 / 播放暂停 / 下一首。点按经 URL Scheme
                // 回主 App（见 liveActivityLinking.ts），不直接操作音频。
                HStack(spacing: 28) {
                    Link(destination: URL(string: "com.anonymous.musicfree://liveactivity/previous")!) {
                        Image(systemName: "backward.fill")
                            .font(.system(size: 18))
                    }
                    Link(destination: URL(string: "com.anonymous.musicfree://liveactivity/playpause")!) {
                        Image(systemName: context.state.isPlaying ? "pause.fill" : "play.fill")
                            .font(.system(size: 22))
                    }
                    Link(destination: URL(string: "com.anonymous.musicfree://liveactivity/next")!) {
                        Image(systemName: "forward.fill")
                            .font(.system(size: 18))
                    }
                }
                .padding(.top, 6)
"""


def main():
    # ---- 1. Attributes.swift: isPlaying in ContentState ----
    attr = os.path.join(ROOT, "ios/MusicFreeWidgets/Attributes.swift")
    replace(
        attr,
        "        /// 歌曲总时长（秒）\n"
        "        var duration: TimeInterval\n"
        "    }",
        "        /// 歌曲总时长（秒）\n"
        "        var duration: TimeInterval\n"
        "        /// 是否正在播放（决定播放按钮显示播放还是暂停图标）\n"
        "        var isPlaying: Bool\n"
        "    }",
        label="Attributes isPlaying",
    )

    # ---- 2. LyricsLiveActivity.swift ----
    w = os.path.join(ROOT, "ios/MusicFreeWidgets/LyricsLiveActivity.swift")
    replace(
        w,
        "/// v1 不带岛上播放按钮：按钮要 AppIntent 回调主 App，那套接线\n"
        "///（URL Scheme 处理）还没做；带一个按了没反应的按钮比没有更糟。\n",
        "/// 单岛模式：歌词岛就是播放器，长按展开页和锁屏横幅都带播放按钮\n"
        "///（上一首 / 播放暂停 / 下一首），经 URL Scheme 回调主 App。\n"
        "/// 系统音频岛由 Module.clearNowPlayingInfo() 清掉，不再单独出现。\n",
        label="widget comment",
    )
    # lock-screen banner: buttons below the progress view.
    replace(
        w,
        "                ProgressView(\n"
        "                    timerInterval: context.state.startedAt...progressEnd(\n"
        "                        startedAt: context.state.startedAt,\n"
        "                        duration: context.state.duration),\n"
        "                    countsDown: false\n"
        "                )\n"
        "            }",
        "                ProgressView(\n"
        "                    timerInterval: context.state.startedAt...progressEnd(\n"
        "                        startedAt: context.state.startedAt,\n"
        "                        duration: context.state.duration),\n"
        "                    countsDown: false\n"
        "                )\n"
        + CONTROL_BUTTONS
        + "            }",
        label="lock-screen buttons",
    )
    # island expanded .bottom: buttons below the lyric lines.
    replace(
        w,
        "                DynamicIslandExpandedRegion(.bottom) {\n"
        "                    VStack(alignment: .leading, spacing: 2) {\n"
        "                        Text(context.state.currentLine)\n"
        "                            .font(.system(size: 16, weight: .semibold))\n"
        "                            .lineLimit(2)\n"
        "                        Text(context.state.nextLine)\n"
        "                            .font(.system(size: 12))\n"
        "                            .foregroundStyle(.secondary)\n"
        "                            .lineLimit(1)\n"
        "                    }\n"
        "                }",
        "                DynamicIslandExpandedRegion(.bottom) {\n"
        "                    VStack(alignment: .leading, spacing: 2) {\n"
        "                        Text(context.state.currentLine)\n"
        "                            .font(.system(size: 16, weight: .semibold))\n"
        "                            .lineLimit(2)\n"
        "                        Text(context.state.nextLine)\n"
        "                            .font(.system(size: 12))\n"
        "                            .foregroundStyle(.secondary)\n"
        "                            .lineLimit(1)\n"
        + CONTROL_BUTTONS
        + "                    }\n"
        "                }",
        label="island buttons",
    )
    # preview ContentState gains isPlaying.
    replace(
        w,
        "        currentLine: \"故事的小黄花 从出生那年就飘着\",\n"
        "        nextLine: \"童年的荡秋千 随记忆一直晃到现在\",\n"
        "        startedAt: Date(), duration: 269)",
        "        currentLine: \"故事的小黄花 从出生那年就飘着\",\n"
        "        nextLine: \"童年的荡秋千 随记忆一直晃到现在\",\n"
        "        startedAt: Date(), duration: 269, isPlaying: true)",
        label="preview isPlaying",
    )

    # ---- 3. Module.swift ----
    m = os.path.join(ROOT, "ios/MusicFreeWidgets/Module.swift")
    replace(
        m,
        "import ExpoModulesCore\nimport ActivityKit\n",
        "import ExpoModulesCore\nimport ActivityKit\nimport MediaPlayer\n",
        label="Module import MediaPlayer",
    )
    replace(
        m,
        "        Function(\"startActivity\") {\n"
        "            (\n"
        "                title: String,\n"
        "                artist: String,\n"
        "                currentLine: String,\n"
        "                nextLine: String,\n"
        "                startedAtMs: Double,\n"
        "                durationSec: Double\n"
        "            ) -> Bool in",
        "        Function(\"startActivity\") {\n"
        "            (\n"
        "                title: String,\n"
        "                artist: String,\n"
        "                currentLine: String,\n"
        "                nextLine: String,\n"
        "                startedAtMs: Double,\n"
        "                durationSec: Double,\n"
        "                isPlaying: Bool\n"
        "            ) -> Bool in",
        label="Module startActivity sig",
    )
    replace(
        m,
        "                let contentState = LyricsLiveActivityAttributes.ContentState(\n"
        "                    currentLine: currentLine,\n"
        "                    nextLine: nextLine,\n"
        "                    startedAt: startedAt,\n"
        "                    duration: max(durationSec, 0)\n"
        "                )\n"
        "                // 30 分钟后标记为过期：App 异常退出时系统能及时收起活动。",
        "                let contentState = LyricsLiveActivityAttributes.ContentState(\n"
        "                    currentLine: currentLine,\n"
        "                    nextLine: nextLine,\n"
        "                    startedAt: startedAt,\n"
        "                    duration: max(durationSec, 0),\n"
        "                    isPlaying: isPlaying\n"
        "                )\n"
        "                // 30 分钟后标记为过期：App 异常退出时系统能及时收起活动。",
        label="Module startActivity state",
    )
    replace(
        m,
        "        Function(\"updateActivity\") {\n"
        "            (\n"
        "                currentLine: String,\n"
        "                nextLine: String,\n"
        "                startedAtMs: Double,\n"
        "                durationSec: Double\n"
        "            ) -> Void in",
        "        Function(\"updateActivity\") {\n"
        "            (\n"
        "                currentLine: String,\n"
        "                nextLine: String,\n"
        "                startedAtMs: Double,\n"
        "                durationSec: Double,\n"
        "                isPlaying: Bool\n"
        "            ) -> Void in",
        label="Module updateActivity sig",
    )
    replace(
        m,
        "                let contentState = LyricsLiveActivityAttributes.ContentState(\n"
        "                    currentLine: currentLine,\n"
        "                    nextLine: nextLine,\n"
        "                    startedAt: startedAt,\n"
        "                    duration: max(durationSec, 0)\n"
        "                )\n"
        "                let updatedContent = ActivityContent(",
        "                let contentState = LyricsLiveActivityAttributes.ContentState(\n"
        "                    currentLine: currentLine,\n"
        "                    nextLine: nextLine,\n"
        "                    startedAt: startedAt,\n"
        "                    duration: max(durationSec, 0),\n"
        "                    isPlaying: isPlaying\n"
        "                )\n"
        "                let updatedContent = ActivityContent(",
        label="Module updateActivity state",
    )
    # clearNowPlayingInfo: add after endActivity, before the closing of definition().
    replace(
        m,
        "        Function(\"endActivity\") { () -> Void in\n"
        "            if #available(iOS 16.2, *) {\n"
        "                Task {\n"
        "                    for activity in Activity<LyricsLiveActivityAttributes>.activities {\n"
        "                        await activity.end(nil, dismissalPolicy: .default)\n"
        "                    }\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}",
        "        Function(\"endActivity\") { () -> Void in\n"
        "            if #available(iOS 16.2, *) {\n"
        "                Task {\n"
        "                    for activity in Activity<LyricsLiveActivityAttributes>.activities {\n"
        "                        await activity.end(nil, dismissalPolicy: .default)\n"
        "                    }\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "\n"
        "        /// 把系统 Now Playing（MPNowPlayingInfoCenter）清掉，系统就\n"
        "        /// 不再单独占一个音频灵动岛。歌词岛自己带播放按钮，就是\n"
        "        /// 唯一的岛；锁屏上歌词 Live Activity 横幅（带按钮）顶上\n"
        "        /// 系统媒体控制。播放器每次切歌 / 改状态都可能重设\n"
        "        /// NowPlayingInfo，所以 JS 侧在每次同步歌词岛时都调一次。\n"
        "        Function(\"clearNowPlayingInfo\") { () -> Void in\n"
        "            MPNowPlayingInfoCenter.default().nowPlayingInfo = nil\n"
        "        }\n"
        "    }\n"
        "}",
        label="Module clearNowPlayingInfo",
    )

    # ---- 4. liveActivityLyrics.ts ----
    la = os.path.join(ROOT, "src/core/liveActivityLyrics.ts")
    replace(
        la,
        " *   startActivity(title, artist, currentLine, nextLine, startedAtMs, durationSec)\n"
        " *   updateActivity(currentLine, nextLine, startedAtMs, durationSec)\n"
        " *   endActivity()",
        " *   startActivity(title, artist, currentLine, nextLine, startedAtMs, durationSec, isPlaying)\n"
        " *   updateActivity(currentLine, nextLine, startedAtMs, durationSec, isPlaying)\n"
        " *   endActivity()\n"
        " *   clearNowPlayingInfo()",
        label="bridge comment",
    )
    replace(
        la,
        "interface IWidgetExtensionModule {\n"
        "    areActivitiesEnabled: () => boolean;\n"
        "    startActivity: (\n"
        "        title: string,\n"
        "        artist: string,\n"
        "        currentLine: string,\n"
        "        nextLine: string,\n"
        "        startedAtMs: number,\n"
        "        durationSec: number,\n"
        "    ) => boolean;\n"
        "    updateActivity: (\n"
        "        currentLine: string,\n"
        "        nextLine: string,\n"
        "        startedAtMs: number,\n"
        "        durationSec: number,\n"
        "    ) => void;\n"
        "    endActivity: () => void;\n"
        "}",
        "interface IWidgetExtensionModule {\n"
        "    areActivitiesEnabled: () => boolean;\n"
        "    startActivity: (\n"
        "        title: string,\n"
        "        artist: string,\n"
        "        currentLine: string,\n"
        "        nextLine: string,\n"
        "        startedAtMs: number,\n"
        "        durationSec: number,\n"
        "        isPlaying: boolean,\n"
        "    ) => boolean;\n"
        "    updateActivity: (\n"
        "        currentLine: string,\n"
        "        nextLine: string,\n"
        "        startedAtMs: number,\n"
        "        durationSec: number,\n"
        "        isPlaying: boolean,\n"
        "    ) => void;\n"
        "    endActivity: () => void;\n"
        "    clearNowPlayingInfo: () => void;\n"
        "}",
        label="bridge interface",
    )
    replace(
        la,
        "let activityActive = false;\nlet lastSentLine = \"\";",
        "let activityActive = false;\nlet lastSentLine = \"\";\nlet lastSentIsPlaying = false;",
        label="bridge dedup state",
    )
    replace(
        la,
        "export function startLyricsLiveActivity(\n"
        "    title: string,\n"
        "    artist: string,\n"
        "    currentLine: string,\n"
        "    nextLine: string,\n"
        "    startedAtMs: number,\n"
        "    durationSec: number,\n"
        "): void {",
        "export function startLyricsLiveActivity(\n"
        "    title: string,\n"
        "    artist: string,\n"
        "    currentLine: string,\n"
        "    nextLine: string,\n"
        "    startedAtMs: number,\n"
        "    durationSec: number,\n"
        "    isPlaying: boolean,\n"
        "): void {",
        label="bridge start sig",
    )
    replace(
        la,
        "        const ok = mod.startActivity(\n"
        "            title,\n"
        "            artist,\n"
        "            truncate(currentLine),\n"
        "            truncate(nextLine),\n"
        "            startedAtMs,\n"
        "            Math.max(durationSec, 0),\n"
        "        );\n"
        "        if (ok) {\n"
        "            activityActive = true;\n"
        "            lastSentLine = currentLine;\n"
        "        } else {",
        "        const ok = mod.startActivity(\n"
        "            title,\n"
        "            artist,\n"
        "            truncate(currentLine),\n"
        "            truncate(nextLine),\n"
        "            startedAtMs,\n"
        "            Math.max(durationSec, 0),\n"
        "            isPlaying,\n"
        "        );\n"
        "        if (ok) {\n"
        "            activityActive = true;\n"
        "            lastSentLine = currentLine;\n"
        "            lastSentIsPlaying = isPlaying;\n"
        "        } else {",
        label="bridge start call",
    )
    replace(
        la,
        "export function updateLyricsLiveActivity(\n"
        "    currentLine: string,\n"
        "    nextLine: string,\n"
        "    startedAtMs: number,\n"
        "    durationSec: number,\n"
        "): void {\n"
        "    // 行没变就不推：同一行重复 update 纯属浪费更新预算。\n"
        "    if (activityActive && currentLine === lastSentLine) {\n"
        "        return;\n"
        "    }",
        "export function updateLyricsLiveActivity(\n"
        "    currentLine: string,\n"
        "    nextLine: string,\n"
        "    startedAtMs: number,\n"
        "    durationSec: number,\n"
        "    isPlaying: boolean,\n"
        "): void {\n"
        "    // 行和播放状态都没变就不推：同一行重复 update 纯属浪费更新预算。\n"
        "    // 只翻播放 / 暂停时，行不变但图标要变，必须推。\n"
        "    if (\n"
        "        activityActive &&\n"
        "        currentLine === lastSentLine &&\n"
        "        isPlaying === lastSentIsPlaying\n"
        "    ) {\n"
        "        return;\n"
        "    }",
        label="bridge update sig+dedup",
    )
    replace(
        la,
        "        mod.updateActivity(\n"
        "            truncate(currentLine),\n"
        "            truncate(nextLine),\n"
        "            startedAtMs,\n"
        "            Math.max(durationSec, 0),\n"
        "        );\n"
        "        lastSentLine = currentLine;",
        "        mod.updateActivity(\n"
        "            truncate(currentLine),\n"
        "            truncate(nextLine),\n"
        "            startedAtMs,\n"
        "            Math.max(durationSec, 0),\n"
        "            isPlaying,\n"
        "        );\n"
        "        lastSentLine = currentLine;\n"
        "        lastSentIsPlaying = isPlaying;",
        label="bridge update call",
    )
    replace(
        la,
        "export function endLyricsLiveActivity(): void {\n"
        "    const mod = getModule();\n"
        "    if (!mod) {\n"
        "        activityActive = false;\n"
        "        lastSentLine = \"\";\n"
        "        return;\n"
        "    }\n"
        "    try {\n"
        "        mod.endActivity();\n"
        "    } catch {\n"
        "        // 结束失败也无所谓：活动最多 8 小时，系统会自己收掉。\n"
        "    } finally {\n"
        "        activityActive = false;\n"
        "        lastSentLine = \"\";\n"
        "    }\n"
        "}",
        "export function endLyricsLiveActivity(): void {\n"
        "    const mod = getModule();\n"
        "    if (!mod) {\n"
        "        activityActive = false;\n"
        "        lastSentLine = \"\";\n"
        "        lastSentIsPlaying = false;\n"
        "        return;\n"
        "    }\n"
        "    try {\n"
        "        mod.endActivity();\n"
        "    } catch {\n"
        "        // 结束失败也无所谓：活动最多 8 小时，系统会自己收掉。\n"
        "    } finally {\n"
        "        activityActive = false;\n"
        "        lastSentLine = \"\";\n"
        "        lastSentIsPlaying = false;\n"
        "    }\n"
        "}\n"
        "\n"
        "/** 清掉系统 Now Playing，让系统不再单独占一个音频灵动岛。 */\n"
        "export function clearNowPlayingInfo(): void {\n"
        "    try {\n"
        "        getModule()?.clearNowPlayingInfo();\n"
        "    } catch {\n"
        "        // 模块缺失时静默 no-op。\n"
        "    }\n"
        "}",
        label="bridge clearNowPlayingInfo",
    )

    # ---- 5. lyricManager.ts ----
    lm = os.path.join(ROOT, "src/core/lyricManager.ts")
    replace(
        lm,
        "import {\n"
        "    endLyricsLiveActivity,\n"
        "    startLyricsLiveActivity,",
        "import {\n"
        "    clearNowPlayingInfo,\n"
        "    endLyricsLiveActivity,\n"
        "    startLyricsLiveActivity,",
        label="lyricManager import",
    )
    # track playback state: add a field. Anchor on the class field
    # lastProgress (declared near the top of the class).
    replace(
        lm,
        "    private lastProgress = { position: 0, duration: 0 };",
        "    private lastProgress = { position: 0, duration: 0 };\n"
        "    // 最近一次播放状态（供歌词岛播放按钮图标用）。\n"
        "    private lastPlaybackPlaying = false;",
        label="lyricManager playing field",
    )
    # PlaybackState listener: pause keeps the island (paused state),
    # stop ends it; always refresh the button icon.
    replace(
        lm,
        "        // 播放状态一变就处理灵动岛：暂停/停止时结束活动（否则歌词岛\n"
        "        // 在音频关掉后还一直挂着），恢复播放时用最新进度重新同步\n"
        "        // （纠正进度条漂移）。没有这个监听，歌词岛只在行变化时才动。\n"
        "        RNTrackPlayer.addEventListener(Event.PlaybackState, ({ state }) => {\n"
        "            if (state === State.Paused || state === State.Stopped) {\n"
        "                endLyricsLiveActivity();\n"
        "            } else if (state === State.Playing) {\n"
        "                this.syncLiveActivity();\n"
        "            }\n"
        "        });",
        "        // 播放状态一变就处理灵动岛（单岛模式：歌词岛就是播放器）。\n"
        "        // 暂停时岛留着（显示暂停态，点播放可恢复）；停止时才结束\n"
        "        // 活动。每次都重同步一次，让播放按钮图标跟着状态翻。\n"
        "        RNTrackPlayer.addEventListener(Event.PlaybackState, ({ state }) => {\n"
        "            if (state === State.Stopped) {\n"
        "                this.lastPlaybackPlaying = false;\n"
        "                endLyricsLiveActivity();\n"
        "            } else if (state === State.Playing) {\n"
        "                this.lastPlaybackPlaying = true;\n"
        "                this.syncLiveActivity();\n"
        "            } else if (state === State.Paused) {\n"
        "                this.lastPlaybackPlaying = false;\n"
        "                this.syncLiveActivity();\n"
        "            }\n"
        "        });",
        label="lyricManager playback listener",
    )
    # syncLiveActivity: pass isPlaying + clear NowPlayingInfo.
    replace(
        lm,
        "        // 每次都走 start：原生 startActivity 已在内部处理“已有活动则更新”，\n"
        "        // 且失败后下次行变化会重新 start，不会像 update 分支那样永久卡死。\n"
        "        startLyricsLiveActivity(\n"
        "            musicItem.title,\n"
        "            musicItem.artist,\n"
        "            currentLine,\n"
        "            nextLine,\n"
        "            startedAtMs,\n"
        "            durationSec,\n"
        "        );",
        "        // 每次同步都清一次系统 Now Playing：播放器切歌 / 改状态时\n"
        "        // 会重设 NowPlayingInfo，系统音频岛就又冒出来；清掉它，\n"
        "        // 歌词岛才是唯一的岛。\n"
        "        clearNowPlayingInfo();\n"
        "\n"
        "        // 每次都走 start：原生 startActivity 已在内部处理“已有活动则更新”，\n"
        "        // 且失败后下次行变化会重新 start，不会像 update 分支那样永久卡死。\n"
        "        startLyricsLiveActivity(\n"
        "            musicItem.title,\n"
        "            musicItem.artist,\n"
        "            currentLine,\n"
        "            nextLine,\n"
        "            startedAtMs,\n"
        "            durationSec,\n"
        "            this.lastPlaybackPlaying,\n"
        "        );",
        label="lyricManager sync isPlaying",
    )

    # ---- 6. New Linking handler module ----
    linking = os.path.join(ROOT, "src/core/liveActivityLinking.ts")
    assert not os.path.exists(linking), "liveActivityLinking.ts already exists"
    with io.open(linking, "w", encoding="utf-8", newline="") as f:
        f.write(
            "/**\n"
            " * 灵动岛 / 锁屏 Live Activity 播放按钮的回调用。\n"
            " *\n"
            " * 岛上按钮是 SwiftUI Link，经 URL Scheme 打开 App：\n"
            " *   com.anonymous.musicfree://liveactivity/<action>\n"
            " * action: play | pause | playpause | next | previous。\n"
            " * AppDelegate 已把 URL 转给 RCTLinkingManager，这里在 JS 侧接住，\n"
            " * 直接驱动 TrackPlayer。点按钮会把 App 带到前台一次（Link 的\n"
            " * 固有行为）；若用户觉得打扰，后续再换成后台 AppIntent。\n"
            " */\n"
            "import { Linking } from \"react-native\";\n"
            "import RNTrackPlayer, { State } from \"react-native-track-player\";\n"
            "import TrackPlayer from \"./trackPlayer\";\n"
            "\n"
            "const SCHEME_PREFIX = \"com.anonymous.musicfree://liveactivity/\";\n"
            "\n"
            "async function handleLiveActivityAction(action: string): Promise<void> {\n"
            "    try {\n"
            "        switch (action) {\n"
            "            case \"play\":\n"
            "                await TrackPlayer.play();\n"
            "                break;\n"
            "            case \"pause\":\n"
            "                await TrackPlayer.pause();\n"
            "                break;\n"
            "            case \"playpause\": {\n"
            "                // 播放器外壳没有 getPlaybackState，用底层 RNTP 查状态。\n"
            "                const { state } =\n"
            "                    await RNTrackPlayer.getPlaybackState();\n"
            "                if (state === State.Playing) {\n"
            "                    await TrackPlayer.pause();\n"
            "                } else {\n"
            "                    await TrackPlayer.play();\n"
            "                }\n"
            "                break;\n"
            "            }\n"
            "            case \"next\":\n"
            "                await TrackPlayer.skipToNext();\n"
            "                break;\n"
            "            case \"previous\":\n"
            "                await TrackPlayer.skipToPrevious();\n"
            "                break;\n"
            "            default:\n"
            "                break;\n"
            "        }\n"
            "    } catch {\n"
            "        // 岛上按钮按了没反应比闪退强：静默。\n"
            "    }\n"
            "}\n"
            "\n"
            "function handleUrl(url: string | null | undefined): void {\n"
            "    if (!url || !url.startsWith(SCHEME_PREFIX)) {\n"
            "        return;\n"
            "    }\n"
            "    const action = url.slice(SCHEME_PREFIX.length).split(\"?\")[0].split(\"#\")[0];\n"
            "    void handleLiveActivityAction(action);\n"
            "}\n"
            "\n"
            "let registered = false;\n"
            "\n"
            "/** 在启动时调用一次：注册岛上按钮的 URL 监听。 */\n"
            "export function setupLiveActivityLinking(): void {\n"
            "    if (registered) {\n"
            "        return;\n"
            "    }\n"
            "    registered = true;\n"
            "    Linking.addEventListener(\"url\", ({ url }) => handleUrl(url));\n"
            "    void Linking.getInitialURL().then(handleUrl);\n"
            "}\n"
        )
    print("OK %s new file" % linking)

    # ---- 7. Register the Linking handler in bootstrap ----
    bs = os.path.join(ROOT, "src/entry/bootstrap/bootstrap.ts")
    # find the lyricManager import and add the linking import next to it.
    replace(
        bs,
        'import lyricManager from "@/core/lyricManager";',
        'import lyricManager from "@/core/lyricManager";\n'
        'import { setupLiveActivityLinking } from "@/core/liveActivityLinking";',
        label="bootstrap import",
    )
    # call it right before lyricManager.setup() in the bootstrap flow.
    replace(
        bs,
        "    await lyricManager.setup();",
        "    setupLiveActivityLinking();\n"
        "    await lyricManager.setup();",
        label="bootstrap call",
    )


if __name__ == "__main__":
    main()
