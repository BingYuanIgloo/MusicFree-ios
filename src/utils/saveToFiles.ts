import { NativeModules } from "react-native";

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
