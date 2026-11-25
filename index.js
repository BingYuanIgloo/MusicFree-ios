/**
 * @format
 */

import * as SplashScreen from 'expo-splash-screen';
SplashScreen.preventAutoHideAsync().catch(() => {});

import {AppRegistry} from 'react-native';
import {name as appName} from './app.json';
import TrackPlayer from 'react-native-track-player';
import Pages from '@/entry';

AppRegistry.registerComponent(appName, () => Pages);
try {
    TrackPlayer.registerPlaybackService(() => require('./src/service/index'));
} catch (e) {
    // 播放服务注册失败绝不能阻止应用挂载: 记日志, 应用继续启动
    console.warn("[index] TrackPlayer.registerPlaybackService() failed, continuing without playback service:", e);
}
