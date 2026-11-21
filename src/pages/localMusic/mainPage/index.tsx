import React from "react";
import LocalMusicSheet from "@/core/localMusicSheet";
import { ROUTE_PATH, useNavigate } from "@/core/router";
import LocalMusicList from "./localMusicList";
import MusicBar from "@/components/musicBar";
import { localMusicSheetId } from "@/constants/commonConst";
import Toast from "@/utils/toast";
import { showDialog } from "@/components/dialogs/useDialog";
import AppBar from "@/components/base/appBar";
import { useI18N } from "@/core/i18n";
import { Platform } from "react-native";
import { getDocumentAsync } from "expo-document-picker";
import {
    DocumentDirectoryPath,
    copyFile,
    exists,
} from "react-native-fs";
import {
    checkAndCreateDir,
    getFileName,
    openInFilesApp,
} from "@/utils/fileUtils";

export default function MainPage() {
    const navigate = useNavigate();
    const { t } = useI18N();

    return (
        <>
            <AppBar
                withStatusBar
                actions={[
                    {
                        icon: "magnifying-glass",
                        onPress() {
                            navigate(ROUTE_PATH.SEARCH_MUSIC_LIST, {
                                musicList: LocalMusicSheet.getMusicList(),
                            });
                        },
                    },
                ]}
                menu={[
                    {
                        icon: "magnifying-glass",
                        title: t("localMusic.scanLocalMusic"),
                        async onPress() {
                            navigate(ROUTE_PATH.FILE_SELECTOR, {
                                fileType: "folder",
                                multi: true,
                                actionText: t("localMusic.beginScan"),
                                async onAction(selectedFiles) {
                                    return new Promise(resolve => {
                                        showDialog("LoadingDialog", {
                                            title: t("localMusic.scanLocalMusic"),
                                            promise:
                                                LocalMusicSheet.importLocal(
                                                    selectedFiles.map(
                                                        _ => _.path,
                                                    ),
                                                ),
                                            onResolve(data, hideDialog) {
                                                Toast.success(t("toast.importSuccess"));
                                                hideDialog();
                                                resolve(true);
                                            },
                                            onCancel(hideDialog) {
                                                LocalMusicSheet.cancelImportLocal();
                                                hideDialog();
                                                resolve(false);
                                            },
                                        });
                                    });
                                },
                            });
                        },
                    },
                    {
                        icon: "document-outline",
                        title: t("localMusic.importAudioFiles"),
                        show: Platform.OS === "ios",
                        async onPress() {
                            try {
                                const pickResult =
                                    await getDocumentAsync({
                                        type: "audio/*",
                                        multiple: true,
                                        copyToCacheDirectory: true,
                                    });
                                if (pickResult.canceled) {
                                    return;
                                }
                                // 导入的文件要长期保存：放到 Documents/imported，
                                // 既不会被系统清理，也能在“文件”App 里看到
                                const importedDir = `${DocumentDirectoryPath}/imported`;
                                await checkAndCreateDir(importedDir);
                                const paths: string[] = [];
                                for (const asset of pickResult.assets) {
                                    const fileName =
                                        asset.name ??
                                        getFileName(asset.uri);
                                    const src = asset.uri.replace(
                                        /^file:\/\//,
                                        "",
                                    );
                                    // 文件本来就在 Documents 里，直接原地导入，不复制
                                    if (
                                        src.startsWith(
                                            DocumentDirectoryPath,
                                        )
                                    ) {
                                        paths.push(src);
                                        continue;
                                    }
                                    let dest = `${importedDir}/${fileName}`;
                                    // 同名文件重命名，避免覆盖
                                    let n = 2;
                                    const dot =
                                        fileName.lastIndexOf(".");
                                    const stem =
                                        dot === -1
                                            ? fileName
                                            : fileName.slice(0, dot);
                                    const ext =
                                        dot === -1
                                            ? ""
                                            : fileName.slice(dot);
                                    while (await exists(dest)) {
                                        dest = `${importedDir}/${stem} (${n})${ext}`;
                                        n += 1;
                                    }
                                    await copyFile(src, dest);
                                    paths.push(dest);
                                }
                                if (!paths.length) {
                                    return;
                                }
                                return new Promise(resolve => {
                                    showDialog("LoadingDialog", {
                                        title: t(
                                            "localMusic.scanLocalMusic",
                                        ),
                                        promise:
                                            LocalMusicSheet.importLocal(
                                                paths,
                                            ),
                                        onResolve(data, hideDialog) {
                                            Toast.success(
                                                t("toast.importSuccess"),
                                            );
                                            hideDialog();
                                            resolve(true);
                                        },
                                        onCancel(hideDialog) {
                                            LocalMusicSheet.cancelImportLocal();
                                            hideDialog();
                                            resolve(false);
                                        },
                                    });
                                });
                            } catch (e: any) {
                                Toast.warn(t("toast.importFailed"));
                            }
                        },
                    },
                    {
                        icon: "pencil-square",
                        title: t("common.batchEdit"),
                        async onPress() {
                            navigate(ROUTE_PATH.MUSIC_LIST_EDITOR, {
                                musicList: LocalMusicSheet.getMusicList(),
                                musicSheet: {
                                    id: localMusicSheetId,
                                },
                            });
                        },
                    },
                    {
                        icon: "folder-outline",
                        title: t("basicSettings.openInFilesApp"),
                        show: Platform.OS === "ios",
                        async onPress() {
                            const ok = await openInFilesApp();
                            if (!ok) {
                                Toast.warn(
                                    t("toast.cannotOpenFilesApp"),
                                );
                            }
                        },
                    },
                    {
                        icon: "arrow-down-tray",
                        title: t("localMusic.downloadList"),
                        async onPress() {
                            navigate(ROUTE_PATH.DOWNLOADING);
                        },
                    },
                ]}>
                {t("home.localMusic")}
            </AppBar>
            <LocalMusicList />
            <MusicBar />
        </>
    );
}
