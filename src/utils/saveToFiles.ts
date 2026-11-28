import { NativeModules } from "react-native";

type FileSaverModule = {
    saveFile?: (filePath: string) => Promise<string>;
    copyFileToURL?: (sourcePath: string, destURL: string) => Promise<boolean>;
};

/**
 * 用苹果自带的文件管理器保存一个文件：弹出 UIDocumentPickerViewController
 *（导出模式），上面有 Save 按钮，下面有 Save as 文件名，用户自选目录。
 * 返回用户选的目标位置（file:// URL 字符串）；取消 / 模块不可用 / 出错
 * 返回 null。调用方用返回值是否为空判断用户有没有点保存。
 * asCopy:YES，App 自己那份还在，不影响离线播放。
 */
export async function saveFileToFiles(filePath: string): Promise<string | null> {
    try {
        const mod = (NativeModules as Record<string, unknown>).FileSaver as
            | FileSaverModule
            | undefined;
        if (!mod?.saveFile) {
            return null;
        }
        const dest = await mod.saveFile(filePath);
        return dest ? dest : null;
    } catch {
        return null;
    }
}

/** 把已下载好的文件写进用户在保存框里选的位置（覆盖占位空文件）。 */
export async function copyFileToPickedURL(
    sourcePath: string,
    destURL: string,
): Promise<boolean> {
    try {
        const mod = (NativeModules as Record<string, unknown>).FileSaver as
            | FileSaverModule
            | undefined;
        if (!mod?.copyFileToURL) {
            return false;
        }
        return !!(await mod.copyFileToURL(sourcePath, destURL));
    } catch {
        return false;
    }
}
