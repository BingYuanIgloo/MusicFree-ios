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
 */

interface IBackJson {
    musicSheets: IMusic.IMusicSheetItem[];
    plugins: Array<{ srcUrl: string; version: string }>;
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
        obj = JSON.parse(raw);
    } else {
        obj = raw as IBackJson;
    }

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
        // 校验是否安装过: 同源且本地版本更高就忽略掉
        if (
            validPlugins.find(
                plugin =>
                    plugin.instance.srcUrl === _.srcUrl &&
                    compare(
                        plugin.instance.version ?? "0.0.0",
                        _.version ?? "0.0.1",
                        ">=",
                    ),
            )
        ) {
            continue;
        }
        try {
            const result = await PluginManager.installPluginFromUrl(_.srcUrl);
            resumeResults.push({
                srcUrl: _.srcUrl,
                success: result.success,
                message: result.message,
            });
        } catch (e: any) {
            resumeResults.push({
                srcUrl: _.srcUrl,
                success: false,
                message: e?.message ?? String(e),
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
