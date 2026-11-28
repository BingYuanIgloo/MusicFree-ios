#!/usr/bin/env python3
"""Fix run54: island stuck/delay/lock-screen/UI + theme light + quality/rate text + Files picker.

Applies to master (2fe34acb). Run from repo root.
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
    # newline=None keeps the file's own line endings for CRLF files
    # when we pass the raw content back; for LF files use "\n".
    full = os.path.join(ROOT, path)
    with open(full, "w", encoding="utf-8", newline=newline) as f:
        f.write(content)

def replace(path, old, new, count=1):
    content = read(path)
    if old not in content:
        print(f"FAIL: pattern not found in {path}:\n{old[:200]}")
        sys.exit(1)
    content = content.replace(old, new, count)
    write(path, content)
    print(f"OK: {path}")

def replace_crlf(path, old, new, count=1):
    """Edit a CRLF file, preserving CRLF line endings.
    The file is read with \r\n intact; normalize to \n for matching
    (the patterns in this script use \n), then convert back to \r\n.
    """
    content = read(path)
    normalized = content.replace("\r\n", "\n")
    if old not in normalized:
        print(f"FAIL: pattern not found in {path}:\n{old[:200]}")
        sys.exit(1)
    normalized = normalized.replace(old, new, count)
    content = normalized.replace("\n", "\r\n")
    # write back with newline="" so \r\n is preserved as-is.
    write(path, content, newline="")
    print(f"OK: {path} (CRLF preserved)")

# ---------------------------------------------------------------- 1. Module.swift
# (a) staleDate 30 min -> 2 min in startActivity, so a killed app's
# island expires quickly instead of lingering half an hour.
# (b) updateActivity: staleDate nil -> 2 min (same reason).
# (c) Remove clearNowPlayingInfo (it wipes the lock-screen Now Playing
# card) and the now-unused MediaPlayer import.
# ----------------------------------------------------------------
replace(
    "ios/MusicFreeWidgets/Module.swift",
    """import ExpoModulesCore
import ActivityKit
import MediaPlayer""",
    """import ExpoModulesCore
import ActivityKit""",
)
replace(
    "ios/MusicFreeWidgets/Module.swift",
    """                // 30 分钟后标记为过期：App 异常退出时系统能及时收起活动。
                let staleDate = Calendar.current.date(
                    byAdding: .minute, value: 30, to: Date()
                )""",
    """                // 2 分钟后标记为过期：App 被杀掉后灵动岛很快消失；
                // 活着时每次歌词更新都会把过期时间往后推，不会误杀。
                let staleDate = Calendar.current.date(
                    byAdding: .minute, value: 2, to: Date()
                )""",
)
replace(
    "ios/MusicFreeWidgets/Module.swift",
    """                let updatedContent = ActivityContent(
                    state: contentState, staleDate: nil)""",
    """                // 更新也带 2 分钟过期时间：App 被杀掉后不再更新，
                // 活动很快过期消失；活着时下次更新会续期。
                let staleDate = Calendar.current.date(
                    byAdding: .minute, value: 2, to: Date()
                )
                let updatedContent = ActivityContent(
                    state: contentState, staleDate: staleDate)""",
)
replace(
    "ios/MusicFreeWidgets/Module.swift",
    """
        /// 把系统 Now Playing（MPNowPlayingInfoCenter）清掉，系统就
        /// 不再单独占一个音频灵动岛。歌词岛自己带播放按钮，就是
        /// 唯一的岛；锁屏上歌词 Live Activity 横幅（带按钮）顶上
        /// 系统媒体控制。播放器每次切歌 / 改状态都可能重设
        /// NowPlayingInfo，所以 JS 侧在每次同步歌词岛时都调一次。
        Function("clearNowPlayingInfo") { () -> Void in
            MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
        }
""",
    "",
)

# ---------------------------------------------------------------- 2. liveActivityLyrics.ts
# (a) getModule(): fall back to NativeModules (classic bridge) when
# expo-modules-core's requireOptionalNativeModule returns null.
# The headless JS task (background lyric sync) does not always have
# the Expo module registry, so the old lookup silently no-op'd and
# background lyrics never updated (stuck until the app was foregrounded).
# (b) Remove clearNowPlayingInfo (see Module.swift).
# ----------------------------------------------------------------
replace(
    "src/core/liveActivityLyrics.ts",
    """import { requireOptionalNativeModule } from "expo-modules-core";""",
    """import { requireOptionalNativeModule } from "expo-modules-core";
