import { getCurrentDialog, showDialog } from "@/components/dialogs/useDialog";
import {
    internalFakeSoundKey,
    sortIndexSymbol,
    timeStampSymbol,
} from "@/constants/commonConst";
import { MusicRepeatMode } from "@/constants/repeatModeConst";
import delay from "@/utils/delay";
import getUrlExt from "@/utils/getUrlExt";
import { errorLog, trace } from "@/utils/log";
import { createMediaIndexMap } from "@/utils/mediaIndexMap";
import {
    getLocalPath,
    isSameMediaItem,
} from "@/utils/mediaUtils";
import Network from "@/utils/network";
import PersistStatus from "@/utils/persistStatus";
import { getQualityOrder } from "@/utils/qualities";
import { musicIsPaused, State, toMusicState } from "@/utils/trackUtils";
import EventEmitter from "eventemitter3";
import { produce } from "immer";
import { atom, getDefaultStore, useAtomValue } from "jotai";
import shuffle from "lodash.shuffle";
import ReactNativeTrackPlayer, {
    Event,
    MediaItem,
    useIsPlaying,
    usePlaybackState,
    useProgress,
} from "@rntp/player";
import LocalMusicSheet from "../localMusicSheet";

import { TrackPlayerEvents } from "@/core.defination/trackPlayer";
import type { IAppConfig } from "@/types/core/config";
import type { IMusicHistory } from "@/types/core/musicHistory";
import { ITrackPlayer } from "@/types/core/trackPlayer/index";
import minDistance from "@/utils/minDistance";
import { IPluginManager } from "@/types/core/pluginManager";
import { ImgAsset } from "@/constants/assetsConst";
import { resolveImportedAssetOrPath } from "@/utils/fileUtils";



const currentMusicAtom = atom<IMusic.IMusicItem | null>(null);
const repeatModeAtom = atom<MusicRepeatMode>(MusicRepeatMode.QUEUE);
const qualityAtom = atom<IMusic.IQualityKey>("standard");
const playListAtom = atom<IMusic.IMusicItem[]>([]);

/** MediaItem.url 可能是字符串或 {uri, headers} 对象，统一取字符串。 */
function mediaUrlString(
    url: MediaItem["url"] | null | undefined,
): string | undefined {
    if (typeof url === "string") {
        return url;
    }
    if (url && typeof url === "object") {
        const uri = (url as { uri?: string | number }).uri;
        return typeof uri === "string" ? uri : undefined;
    }
    return undefined;
}


