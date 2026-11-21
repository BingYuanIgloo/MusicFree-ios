import { PlaybackState } from "@rntp/player";

/**
 * 播放状态（v4 State 的本地等价物）。
 *
 * v5 不再提供 State 枚举：PlaybackState 只有
 * idle / ready / buffering / ended / error 五种，
 * “是否在播”要另外看 isPlaying()。这里保留 v4 的语义，
 * 供 musicIsPaused / musicIsBuffering 以及各处
 * useMusicState() 的调用方继续使用，不用改业务代码。
 */
export enum State {
    None = "none",
    Ready = "ready",
    Playing = "playing",
    Paused = "paused",
    Stopped = "stopped",
    Buffering = "buffering",
    Loading = "loading",
    Ended = "ended",
    Error = "error",
    Connecting = "connecting",
}

/**
 * 把 v5 的 PlaybackState + isPlaying 映射回 v4 语义的 State。
 * - Buffering → Buffering
 * - 正在出声 → Playing
 * - Idle（未加载任何曲目）/ Ended → Stopped（调用方会重新设置音源）
 * - Error → Error
 * - 其余（Ready 且未播放）→ Paused
 */
export const toMusicState = (
    playbackState: PlaybackState,
    isPlaying: boolean,
): State => {
    if (playbackState === PlaybackState.Buffering) {
        return State.Buffering;
    }
    if (isPlaying) {
        return State.Playing;
    }
    if (
        playbackState === PlaybackState.Idle ||
        playbackState === PlaybackState.Ended
    ) {
        return State.Stopped;
    }
    if (playbackState === PlaybackState.Error) {
        return State.Error;
    }
    return State.Paused;
};

/**
 * 音乐是否处于停止状态
 * @param state
 * @returns
 */
export const musicIsPaused = (state: State | undefined) =>
    state !== State.Playing;

/**
 * 音乐是否处于缓冲中状态
 * @param state
 * @returns
 */
export const musicIsBuffering = (state: State | undefined) =>
    state === State.Loading || state === State.Buffering;