import { NativeModules } from "react-native";""",
)
replace(
    "src/core/liveActivityLyrics.ts",
    """ *   startActivity(title, artist, currentLine, nextLine, startedAtMs, durationSec, isPlaying)
 *   updateActivity(currentLine, nextLine, startedAtMs, durationSec, isPlaying)
 *   endActivity()
 *   clearNowPlayingInfo()
 *""",
    """ *   startActivity(title, artist, currentLine, nextLine, startedAtMs, durationSec, isPlaying)
 *   updateActivity(currentLine, nextLine, startedAtMs, durationSec, isPlaying)
 *   endActivity()
 *""",
)
replace(
    "src/core/liveActivityLyrics.ts",
    """    endActivity: () => void;
    clearNowPlayingInfo: () => void;
}""",
    """    endActivity: () => void;
}""",
)
replace(
    "src/core/liveActivityLyrics.ts",
    """function getModule(): IWidgetExtensionModule | null {
    if (cachedModule !== undefined) {
        return cachedModule;
    }
    try {
        cachedModule =
            requireOptionalNativeModule<IWidgetExtensionModule>(
                "ReactNativeWidgetExtension",
            ) ?? null;
    } catch {
        cachedModule = null;
    }
    return cachedModule;
}""",
    """function getModule(): IWidgetExtensionModule | null {
    if (cachedModule !== undefined) {
        return cachedModule;
    }
    try {
        cachedModule =
            requireOptionalNativeModule<IWidgetExtensionModule>(
                "ReactNativeWidgetExtension",
            ) ?? null;
    } catch {
        cachedModule = null;
    }
    // 后台 headless 任务里 Expo 的模块注册表不一定可用，
    // requireOptionalNativeModule 会返回 null，导致后台歌词
    // 同步静默失败（歌词卡住、只在切回前台才刷新）。
    // 退到经典 NativeModules 桥：原生模块在 headless 任务里
    // 同样注册着，可以直接拿到。
    if (!cachedModule) {
        try {
            const nm = (NativeModules as Record<string, unknown>)
                .ReactNativeWidgetExtension as
                | IWidgetExtensionModule
                | undefined;
            cachedModule = nm ?? null;
        } catch {
            cachedModule = null;
        }
    }
    return cachedModule;
}""",
)
replace(
    "src/core/liveActivityLyrics.ts",
    """
/** 清掉系统 Now Playing，让系统不再单独占一个音频灵动岛。 */
export function clearNowPlayingInfo(): void {
    try {
        getModule()?.clearNowPlayingInfo();
    } catch {
        // 模块缺失时静默 no-op。
    }
}

""",
    "",
)

# ---------------------------------------------------------------- 3. lyricManager.ts
# Stop clearing Now Playing on every lyric sync: it wipes
# MPNowPlayingInfoCenter, so the lock-screen media card is left
# empty (no artwork/title, just a bare playback box).
# ----------------------------------------------------------------
replace(
    "src/core/lyricManager.ts",
    """import {
    clearNowPlayingInfo,
    endLyricsLiveActivity,
    startLyricsLiveActivity,
} from "@/core/liveActivityLyrics";""",
    """import {
    endLyricsLiveActivity,
    startLyricsLiveActivity,
} from "@/core/liveActivityLyrics";""",
)
replace(
    "src/core/lyricManager.ts",
    """        // 每次同步都清一次系统 Now Playing：播放器切歌 / 改状态时
        // 会重设 NowPlayingInfo，系统音频岛就又冒出来；清掉它，
        // 歌词岛才是唯一的岛。
        clearNowPlayingInfo();

        // 每次都走 start：原生 startActivity 已在内部处理“已有活动则更新”，""",
    """        // 不再清系统 Now Playing：清掉它会把锁屏媒体卡也清空
        //（只剩一个空播放框，没有封面/歌名）。歌词岛本身就是
        // 唯一的岛（原生 startActivity 只更新已有活动，不再新建）。

        // 每次都走 start：原生 startActivity 已在内部处理“已有活动则更新”，""",
)

