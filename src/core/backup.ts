/** 备份与恢复 */
/** 歌单、插件 */
import { compare } from "compare-versions";
import PluginManager from "./pluginManager";
import MusicSheet from "@/core/musicSheet";
import { ResumeMode } from "@/constants/commonConst.ts";

/**
 * 结果：一份大的json文件
 * {
 *     musicSheets: [],
 *     plugins: [],
 * }
 * 也支持 Android v2 备份（format: "musicfree-backup", version: 2）：
 * 顶层 sections.plugins.installed / sections.musicSheets 会被归一化成上面
 * 的扁平结构再恢复；settings / mediaMeta / starredPlaylists /
 * subscriptions / alternatives 在 iOS 上没有对应位置，直接丢弃（只记一条日志）。
 */

interface IBackJson {
    musicSheets: IMusic.IMusicSheetItem[];
    plugins: Array<{ srcUrl: string; version: string }>;
}

/** 把 Android v2 备份归一化成 iOS 扁平格式；扁平格式原样返回。 */
function normalizeBackupJson(obj: any): IBackJson {
    const isV2 =
        obj != null &&
        typeof obj === "object" &&
        obj.version === 2 &&
        obj.sections != null &&
        (obj.format === "musicfree-backup" || obj.format == null);
    if (!isV2) {
        return obj as IBackJson;
    }

    const sections = obj.sections ?? {};
    const installed = sections.plugins?.installed;
    const plugins = (Array.isArray(installed) ? installed : [])
        .filter((_: any) => typeof _.srcUrl === "string" && _.srcUrl.length > 0)
        .map((_: any) => ({
            srcUrl: _.srcUrl,
            version: _.version ?? "0.0.1",
        }));
    const musicSheets = Array.isArray(sections.musicSheets)
        ? sections.musicSheets
        : [];

    const dropped: string[] = [];
    const settingsCount = Object.keys(sections.settings?.values ?? {}).length;
    if (settingsCount > 0) {
        dropped.push(`settings(${settingsCount} 项，Android 专属）`);
    }
    const mediaMetaCount = Array.isArray(sections.mediaMeta)
        ? sections.mediaMeta.length
        : 0;
    if (mediaMetaCount > 0) {
        dropped.push(`mediaMeta(${mediaMetaCount} 条，Android 专属）`);
    }
    if (Array.isArray(sections.starredPlaylists) && sections.starredPlaylists.length > 0) {
        dropped.push(`starredPlaylists(${sections.starredPlaylists.length} 个）`);
    }
    const subCount = Array.isArray(sections.plugins?.subscriptions)
        ? sections.plugins.subscriptions.length
        : 0;
    if (subCount > 0) {
        dropped.push(`插件订阅(${subCount} 个）`);
    }
    const altCount = Array.isArray(sections.plugins?.alternatives)
        ? sections.plugins.alternatives.length
        : 0;
    if (altCount > 0) {
        dropped.push(`备用插件(${altCount} 个）`);
    }
    console.info(
        "[备份恢复] 检测到 Android v2 备份，已归一化：",
        `插件 ${plugins.length} 个，歌单 ${musicSheets.length} 个；`,
        dropped.length > 0
            ? `iOS 无对应位置，已丢弃：${dropped.join("、")}。`
            : "无可丢弃内容。",
    );

    return { musicSheets, plugins };
}

function backup() {
    const musicSheets = MusicSheet.backupSheets();
    const plugins = PluginManager.getEnabledPlugins();
    const normalizedPlugins = plugins.map(_ => ({
        srcUrl: _.instance.srcUrl,
        version: _.instance.version,
    }));

    return JSON.stringify({
        musicSheets: musicSheets,
        plugins: normalizedPlugins,
    });
}

async function resume(
    raw: string | Object,
    resumeMode: ResumeMode = ResumeMode.Append,
) {
    let obj: IBackJson;
    if (typeof raw === "string") {
        try {
            obj = JSON.parse(raw);
        } catch {
            throw new Error("备份文件格式无效");
        }
    } else {
        obj = raw as IBackJson;
    }
    /** Android v2 备份先归一化成扁平格式；扁平格式原样通过。 */
    obj = normalizeBackupJson(obj);

    const { plugins, musicSheets } = obj ?? {};
    /** 恢复插件：逐个串行安装。
     * 之前是并发 + Promise.all：installPluginFromUrl 内部先快照插件列表、再整体写回，
     * 两个安装重叠时后写回的会丢掉先装好的插件，导致导入静默缺失。 */
    const validPlugins = PluginManager.getEnabledPlugins();
    const resumeResults: Array<{
        srcUrl: string;
        success: boolean;
        message?: string;
    }> = [];
    for (const _ of plugins ?? []) {
        // 校验是否安装过: 同源且本地版本更高就忽略掉。
        // compare() 碰到不规范版本号会抛错，之前这段在 try/catch 外面，
        // 一个坏版本就中断整个恢复（只恢复了前几条、速度还显得快）。
        let alreadyInstalled = false;
        try {
            alreadyInstalled = !!validPlugins.find(
                plugin =>
                    plugin.instance.srcUrl === _.srcUrl &&
                    compare(
                        plugin.instance.version ?? "0.0.0",
                        _.version ?? "0.0.1",
                        ">=",
                    ),
            );
        } catch {
            // 坏版本当作没装过，走正常安装流程（安装侧自己会判重）。
            alreadyInstalled = false;
        }
        if (alreadyInstalled) {
            continue;
        }
        // 安装失败重试一次（临时网络抖动很常见），两次都失败才记失败。
        let lastError: any = null;
        let installed = false;
        for (let attempt = 0; attempt < 2 && !installed; attempt++) {
            try {
                const result = await PluginManager.installPluginFromUrl(_.srcUrl);
                resumeResults.push({
                    srcUrl: _.srcUrl,
                    success: result.success,
                    message: result.message,
                });
                installed = true;
            } catch (e: any) {
                lastError = e;
            }
        }
        if (!installed) {
            resumeResults.push({
                srcUrl: _.srcUrl,
                success: false,
                message: lastError?.message ?? String(lastError),
            });
        }
    }
    const failedPlugins = resumeResults.filter(r => !r.success);
    if (failedPlugins.length > 0) {
        console.warn(
            "[备份恢复] 以下插件安装失败：",
            failedPlugins.map(f => `${f.srcUrl} (${f.message ?? "未知错误"})`),
        );
    }

    /** 恢复歌单 */
    const resumeMusicSheets = await MusicSheet.resumeSheets(musicSheets, resumeMode);

    return [...resumeResults, resumeMusicSheets];
}

const Backup = {
    backup,
    resume,
};
export default Backup;