class TrackPlayer extends EventEmitter<{
    [TrackPlayerEvents.PlayEnd]: () => void;
    [TrackPlayerEvents.CurrentMusicChanged]: (musicItem: IMusic.IMusicItem | null) => void;
    [TrackPlayerEvents.ProgressChanged]: (progress: {
        position: number;
        duration: number;
    }) => void;
}> implements ITrackPlayer {
    // 依赖
    private configService!: IAppConfig;
    private musicHistoryService!: IMusicHistory;
    private pluginManagerService!: IPluginManager;

    // 当前播放的音乐下标
    private currentIndex = -1;
    // v5 的 MediaItemTransition 不再带 lastIndex，fake 曲目判断需要自己记上一个下标
    private lastActiveIndex = -1;
    // 音乐播放器服务是否启动
    private serviceInited = false;
    // 播放队列索引map
    private playListIndexMap = createMediaIndexMap([] as IMusic.IMusicItem[]);


    private static maxMusicQueueLength = 10000;
    private static halfMaxMusicQueueLength = 5000;
    private static toggleRepeatMapping = {
        [MusicRepeatMode.SHUFFLE]: MusicRepeatMode.SINGLE,
        [MusicRepeatMode.SINGLE]: MusicRepeatMode.QUEUE,
        [MusicRepeatMode.QUEUE]: MusicRepeatMode.SHUFFLE,
    };
    private static fakeAudioUrl = "musicfree://fake-audio";
    private static proposedAudioUrl = "musicfree://proposed-audio";

    constructor() {
        super();
    }

    public get previousMusic() {
        const currentMusic = this.currentMusic;
        if (!currentMusic) {
            return null;
        }

        return this.getPlayListMusicAt(this.currentIndex - 1);
    }

    public get currentMusic() {
        return getDefaultStore().get(currentMusicAtom);
    }

    public get nextMusic() {
        const currentMusic = this.currentMusic;
        if (!currentMusic) {
            return null;
        }

        return this.getPlayListMusicAt(this.currentIndex + 1);
    }

    public get repeatMode() {
        return getDefaultStore().get(repeatModeAtom);
    }

    public get quality() {
        return getDefaultStore().get(qualityAtom);
    }

    public get playList() {
        return getDefaultStore().get(playListAtom);
    }


    injectDependencies(configService: IAppConfig, musicHistoryService: IMusicHistory, pluginManager: IPluginManager): void {
        this.configService = configService;
        this.musicHistoryService = musicHistoryService;
        this.pluginManagerService = pluginManager;
    }


    async setupTrackPlayer() {
        const rate = PersistStatus.get("music.rate");
        const musicQueue = PersistStatus.get("music.playList");
        const repeatMode = PersistStatus.get("music.repeatMode");
        const progress = PersistStatus.get("music.progress");
        const track = PersistStatus.get("music.musicItem");
        const quality =
            PersistStatus.get("music.quality") ||
            this.configService.getConfig("basic.defaultPlayQuality") ||
            "standard";

        // 状态恢复
        if (rate) {
            ReactNativeTrackPlayer.setPlaybackSpeed(+rate / 100);
        }
        if (repeatMode) {
            getDefaultStore().set(repeatModeAtom, repeatMode as MusicRepeatMode);
        }

        if (musicQueue && Array.isArray(musicQueue)) {
            this.addAll(
                musicQueue,
                undefined,
                repeatMode === MusicRepeatMode.SHUFFLE,
            );
        }

        if (track && this.isInPlayList(track)) {
            if (!this.configService.getConfig("basic.autoPlayWhenAppStart")) {
                track.isInit = true;
            }

            // 异步
            this.pluginManagerService.getByMedia(track)
                ?.methods.getMediaSource(track, quality)
                .then(async newSource => {
                    track.url = newSource?.url || track.url;
                    track.headers = newSource?.headers || track.headers;

                    if (isSameMediaItem(this.currentMusic, track)) {
                        await this.setTrackSource(track, false);
                        if (progress) {
                            // 异步
                            this.seekTo(progress);
                        }
                    }
                });
            this.setCurrentMusic(track);

            if (progress) {
                // 异步
                this.seekTo(progress);
            }
        }

        if (!this.serviceInited) {

            /**
             * 此事件可能会被触发多次（比如直接替换queue） 参考代码：https://github.com/doublesymmetry/KotlinAudio
             */
            ReactNativeTrackPlayer.addEventListener(
                Event.MediaItemTransition,
                async evt => {
                    // v5 的 MediaItemTransition 不再带 lastIndex / track：
                    // 上一个下标由本类自己记录（lastActiveIndex），
                    // 当前曲目在 evt.item 里。
                    const prevIndex = this.lastActiveIndex;
                    this.lastActiveIndex = evt.index;
                    if (
                        evt.index === 1 &&
                        prevIndex === 0 &&
                        mediaUrlString(evt.item?.url) ===
                            TrackPlayer.fakeAudioUrl
                    ) {
                        trace("队列末尾，播放下一首");
                        this.emit(TrackPlayerEvents.PlayEnd);
                        if (
                            this.repeatMode ===
                            MusicRepeatMode.SINGLE
                        ) {
                            await this.play(null, true);
                        } else {
                            // 当前生效的歌曲是下一曲的标记
                            await this.skipToNext();
                        }
                    }
                },
            );

            ReactNativeTrackPlayer.addEventListener(
                Event.PlaybackError,
                async e => {
                    errorLog("播放出错", e.message);
                    // WARNING: 不稳定，报错的时候有可能track已经变到下一首歌去了
                    const currentTrack =
                        ReactNativeTrackPlayer.getActiveMediaItem();
                    if (Boolean(currentTrack?.extras?.isInit)) {
                        // HACK: 避免初始失败的情况：把 isInit 从 extras 里清掉，
                        // 否则下一次报错还会走这条分支，永远不跳下一首。
                        // v5 的 updateMetadata 只改展示字段，改不了 extras，
                        // 所以用 replaceMediaItem 原位替换（曲目本身已出错，无打断）。
                        ReactNativeTrackPlayer.replaceMediaItem(0, {
                            ...currentTrack,
                            extras: {
                                ...(currentTrack.extras ?? {}),
                                isInit: undefined,
                            },
                        });
                        return;
                    }

                    const currentUrl = mediaUrlString(currentTrack?.url);
                    // v4 用报错文案 "android-io-file-not-found" 排除本地文件缺失；
                    // v5 的 code 已归一化（network/source/...），文案不再可靠，
                    // 改为直接判断当前曲目是不是本地文件。
                    const isLocalFile =
                        !!currentUrl &&
                        (currentUrl.startsWith("file://") ||
                            currentUrl.startsWith("content://"));
                    if (
                        currentUrl !== TrackPlayer.fakeAudioUrl &&
                        currentUrl !== TrackPlayer.proposedAudioUrl &&
                        ReactNativeTrackPlayer.getActiveMediaItemIndex() === 0 &&
                        e.message &&
                        !isLocalFile
                    ) {
                        trace("播放出错", {
                            message: e.message,
                            code: e.code,
                        });

                        this.handlePlayFail();
                    }
                },
            );

            this.serviceInited = true;
        }
    }

    /**************** 播放队列 ******************/
    getMusicIndexInPlayList(musicItem?: IMusic.IMusicItem | null) {
        if (!musicItem) {
            return -1;
        }
        return this.playListIndexMap.getIndex(musicItem);
    }

    isInPlayList(musicItem?: IMusic.IMusicItem | null) {
        if (!musicItem) {
            return false;
        }

        return this.playListIndexMap.has(musicItem);
    }

    getPlayListMusicAt(index: number): IMusic.IMusicItem | null {
        const playList = this.playList;
        const len = playList.length;
        if (len === 0) {
            return null;
        }
        return playList[(index + len) % len];
    }

    isPlayListEmpty() {
        return this.playList.length === 0;
    }

    /****** 播放逻辑 *****/
    addAll(
        musicItems: Array<IMusic.IMusicItem>,
        beforeIndex?: number,
        shouldShuffle?: boolean,
    ): void {
        const now = Date.now();
        let newPlayList: IMusic.IMusicItem[] = [];
        let currentPlayList = this.playList;
        musicItems.forEach((item, index) => {
            item[timeStampSymbol] = now;
            item[sortIndexSymbol] = index;
        });

        if (beforeIndex === undefined || beforeIndex < 0) {
            // 1.1. 添加到歌单末尾，并过滤掉已有的歌曲
            newPlayList = currentPlayList.concat(
                musicItems.filter(item => !this.isInPlayList(item)),
            );
        } else {
            // 1.2. 新的播放列表，插入
            const indexMap = createMediaIndexMap(musicItems);
            const beforeDraft = currentPlayList
                .slice(0, beforeIndex)
                .filter(item => !indexMap.has(item));
            const afterDraft = currentPlayList
                .slice(beforeIndex)
                .filter(item => !indexMap.has(item));

            newPlayList = [...beforeDraft, ...musicItems, ...afterDraft];
        }

        // 如果太长了
        if (newPlayList.length > TrackPlayer.maxMusicQueueLength) {
            newPlayList = this.shrinkPlayListToSize(
                newPlayList,
                beforeIndex ?? newPlayList.length - 1,
            );
        }

        // 2. 如果需要随机
        if (shouldShuffle) {
            newPlayList = shuffle(newPlayList);
        }
        // 3. 设置播放列表
        this.setPlayList(newPlayList);
    }

    add(
        musicItem: IMusic.IMusicItem | IMusic.IMusicItem[],
        beforeIndex?: number,
    ): void {
        this.addAll(
            Array.isArray(musicItem) ? musicItem : [musicItem],
            beforeIndex,
        );
    }

    addNext(musicItem: IMusic.IMusicItem | IMusic.IMusicItem[]): void {
        const shouldAutoPlay = this.isPlayListEmpty() || !this.currentMusic;

        this.add(musicItem, this.currentIndex + 1);

        if (shouldAutoPlay) {
            this.play(Array.isArray(musicItem) ? musicItem[0] : musicItem);
        }
    }

    async remove(musicItem: IMusic.IMusicItem): Promise<void> {
        const playList = this.playList;

        let newPlayList: IMusic.IMusicItem[] = [];
        let currentMusic: IMusic.IMusicItem | null = this.currentMusic;
        const targetIndex = this.getMusicIndexInPlayList(musicItem);
        let shouldPlayCurrent: boolean | null = null;
        if (targetIndex === -1) {
            // 1. 这种情况应该是出错了
            return;
        }
        // 2. 移除的是当前项
        if (this.currentIndex === targetIndex) {
            // 2.1 停止播放，移除当前项
            newPlayList = produce(playList, draft => {
                draft.splice(targetIndex, 1);
            });
            // 2.2 设置新的播放列表，并更新当前音乐
            if (newPlayList.length === 0) {
                currentMusic = null;
                shouldPlayCurrent = false;
            } else {
                currentMusic = newPlayList[this.currentIndex % newPlayList.length];
                try {
                    const state = toMusicState(
                        ReactNativeTrackPlayer.getPlaybackState(),
                        ReactNativeTrackPlayer.isPlaying(),
                    );
                    shouldPlayCurrent = !musicIsPaused(state);
                } catch {
                    shouldPlayCurrent = false;
                }
            }
            this.setCurrentMusic(currentMusic);
        } else {
            // 3. 删除
            newPlayList = produce(playList, draft => {
                draft.splice(targetIndex, 1);
            });
        }

        this.setPlayList(newPlayList);
        if (shouldPlayCurrent === true) {
            await this.play(currentMusic, true);
        } else if (shouldPlayCurrent === false) {
            await this.reset();
        }
    }

    isCurrentMusic(musicItem?: IMusic.IMusicItem | null) {
        return isSameMediaItem(musicItem, this.currentMusic);
    }

    async play(
        musicItem?: IMusic.IMusicItem | null,
        forcePlay?: boolean,
    ): Promise<void> {
        try {
            // 如果不传参，默认是播放当前音乐
            if (!musicItem) {
                musicItem = this.currentMusic;
            }
            if (!musicItem) {
                throw new Error(PlayFailReason.PLAY_LIST_IS_EMPTY);
            }
            // 1. 移动网络禁止播放
            const localPath = getLocalPath(musicItem);
            if (
                Network.isCellular &&
                !this.configService.getConfig("basic.useCelluarNetworkPlay") &&
                !LocalMusicSheet.isLocalMusic(musicItem) &&
                !localPath
            ) {
                await this.reset();
                throw new Error(PlayFailReason.FORBID_CELLUAR_NETWORK_PLAY);
            }

            // 2. 如果是当前正在播放的音频
            if (this.isCurrentMusic(musicItem)) {
                // 获取底层播放器中的track（v5：getTrack 改成读整个队列，
                // 再用 extras 里的 platform/id 还原成内部曲目对象做比对）
                const currentTrack = ReactNativeTrackPlayer.getQueue()[0];
                const currentTrackItem =
                    this.mediaItemToMusicItem(currentTrack);
                // 2.1 如果当前有源
                if (
                    currentTrackItem &&
                    mediaUrlString(currentTrack?.url) &&
                    isSameMediaItem(musicItem, currentTrackItem)
                ) {
                    const currentActiveIndex =
                        ReactNativeTrackPlayer.getActiveMediaItemIndex();
                    if (currentActiveIndex !== 0) {
                        ReactNativeTrackPlayer.skipToIndex(0);
                    }
                    if (forcePlay) {
                        // 2.1.1 强制重新开始
                        await this.seekTo(0);
                    }
                    const currentState = toMusicState(
                        ReactNativeTrackPlayer.getPlaybackState(),
                        ReactNativeTrackPlayer.isPlaying(),
                    );
                    if (currentState === State.Stopped) {
                        await this.setTrackSource(currentTrackItem);
                    }
                    if (currentState !== State.Playing) {
                        // 2.1.2 恢复播放
                        ReactNativeTrackPlayer.play();
                    }
                    // 这种情况下，播放队列和当前歌曲都不需要变化
                    return;
                }
                // 2.2 其他情况：重新获取源
            }

            // 3. 如果没有在播放列表中，添加到队尾；同时更新列表状态
            const inPlayList = this.isInPlayList(musicItem);
            if (!inPlayList) {
                this.add(musicItem);
            }

            // 4. 更新列表状态和当前音乐
            this.setCurrentMusic(musicItem);
            // v5：setQueue 改名 setMediaItems；曲目对象先经 toMediaItem
            // 转成 MediaItem（artwork/album → artworkUrl/albumTitle，
            // headers 进 url 对象，.m3u8 标 mimeType）。
            ReactNativeTrackPlayer.setMediaItems([
                this.toMediaItem({
                    ...musicItem,
                    url: TrackPlayer.proposedAudioUrl,
                }),
                this.toMediaItem(this.getFakeNextTrack()),
            ]);

            // 5. 获取音源
            let track: IMusic.IMusicItem;

            // 5.1 通过插件获取音源
            const plugin = this.pluginManagerService.getByName(musicItem.platform);
            // 5.2 获取音质排序
            const qualityOrder = getQualityOrder(
                this.configService.getConfig("basic.defaultPlayQuality") ?? "standard",
                this.configService.getConfig("basic.playQualityOrder") ?? "asc",
            );
            // 5.3 插件返回音源
            let source: IPlugin.IMediaSourceResult | null = null;
            for (let quality of qualityOrder) {
                if (this.isCurrentMusic(musicItem)) {
                    source =
                        (await plugin?.methods?.getMediaSource(
                            musicItem,
                            quality,
                        )) ?? null;
                    // 5.3.1 获取到真实源
                    if (source) {
                        this.setQuality(quality);
                        break;
                    }
                } else {
                    // 5.3.2 已经切换到其他歌曲了，
                    return;
                }
            }

            if (!this.isCurrentMusic(musicItem)) {
                return;
            }
            if (!source) {
                // 如果有source
                if (musicItem.source) {
                    for (let quality of qualityOrder) {
                        if (musicItem.source[quality]?.url) {
                            source = musicItem.source[quality]!;
                            this.setQuality(quality);

                            break;
                        }
                    }
                }
                // 5.4 没有返回源
                if (!source && !musicItem.url) {
                    // 插件失效的情况
                    if (this.configService.getConfig("basic.tryChangeSourceWhenPlayFail")) {
                        // 重试
                        const similarMusic = await this.getSimilarMusic(
                            musicItem,
                            "music",
                            () => !this.isCurrentMusic(musicItem),
                        );

                        if (similarMusic) {
                            const similarMusicPlugin =
                                this.pluginManagerService.getByMedia(similarMusic);

                            for (let quality of qualityOrder) {
                                if (this.isCurrentMusic(musicItem)) {
                                    source =
                                        (await similarMusicPlugin?.methods?.getMediaSource(
                                            similarMusic,
                                            quality,
                                        )) ?? null;
                                    // 5.4.1 获取到真实源
                                    if (source) {
                                        this.setQuality(quality);
                                        break;
                                    }
                                } else {
                                    // 5.4.2 已经切换到其他歌曲了，
                                    return;
                                }
                            }
                        }

                        if (!source) {
                            throw new Error(PlayFailReason.INVALID_SOURCE);
                        }
                    } else {
                        throw new Error(PlayFailReason.INVALID_SOURCE);
                    }
                } else {
                    source = {
                        url: musicItem.url,
                    };
                    this.setQuality("standard");
                }
            }

            // 6. 特殊类型源：.m3u8 在 toMediaItem 里标 mimeType
            // 'application/x-mpegURL'（v5 的 MediaItem 没有 type 字段）。
            // 7. 合并结果
            track = this.mergeTrackSource(musicItem, source) as IMusic.IMusicItem;

            // 8. 新增历史记录
            this.musicHistoryService.addMusic(musicItem);

            trace("获取音源成功", track);
            // 9. 设置音源
            await this.setTrackSource(track);

            // 10. 获取补充信息
            let info: Partial<IMusic.IMusicItem> | null = null;
            try {
                info =
                    (await plugin?.methods?.getMusicInfo?.(musicItem)) ?? null;
                if (
                    (typeof info?.url === "string" && info.url.trim() === "") ||
                    (info?.url && typeof info.url !== "string")
                ) {
                    delete info.url;
                }
            } catch { }

            // 11. 设置补充信息
            if (info && this.isCurrentMusic(musicItem)) {
                const mergedTrack = this.mergeTrackSource(track, info);
                getDefaultStore().set(currentMusicAtom, mergedTrack as IMusic.IMusicItem);
                ReactNativeTrackPlayer.updateMetadata(
                    0,
                    this.toMediaMetadata(mergedTrack),
                );
            }
        } catch (e: any) {
            const message = e?.message;
            if (
                typeof message === "string" &&
                /setupPlayer|not initialized/i.test(message)
            ) {
                // v5 不再抛 v4 那句固定文案；只要报错提到 setupPlayer /
                // 未初始化，就重建一次播放器再重试（v5 的 setupPlayer
                // 重复调用会被忽略，不会抛“已初始化”）。
                ReactNativeTrackPlayer.setupPlayer();
                this.play(musicItem, forcePlay);
            } else if (message === PlayFailReason.FORBID_CELLUAR_NETWORK_PLAY) {
                if (getCurrentDialog()?.name !== "SimpleDialog") {
                    showDialog("SimpleDialog", {
                        title: "流量提醒",
                        content:
                            "当前非WIFI环境，侧边栏设置中打开【使用移动网络播放】功能后可继续播放",
                    });
                }
            } else if (message === PlayFailReason.INVALID_SOURCE) {
                trace("音源为空，播放失败");
                await this.handlePlayFail();
            } else if (message === PlayFailReason.PLAY_LIST_IS_EMPTY) {
                // 队列是空的，不应该出现这种情况
            }
        }
    }

    async pause(): Promise<void> {
        await ReactNativeTrackPlayer.pause();
    }

    toggleRepeatMode(): void {
        this.setRepeatMode(TrackPlayer.toggleRepeatMapping[this.repeatMode]);
    }

    // 清空播放队列
    async clearPlayList(): Promise<void> {
        this.setPlayList([]);
        this.setCurrentMusic(null);

        await this.reset();
        PersistStatus.set("music.musicItem", undefined);
        PersistStatus.set("music.progress", 0);
    }

    async skipToNext(): Promise<void> {
        if (this.isPlayListEmpty()) {
            this.setCurrentMusic(null);
            return;
        }

        await this.play(this.getPlayListMusicAt(this.currentIndex + 1), true);
    }

    async skipToPrevious(): Promise<void> {
        if (this.isPlayListEmpty()) {
            this.setCurrentMusic(null);
            return;
        }

        await this.play(
            this.getPlayListMusicAt(this.currentIndex === -1 ? 0 : this.currentIndex - 1),
            true,
        );
    }

    async changeQuality(newQuality: IMusic.IQualityKey): Promise<boolean> {
        // 获取当前的音乐和进度
        if (newQuality === this.quality) {
            return true;
        }

        // 获取当前歌曲
        const musicItem = this.currentMusic;
        if (!musicItem) {
            return false;
        }
        try {
            const progress = ReactNativeTrackPlayer.getProgress();
            const plugin = this.pluginManagerService.getByMedia(musicItem);
            const newSource = await plugin?.methods?.getMediaSource(
                musicItem,
                newQuality,
            );
            if (!newSource?.url) {
                throw new Error(PlayFailReason.INVALID_SOURCE);
            }
            if (this.isCurrentMusic(musicItem)) {
                const playingState = toMusicState(
                    ReactNativeTrackPlayer.getPlaybackState(),
                    ReactNativeTrackPlayer.isPlaying(),
                );
                await this.setTrackSource(
                    this.mergeTrackSource(
                        musicItem,
                        newSource,
                    ) as IMusic.IMusicItem,
                    !musicIsPaused(playingState),
                );

                await this.seekTo(progress.position ?? 0);
                this.setQuality(newQuality);
            }
            return true;
        } catch {
            // 修改失败
            return false;
        }
    }

    async playWithReplacePlayList(
        musicItem: IMusic.IMusicItem,
        newPlayList: IMusic.IMusicItem[],
    ): Promise<void> {
        if (newPlayList.length !== 0) {
            const now = Date.now();
            if (newPlayList.length > TrackPlayer.maxMusicQueueLength) {
                newPlayList = this.shrinkPlayListToSize(
                    newPlayList,
                    newPlayList.findIndex(it => isSameMediaItem(it, musicItem)),
                );
            }

            newPlayList.forEach((it, index) => {
                it[timeStampSymbol] = now;
                it[sortIndexSymbol] = index;
            });

            this.setPlayList(
                this.repeatMode === MusicRepeatMode.SHUFFLE
                    ? shuffle(newPlayList)
                    : newPlayList,
            );
            await this.play(musicItem, true);
        }
    }

    async seekTo(progress: number) {
        PersistStatus.set("music.progress", progress);
        return ReactNativeTrackPlayer.seekTo(progress);
    }

    // v5 的 getter / setter 都是同步的；接口要求 Promise，包一层 async。
    getProgress = async () => ReactNativeTrackPlayer.getProgress();
    getRate = async () => ReactNativeTrackPlayer.getPlaybackSpeed();
    setRate = async (rate: number) => {
        ReactNativeTrackPlayer.setPlaybackSpeed(rate);
    };
    // v5 没有 reset()：stop 停播并回到开头 + clear 清空队列，
    // 等价于 v4 reset()（定时关闭等处依赖它）。
    reset = async () => {
        ReactNativeTrackPlayer.stop();
        ReactNativeTrackPlayer.clear();
    };


    /**************** 辅助函数 -- 设置内部状态 ****************/

    private setCurrentMusic(musicItem?: IMusic.IMusicItem | null) {
        // 设置UI内部状态的musicitem
        if (!musicItem) {
            this.currentIndex = -1;
            getDefaultStore().set(currentMusicAtom, null);
            PersistStatus.set("music.musicItem", undefined);
            PersistStatus.set("music.progress", 0);

            this.emit(TrackPlayerEvents.CurrentMusicChanged, null);
            return;
        }
        if (typeof musicItem.artwork !== "string") {
            musicItem.artwork = ImgAsset.albumDefault;
        }
        this.currentIndex = this.getMusicIndexInPlayList(musicItem);
        getDefaultStore().set(currentMusicAtom, musicItem);

        this.emit(TrackPlayerEvents.CurrentMusicChanged, musicItem);
    }

    private setRepeatMode(mode: MusicRepeatMode) {
        const playList = this.playList;
        let newPlayList: IMusic.IMusicItem[];
        const prevMode = getDefaultStore().get(repeatModeAtom);
        if (
            (prevMode === MusicRepeatMode.SHUFFLE &&
                mode !== MusicRepeatMode.SHUFFLE) ||
            (mode === MusicRepeatMode.SHUFFLE &&
                prevMode !== MusicRepeatMode.SHUFFLE)
        ) {
            if (mode === MusicRepeatMode.SHUFFLE) {
                newPlayList = shuffle(playList);
            } else {
                newPlayList = this.sortByTimestampAndIndex(playList, true);
            }
            this.setPlayList(newPlayList);
        }

        getDefaultStore().set(repeatModeAtom, mode);
        // 更新下一首歌的信息（队列第 2 项即 fake 曲目）。
        // 注意：本 App 从不用原生 repeat mode（循环全靠 fake 曲目机制），
        // 所以这里不需要调 v5 的 setRepeatMode。
        ReactNativeTrackPlayer.updateMetadata(
            1,
            this.toMediaMetadata(this.getFakeNextTrack()),
        );
        // 记录
        PersistStatus.set("music.repeatMode", mode);
    }

    private setQuality(quality: IMusic.IQualityKey) {
        getDefaultStore().set(qualityAtom, quality);
        PersistStatus.set("music.quality", quality);
    }

    // 设置音源
    private async setTrackSource(track: IMusic.IMusicItem, autoPlay = true) {
        const mediaItem = this.toMediaItem(track);
        if (!mediaItem) {
            return;
        }
        ReactNativeTrackPlayer.setMediaItems([
            mediaItem,
            this.toMediaItem(this.getFakeNextTrack()),
        ]);
        PersistStatus.set("music.musicItem", track);
        PersistStatus.set("music.progress", 0);
        if (autoPlay) {
            ReactNativeTrackPlayer.play();
        }
    }

    /**
     * 设置播放队列
     * @param newPlayList 播放队列
     * @param persist 是否持久化
     */
    private setPlayList(newPlayList: IMusic.IMusicItem[], persist = true) {
        getDefaultStore().set(playListAtom, newPlayList);

        this.playListIndexMap = createMediaIndexMap(newPlayList);

        if (persist) {
            PersistStatus.set("music.playList", newPlayList);
        }

        this.currentIndex = this.getMusicIndexInPlayList(this.currentMusic);
    }


    /**************** 辅助函数 -- 工具方法 ****************/
    private shrinkPlayListToSize = (
        queue: IMusic.IMusicItem[],
        targetIndex = this.currentIndex,
    ) => {
        // 播放列表上限，太多无法缓存状态
        if (queue.length > TrackPlayer.maxMusicQueueLength) {
            if (targetIndex < TrackPlayer.halfMaxMusicQueueLength) {
                queue = queue.slice(0, TrackPlayer.maxMusicQueueLength);
            } else {
                const right = Math.min(
                    queue.length,
                    targetIndex + TrackPlayer.halfMaxMusicQueueLength,
                );
                const left = Math.max(0, right - TrackPlayer.maxMusicQueueLength);
                queue = queue.slice(left, right);
            }
        }
        return queue;
    };

    private mergeTrackSource(
        mediaItem: ICommon.IMediaBase,
        props: Record<string, any> | undefined,
    ) {
        return props
            ? {
                ...mediaItem,
                ...props,
                id: mediaItem.id,
                platform: mediaItem.platform,
            }
            : mediaItem;
    }

    private sortByTimestampAndIndex(array: any[], newArray = false) {
        if (newArray) {
            array = [...array];
        }
        return array.sort((a, b) => {
            const ts = a[timeStampSymbol] - b[timeStampSymbol];
            if (ts !== 0) {
                return ts;
            }
            return a[sortIndexSymbol] - b[sortIndexSymbol];
        });
    }

    private getFakeNextTrack(): IMusic.IMusicItem {
        let track: IMusic.IMusicItem | null;
        const repeatMode = this.repeatMode;
        if (repeatMode === MusicRepeatMode.SINGLE) {
            // 单曲循环
            track = this.getPlayListMusicAt(this.currentIndex);
        } else {
            // 下一曲
            track = this.getPlayListMusicAt(this.currentIndex + 1);
        }

        if (track) {
            return produce(track, _ => {
                _.url = TrackPlayer.fakeAudioUrl;
                _.$ = internalFakeSoundKey;
                _.artwork = resolveImportedAssetOrPath(ImgAsset.albumDefault) as unknown as any;
            });
        } else {
            // 只有列表长度为0时才会出现的特殊情况
            return {
                url: TrackPlayer.fakeAudioUrl,
                $: internalFakeSoundKey,
            } as IMusic.IMusicItem;
        }
    }


    private async handlePlayFail() {
        // 如果自动跳转下一曲, 500s后自动跳转
        if (!this.configService.getConfig("basic.autoStopWhenError")) {
            await delay(500);
            await this.skipToNext();
        }
    }

    /**
 *
 * @param musicItem 音乐类型
 * @param type 媒体类型
 * @param abortFunction 如果函数为true，则中断
 * @returns
 */
    private async getSimilarMusic<T extends ICommon.SupportMediaType>(
        musicItem: IMusic.IMusicItem,
        type: T = "music" as T,
        abortFunction?: () => boolean,
    ): Promise<ICommon.SupportMediaItemBase[T] | null> {
        const keyword = musicItem.alias || musicItem.title;
        const plugins = this.pluginManagerService.getSearchablePlugins(type);

        let distance = Infinity;
        let minDistanceMusicItem;
        let targetPlugin;

        const startTime = Date.now();

        for (let plugin of plugins) {
            // 超时时间：8s
            if (abortFunction?.() || Date.now() - startTime > 8000) {
                break;
            }
            if (plugin.name === musicItem.platform) {
                continue;
            }
            const results = await plugin.methods
                .search(keyword, 1, type)
                .catch(() => null);

            // 取前两个
            const firstTwo = results?.data?.slice(0, 2) || [];

            for (let item of firstTwo) {
                if (item.title === keyword && item.artist === musicItem.artist) {
                    distance = 0;
                    minDistanceMusicItem = item;
                    targetPlugin = plugin;
                    break;
                } else {
                    const dist =
                        minDistance(keyword, musicItem.title) +
                        minDistance(item.artist, musicItem.artist);
                    if (dist < distance) {
                        distance = dist;
                        minDistanceMusicItem = item;
                        targetPlugin = plugin;
                    }
                }
            }

            if (distance === 0) {
                break;
            }
        }
        if (minDistanceMusicItem && targetPlugin) {
            return minDistanceMusicItem as ICommon.SupportMediaItemBase[T];
        }

        return null;
    }


    /**
     * 把 App 内部的曲目对象转成 v5 的 MediaItem。
     * v4 是把 IMusicItem 直接当 Track 用的（字段名 artwork / album /
     * headers / type）；v5 的字段名不同，必须显式映射：
     * - artwork → artworkUrl，album → albumTitle
     *   （artwork 不能为 null，部分情况下不能是 ImageSource 类型，
     *   所以这里和原来一样先经 resolveImportedAssetOrPath 解析）
     * - headers 放进 url 对象 {uri, headers}
     * - .m3u8 → mimeType 'application/x-mpegURL'（v4 的 type: "hls"）
     * - platform / id / isInit / $ 只存在于 extras 里：原生侧只存
     *   MediaItem 的定型字段，读回时靠 extras 还原比对。
     */
    private toMediaItem(item: IMusic.IMusicItem): MediaItem {
        const rawUrl = item.url ?? "";
        const headers = (item as any).headers as
            | Record<string, string>
            | undefined;
        const isHls =
            getUrlExt(rawUrl) === ".m3u8" || (item as any).type === "hls";
        return {
            ...this.toMediaMetadata(item),
            mediaId:
                rawUrl === TrackPlayer.fakeAudioUrl
                    ? TrackPlayer.fakeAudioUrl
                    : `${item.platform}:${item.id}`,
            url: headers ? { uri: rawUrl, headers } : rawUrl,
            duration: item.duration,
            mimeType: isHls ? "application/x-mpegURL" : undefined,
            extras: {
                platform: item.platform,
                id: item.id,
                isInit: (item as any).isInit ?? undefined,
                isFake:
                    (item as any).$ === internalFakeSoundKey
                        ? true
                        : undefined,
            },
        };
    }

    /** 从曲目对象取 v5 updateMetadata 接受的四个展示字段。 */
    private toMediaMetadata(item: IMusic.IMusicItem): {
        title?: string;
        artist?: string;
        albumTitle?: string;
        artworkUrl?: MediaItem["artworkUrl"];
    } {
        return {
            title: item.title,
            artist: item.artist,
            albumTitle: item.album,
            artworkUrl: resolveImportedAssetOrPath(
                item.artwork?.trim?.()?.length
                    ? item.artwork
                    : ImgAsset.albumDefault,
            ) as unknown as MediaItem["artworkUrl"],
        };
    }

    /**
     * 把 v5 读回的 MediaItem 还原成 App 内部的曲目对象
     *（仅用于比对 / 重设音源；platform / id 存在 extras 里）。
     */
    private mediaItemToMusicItem(
        item: MediaItem | null | undefined,
    ): IMusic.IMusicItem | null {
        if (!item) {
            return null;
        }
        return {
            id: (item.extras?.id as string) ?? "",
            platform: (item.extras?.platform as string) ?? "",
            url: mediaUrlString(item.url) ?? "",
            title: item.title ?? "",
            artist: item.artist ?? "",
            album: item.albumTitle ?? "",
            artwork: item.artworkUrl as unknown as string,
            duration: item.duration ?? 0,
        } as IMusic.IMusicItem;
    }

}

export const usePlayList = () => useAtomValue(playListAtom);
export const useCurrentMusic = () => useAtomValue(currentMusicAtom);
export const useRepeatMode = () => useAtomValue(repeatModeAtom);
export const useMusicQuality = () => useAtomValue(qualityAtom);
export function useMusicState() {
    // v5 的 usePlaybackState() 直接返回 PlaybackState（没有 .state），
    // 且“是否在播”要另外看 useIsPlaying()；两者一起映射回 v4 语义的 State。
    const playbackState = usePlaybackState();
    const isPlaying = useIsPlaying();

    return toMusicState(playbackState, isPlaying);
}
export { State as MusicState, useProgress };

enum PlayFailReason {
    /** 禁止移动网络播放 */
    FORBID_CELLUAR_NETWORK_PLAY = "FORBID_CELLUAR_NETWORK_PLAY",
    /** 播放列表为空 */
    PLAY_LIST_IS_EMPTY = "PLAY_LIST_IS_EMPTY",
    /** 无效源 */
    INVALID_SOURCE = "INVALID_SOURCE",
    /** 非当前音乐 */
}

const trackPlayer = new TrackPlayer();
export default trackPlayer;