# ---------------------------------------------------------------- 4. LyricsLiveActivity.swift
# Center the playback buttons (QQ/NetEase style): they sit in a
# leading-aligned VStack, so they hug the left edge. Give the HStack
# a full-width centered frame in BOTH the lock-screen banner and
# the expanded island bottom. Also add a little more breathing room.
# ----------------------------------------------------------------
# Lock-screen banner buttons.
replace(
    "ios/MusicFreeWidgets/LyricsLiveActivity.swift",
    """/// 系统音频岛由 Module.clearNowPlayingInfo() 清掉，不再单独出现。""",
    """/// 不再清系统 Now Playing：清掉它会把锁屏媒体卡也清空
///（只剩空播放框）。歌词岛本身就是唯一的岛。""",
)
# Lock-screen banner buttons.
replace(
    "ios/MusicFreeWidgets/LyricsLiveActivity.swift",
    """                // 播放控制：上一首 / 播放暂停 / 下一首。点按经 URL Scheme
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
                .padding(.top, 6)""",
    """                // 播放控制：上一首 / 播放暂停 / 下一首。点按经 URL Scheme
                // 回主 App（见 liveActivityLinking.ts），不直接操作音频。
                // 居中（QQ/网易云式）：按钮组占满整行宽度再居中，
                // 否则 HStack 跟着外层 leading 对齐，全挤在左边。
                HStack(spacing: 32) {
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
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.top, 8)""",
)
# Expanded island bottom buttons.
replace(
    "ios/MusicFreeWidgets/LyricsLiveActivity.swift",
    """                // 播放控制：上一首 / 播放暂停 / 下一首。点按经 URL Scheme
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
                .padding(.top, 6)""",
    """                // 播放控制：上一首 / 播放暂停 / 下一首。点按经 URL Scheme
                // 回主 App（见 liveActivityLinking.ts），不直接操作音频。
                // 居中（QQ/网易云式）：按钮组占满整行宽度再居中。
                HStack(spacing: 32) {
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
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.top, 8)""",
)

# ---------------------------------------------------------------- 5. theme.ts — default to LIGHT
# The app opens dark by default (?? "p-dark" + initial darkTheme).
# User likes light mode and does not want a dark default.
# ----------------------------------------------------------------
replace(
    "src/core/theme.ts",
    """const themeStore = new GlobalState(darkTheme);""",
    """const themeStore = new GlobalState(lightTheme);""",
)
replace(
    "src/core/theme.ts",
    """    const currentTheme = Config.getConfig("theme.selectedTheme") ?? "p-dark";""",
    """    const currentTheme = Config.getConfig("theme.selectedTheme") ?? "p-light";""",
)

