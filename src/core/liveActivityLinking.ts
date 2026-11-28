/**
 * 灵动岛 / 锁屏 Live Activity 播放按钮的回调用。
 *
 * 岛上按钮是 SwiftUI Link，经 URL Scheme 打开 App：
 *   com.anonymous.musicfree://liveactivity/<action>
 * action: play | pause | playpause | next | previous。
 * AppDelegate 已把 URL 转给 RCTLinkingManager，这里在 JS 侧接住，
 * 直接驱动 TrackPlayer。点按钮会把 App 带到前台一次（Link 的
 * 固有行为）；若用户觉得打扰，后续再换成后台 AppIntent。
 */
import { Linking } from "react-native";
import RNTrackPlayer, { State } from "react-native-track-player";
import TrackPlayer from "./trackPlayer";

const SCHEME_PREFIX = "com.anonymous.musicfree://liveactivity/";

async function handleLiveActivityAction(action: string): Promise<void> {
    try {
        switch (action) {
            case "play":
                await TrackPlayer.play();
                break;
            case "pause":
                await TrackPlayer.pause();
                break;
            case "playpause": {
                // 播放器外壳没有 getPlaybackState，用底层 RNTP 查状态。
                const { state } =
                    await RNTrackPlayer.getPlaybackState();
                if (state === State.Playing) {
                    await TrackPlayer.pause();
                } else {
                    await TrackPlayer.play();
                }
                break;
            }
            case "next":
                await TrackPlayer.skipToNext();
                break;
            case "previous":
                await TrackPlayer.skipToPrevious();
                break;
            default:
                break;
        }
    } catch {
        // 岛上按钮按了没反应比闪退强：静默。
    }
}

function handleUrl(url: string | null | undefined): void {
    if (!url || !url.startsWith(SCHEME_PREFIX)) {
        return;
    }
    const action = url.slice(SCHEME_PREFIX.length).split("?")[0].split("#")[0];
    void handleLiveActivityAction(action);
}

let registered = false;

/** 在启动时调用一次：注册岛上按钮的 URL 监听。 */
export function setupLiveActivityLinking(): void {
    if (registered) {
        return;
    }
    registered = true;
    Linking.addEventListener("url", ({ url }) => handleUrl(url));
    void Linking.getInitialURL().then(handleUrl);
}
