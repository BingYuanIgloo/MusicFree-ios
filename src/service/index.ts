import Config from "@/core/appConfig";
import RNTrackPlayer, { Event, State } from "react-native-track-player";
import TrackPlayer from "@/core/trackPlayer";
import { musicIsPaused } from "@/utils/trackUtils";
import PersistStatus from "@/utils/persistStatus";
import getOrCreateMMKV from "@/utils/getOrCreateMMKV";
import {
    endLyricsLiveActivity,
    startLyricsLiveActivity,
} from "@/core/liveActivityLyrics";

let resumeState: State | null;
module.exports = async function () {
    RNTrackPlayer.addEventListener(Event.RemotePlay, () => TrackPlayer.play());
    RNTrackPlayer.addEventListener(Event.RemotePause, () =>
        TrackPlayer.pause(),
    );
    RNTrackPlayer.addEventListener(Event.RemotePrevious, () =>
        TrackPlayer.skipToPrevious(),
    );
    RNTrackPlayer.addEventListener(Event.RemoteNext, () =>
        TrackPlayer.skipToNext(),
    );
    RNTrackPlayer.addEventListener(
        Event.RemoteDuck,
        async ({ paused, permanent }) => {
            if (Config.getConfig("basic.notInterrupt")) {
                return;
            }
            if (permanent) {
                return TrackPlayer.pause();
            }
            const tempRemoteDuckConf = Config.getConfig(
                "basic.tempRemoteDuck",
            );
            if (tempRemoteDuckConf === "lowerVolume") {
                if (paused) {
                    const tempRemoteDuckVolume = Config.getConfig(
                        "basic.tempRemoteDuckVolume",
                    ) ?? 0.5;
                    return RNTrackPlayer.setVolume(1 - tempRemoteDuckVolume);
                } else {
                    return RNTrackPlayer.setVolume(1);
                }
            } else {
                if (paused) {
                    resumeState =
                        (await RNTrackPlayer.getPlaybackState()).state ??
                        State.Paused;
                    return TrackPlayer.pause();
                } else {
                    if (resumeState && !musicIsPaused(resumeState)) {
                        resumeState = null;
                        return TrackPlayer.play();
                    }
                    resumeState = null;
                }
            }
        },
    );


    // 后台歌词同步：主线程切后台会被挂起，歌词行就停在原地。
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
    });

    RNTrackPlayer.addEventListener(Event.RemoteStop, async () => {
        RNTrackPlayer.stop();
    });

    RNTrackPlayer.addEventListener(Event.RemoteSeek, async evt => {
        TrackPlayer.seekTo(evt.position);
    });
};
