module.exports = {
    presets: ['babel-preset-expo'],
    plugins: [
        [
            'module-resolver',
            {
                root: ['./'],
                alias: {
                    '^@/(.+)': './src/\\1',
                    'webdav': "webdav/dist/react-native"
                },
            },
        ],
    ],
    env: {
        production: {
            plugins: ['transform-remove-console'],
        },
    },
};
