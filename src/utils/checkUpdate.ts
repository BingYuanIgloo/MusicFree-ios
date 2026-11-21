import axios from "axios";
import { compare } from "compare-versions";
import DeviceInfo from "react-native-device-info";
import { Platform } from "react-native";

const updateList = [
    "https://gitee.com/maotoumao/MusicFree/raw/master/release/version.json",
    "https://raw.githubusercontent.com/maotoumao/MusicFree/master/release/version.json",
    "https://cdn.jsdelivr.net/gh/maotoumao/MusicFree@master/release/version.json",
];

interface IUpdateInfo {
    needUpdate: boolean;
    data: {
        version: string;
        changeLog: string[];
        download: string[];
    };
}

export default async function checkUpdate(): Promise<IUpdateInfo | undefined> {
    // iOS 没有 APK 更新通道（通过 SideStore 重建安装），不检查上游 version.json
    if (Platform.OS === "ios") {
        return undefined;
    }
    const currentVersion = DeviceInfo.getVersion();
    for (let i = 0; i < updateList.length; ++i) {
        try {
            const rawInfo = (await axios.get(updateList[i])).data;
            if (compare(rawInfo.version, currentVersion, ">")) {
                return {
                    needUpdate: true,
                    data: rawInfo,
                };
            }
        } catch {}
    }
}