# ---------------------------------------------------------------- 6. operations.tsx (CRLF) — quality / rate as TEXT
# The quality badge ("超") and rate ("1.0x") are white PNGs; in light
# mode they stay white while neighbours turn dark. User: make them
# text, not images. Quality single chars: 低/标/高/超 (verified from
# the PNGs). Rate: 100 -> "1.0x", 50 -> "0.5x", 75 -> "0.75x", etc.
# ----------------------------------------------------------------
replace_crlf(
    "src/pages/musicDetail/components/content/albumCover/operations.tsx",
    """import { ImgAsset } from "@/constants/assetsConst";""",
    """import ThemeText from "@/components/base/themeText";""",
)
replace_crlf(
    "src/pages/musicDetail/components/content/albumCover/operations.tsx",
    """                <Image
                    source={ImgAsset.quality[currentQuality]}
                    style={styles.quality}
                />""",
    """                <ThemeText fontSize="title" fontWeight="semibold">
                    {qualityShortText[currentQuality]}
                </ThemeText>""",
)
replace_crlf(
    "src/pages/musicDetail/components/content/albumCover/operations.tsx",
    """                <Image source={ImgAsset.rate[rate!]} style={styles.quality} />""",
    """                <ThemeText fontSize="title" fontWeight="semibold">
                    {rateText}
                </ThemeText>""",
)
# Add the helpers + remove the now-unused quality style. Insert the
# helpers right after the imports, and drop the unused Image import.
replace_crlf(
    "src/pages/musicDetail/components/content/albumCover/operations.tsx",
    """import React, { useMemo } from "react";
import { Image, Pressable, StyleSheet, View } from "react-native";""",
    """import React, { useMemo } from "react";
import { Pressable, StyleSheet, View } from "react-native";""",
)
replace_crlf(
    "src/pages/musicDetail/components/content/albumCover/operations.tsx",
    """export default function Operations() {
    const musicItem = useCurrentMusic();""",
    """// 音质单字（原来是白色 PNG 图，浅色下看不清；改成文字后跟主题变色）。
const qualityShortText: Record<string, string> = {
    low: "低",
    standard: "标",
    high: "高",
    super: "超",
};

export default function Operations() {
    const musicItem = useCurrentMusic();""",
)
# rateText: compute from the persisted rate (default 100) inside the
# component, right after `const rate = ...`.
replace_crlf(
    "src/pages/musicDetail/components/content/albumCover/operations.tsx",
    """    const rate = PersistStatus.useValue("music.rate", 100);""",
    """    const rate = PersistStatus.useValue("music.rate", 100);
    const rateValue = rate ?? 100;
    const rateText =
        rateValue % 100 === 0
            ? `${rateValue / 100}.0x`
            : `${rateValue / 100}x`;""",
)
replace_crlf(
    "src/pages/musicDetail/components/content/albumCover/operations.tsx",
    """    quality: {
        width: rpx(52),
        height: rpx(52),
    },
});""",
    """});""",
)

# ---------------------------------------------------------------- 7. FileSaver native module (new files)
# Presents UIDocumentPickerViewController in EXPORT mode: the exact
# Apple Files picker the user screenshotted (blue Save top-right,
# "Save as" filename field, pick a folder). Used for music downloads
# and backup export. Import (pick a file) already uses
# expo-document-picker and stays as-is.
# ----------------------------------------------------------------
os.makedirs(os.path.join(ROOT, "ios/FileSaver"), exist_ok=True)
with open(os.path.join(ROOT, "ios/FileSaver/FileSaver.podspec"), "w", encoding="utf-8", newline="\n") as f:
    f.write(
        """Pod::Spec.new do |s|
  s.name             = 'FileSaver'
  s.version          = '1.0.0'
  s.summary          = 'Save a file via the iOS Files picker (UIDocumentPickerViewController export mode).'
  s.homepage         = 'https://example.com'
  s.license          = { :type => 'MIT' }
  s.author           = { 'MusicFree' => '' }
  s.source           = { :git => '', :tag => '1.0.0' }
  s.platform         = :ios, '13.0'
  s.source_files     = '*.{h,m}'
  s.dependency 'React-Core'
end
"""
    )
with open(os.path.join(ROOT, "ios/FileSaver/FileSaver.h"), "w", encoding="utf-8", newline="\n") as f:
    f.write(
        """#import <React/RCTBridgeModule.h>

@interface FileSaver : NSObject <RCTBridgeModule, UIDocumentPickerDelegate>
@end
"""
    )
