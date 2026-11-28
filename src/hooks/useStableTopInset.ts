import { useSafeAreaInsets } from "react-native-safe-area-context";

/**
 * 顶部安全区高度（状态栏/刘海/灵动岛）。页面转场动画期间，系统返回的 top 会短暂变成 0，
 * 导致顶部输入框先贴到状态栏、动画结束后再跳回正确位置（闪一下）。
 * 这里记住曾经测到的最大值，top 一旦量出来就不再回落到 0。
 */
// 先给 Dynamic Island 的初值 59：第一帧 top 还没量出来时是 0，
    // 输入框会先贴到状态栏、量出来后再跳回正确位置（闪一下）。
    // 有了初值就不再从 0 起跳；量到更大的再往上记，永不回落。
    let maxTopInset = 59;

export default function useStableTopInset(): number {
    const { top } = useSafeAreaInsets();
    if (top > maxTopInset) {
        maxTopInset = top;
    }
    return Math.max(top, maxTopInset);
}
