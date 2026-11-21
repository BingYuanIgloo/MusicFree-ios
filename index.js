/**
 * @format
 */

import {AppRegistry} from 'react-native';
import {name as appName} from './app.json';
import TrackPlayer from '@rntp/player';
import Pages from '@/entry';

// v5：registerPlaybackService 改名 registerPlaybackSession，且要在
// registerComponent 之前调用；session 回调要真的执行 service 函数
//（v4 是把 require 的结果当作 service 交给库去调用，v5 是直接运行回调）。
TrackPlayer.registerPlaybackSession(() => require('./src/service/index')());
AppRegistry.registerComponent(appName, () => Pages);