with open(os.path.join(ROOT, "ios/FileSaver/FileSaver.m"), "w", encoding="utf-8", newline="\n") as f:
    f.write(
        """#import "FileSaver.h"
#import <React/RCTUtils.h>

@implementation FileSaver {
  RCTPromiseResolveBlock _resolve;
  RCTPromiseRejectBlock _reject;
}

RCT_EXPORT_MODULE(FileSaver);

RCT_EXPORT_METHOD(saveFile:(NSString *)filePath
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  _resolve = resolve;
  _reject = reject;
  dispatch_async(dispatch_get_main_queue(), ^{
    if (!filePath || ![[NSFileManager defaultManager] fileExistsAtPath:filePath]) {
      if (_reject) {
        _reject(@"ENOENT", @"File does not exist", nil);
        _resolve = nil;
        _reject = nil;
      }
      return;
    }
    NSURL *url = [NSURL fileURLWithPath:filePath];
    UIDocumentPickerViewController *picker = nil;
    if (@available(iOS 14.0, *)) {
      // asCopy:YES: the file is copied to the chosen location,
      // the app keeps its own copy (offline playback still works).
      picker = [[UIDocumentPickerViewController alloc] initForExportingURLs:@[url] asCopy:YES];
    } else {
      picker = [[UIDocumentPickerViewController alloc] initWithURLs:@[url] inMode:UIDocumentPickerModeExportToService];
    }
    picker.delegate = self;
    picker.modalPresentationStyle = UIModalPresentationFormSheet;
    UIViewController *root = RCTPresentedViewController();
    if (!root) {
      if (_reject) {
        _reject(@"NO_ROOT", @"No presenting view controller", nil);
        _resolve = nil;
        _reject = nil;
      }
      return;
    }
    [root presentViewController:picker animated:YES completion:nil];
  });
}

- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
  if (_resolve) {
    _resolve(@(YES));
    _resolve = nil;
    _reject = nil;
  }
}

- (void)documentPickerWasCancelled:(UIDocumentPickerViewController *)controller {
  if (_resolve) {
    _resolve(@(NO));
    _resolve = nil;
    _reject = nil;
  }
}

@end
"""
    )
print("OK: ios/FileSaver/* (new native module)")

# Podfile: add the local pod inside the main app target, right after
# use_expo_modules!.
replace(
    "ios/Podfile",
    """target 'MusicFree' do
  use_expo_modules!
""",
    """target 'MusicFree' do
  use_expo_modules!

  # 本地原生模块：苹果文件管理器保存（下载 / 备份导出用）。
  pod 'FileSaver', :path => './FileSaver'
""",
)

# ---------------------------------------------------------------- 8. JS wrapper src/utils/saveToFiles.ts (new file)
# ----------------------------------------------------------------
with open(os.path.join(ROOT, "src/utils/saveToFiles.ts"), "w", encoding="utf-8", newline="\n") as f:
    f.write(
        """import { NativeModules } from "react-native";

/**
 * 用苹果自带的文件管理器保存一个文件：弹出 UIDocumentPickerViewController
 *（导出模式），上面有 Save 按钮，下面有 Save as 文件名，用户自选目录。
 * 返回 true = 用户点了 Save，false = 取消 / 模块不可用 / 出错。
 * asCopy:YES，App 自己那份还在，不影响离线播放。
 */
export async function saveFileToFiles(filePath: string): Promise<boolean> {
    try {
        const mod = (NativeModules as Record<string, unknown>).FileSaver as
            | { saveFile?: (filePath: string) => Promise<boolean> }
            | undefined;
        if (!mod?.saveFile) {
            return false;
        }
        return !!(await mod.saveFile(filePath));
    } catch {
        return false;
    }
}
"""
    )
print("OK: src/utils/saveToFiles.ts (new)")

# ---------------------------------------------------------------- 9. downloader.ts
# (a) Toast when a download starts / fails (tapping download used to
# do nothing visible). (b) After a download completes, present the
# Apple Files picker so the user picks where to save it; the app
# keeps its own copy in download/music/ for offline playback.
# ----------------------------------------------------------------
replace(
    "src/core/downloader.ts",
    """import LocalMusicSheet from "./localMusicSheet";
import { IPluginManager } from "@/types/core/pluginManager";""",
    """import LocalMusicSheet from "./localMusicSheet";
import { IPluginManager } from "@/types/core/pluginManager";
import Toast from "@/utils/toast";
import { saveFileToFiles } from "@/utils/saveToFiles";""",
)
replace(
    "src/core/downloader.ts",
    """    download(musicItems: IMusic.IMusicItem | IMusic.IMusicItem[], quality?: IMusic.IQualityKey) {
        if (network.isOffline) {
            this.emit(DownloaderEvent.DownloadError, DownloadFailReason.NetworkOffline);
            return;
        }

        if (network.isCellular && !this.configService.getConfig("basic.useCelluarNetworkDownload")) {
            this.emit(DownloaderEvent.DownloadError, DownloadFailReason.NotAllowToDownloadInCellular);
            return;
        }""",
    """    download(musicItems: IMusic.IMusicItem | IMusic.IMusicItem[], quality?: IMusic.IQualityKey) {
        if (network.isOffline) {
            Toast.warn("当前无网络，无法下载");
            this.emit(DownloaderEvent.DownloadError, DownloadFailReason.NetworkOffline);
            return;
        }

        if (network.isCellular && !this.configService.getConfig("basic.useCelluarNetworkDownload")) {
            Toast.warn("当前为移动网络，已在设置中禁止移动网络下载");
            this.emit(DownloaderEvent.DownloadError, DownloadFailReason.NotAllowToDownloadInCellular);
            return;
        }""",
)
replace(
    "src/core/downloader.ts",
    """        if (!musicItems.length) {
            return;
        }

        // 添加进任务队列""",
    """        if (!musicItems.length) {
            return;
        }

        Toast.success("已开始下载，完成后会弹出文件管理器让你选保存位置");

        // 添加进任务队列""",
)
replace(
    "src/core/downloader.ts",
    """            this.markTaskAsCompleted(musicItem);
        } catch (e: any) {
            this.markTaskAsError(musicItem, DownloadFailReason.Unknown, e);
        }""",
    """            this.markTaskAsCompleted(musicItem);

            // 下完弹出苹果文件管理器（Save 按钮，自选目录）：
            // asCopy，App 自己那份还在 download/music/，离线播放不受影响。
            try {
                await saveFileToFiles(targetDownloadPath.replace(/^file:\\/\\//, ""));
            } catch {
                // 弹不出也不影响已下载的文件本身。
            }
        } catch (e: any) {
            Toast.warn("下载失败，无法获取到这首歌");
            this.markTaskAsError(musicItem, DownloadFailReason.Unknown, e);
        }""",
)

# ---------------------------------------------------------------- 10. backupSetting.tsx (CRLF) — iOS backup export via Files picker
# Replace Share.open (share sheet) with the direct Apple Files picker
# (Save button, pick a folder). Import (restore) already uses
# expo-document-picker and stays as-is.
# ----------------------------------------------------------------
replace_crlf(
    "src/pages/setting/settingTypes/backupSetting.tsx",
    """import { getDocumentAsync } from "expo-document-picker";
import Share from "react-native-share";
import { DocumentDirectoryPath } from "react-native-fs";""",
    """import { getDocumentAsync } from "expo-document-picker";
import { DocumentDirectoryPath } from "react-native-fs";
import { saveFileToFiles } from "@/utils/saveToFiles";""",
)
replace_crlf(
    "src/pages/setting/settingTypes/backupSetting.tsx",
    """    const onBackupToLocal = async () => {
        // iOS 沙盒内无法自选任意文件夹：改用系统分享单，
        // 用户可在“存储到‘文件’”里把备份存到手机任意位置。
        if (Platform.OS === "ios") {
            const raw = Backup.backup();
            const filePath = `${DocumentDirectoryPath}/backup.json`;
            try {
                await writeInChunks(filePath, raw);
            } catch (e: any) {
                Toast.warn(t("toast.backupFail", { reason: e?.message ?? e }));
                return;
            }
            try {
                await Share.open({
                    url: `file://${filePath}`,
                    type: "application/json",
                    filename: "backup.json",
                });
                Toast.success(t("toast.backupSuccess"));
            } catch {
                // 用户取消分享，不提示；备份已保存在应用 Documents 内
            }
            return;
        }""",
    """    const onBackupToLocal = async () => {
        // iOS：直接弹苹果文件管理器（Save 按钮，自选目录），
        // 不再走分享单。
        if (Platform.OS === "ios") {
            const raw = Backup.backup();
            const filePath = `${DocumentDirectoryPath}/backup.json`;
            try {
                await writeInChunks(filePath, raw);
            } catch (e: any) {
                Toast.warn(t("toast.backupFail", { reason: e?.message ?? e }));
                return;
            }
            const saved = await saveFileToFiles(filePath);
            if (saved) {
                Toast.success(t("toast.backupSuccess"));
            }
            // 用户取消也不提示；备份已保存在应用 Documents 内
            return;
        }""",
)

print("ALL FIX-RUN54 EDITS APPLIED")
