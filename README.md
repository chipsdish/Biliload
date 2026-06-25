# Biliload

本地 B 站视频下载与双语字幕生成应用。

## 功能

- 输入 B 站视频链接，下载视频或音频。
- 使用 Whisper 生成视频原语言字幕。
- 将字幕翻译为中文，输出原文 SRT、中文 SRT、双语 SRT、JSON 和 TXT。
- 安装 `extension/` Chrome 扩展后，打开对应 B 站视频页会自动从本地应用读取字幕并叠加到播放器上。

## 运行

```bash
./run.sh
```

打开：

```text
http://127.0.0.1:8787
```

首次运行会创建 `.venv` 并安装依赖。`ffmpeg` 需要已安装并在 `PATH` 中。

## B 站网页导入

1. 启动 Biliload。
2. 打开 `chrome://extensions`。
3. 启用“开发者模式”。
4. 点击“加载已解压的扩展程序”。
5. 选择当前项目的 `extension/` 目录。
6. 在 Biliload 中生成字幕后，打开同一个 B 站视频页。

扩展会读取 `http://127.0.0.1:8787/api/page-subtitle` 返回的字幕并叠加显示。它不会上传字幕到 B 站服务器。

## 目录

- `app/`：FastAPI 后端和下载/转写/翻译流程。
- `static/`：本地 Web UI。
- `extension/`：B 站页面字幕叠加 Chrome 扩展。
- `data/`：运行时生成的任务、视频和字幕文件，已加入 `.gitignore`。

## 注意

- B 站部分视频需要登录态，默认会读取 Chrome cookies。
- 粤语建议选择“粤语”或“中文/普通话”；Whisper 对粤语通常用 `zh` 模型路径更稳。
- `large-v3-turbo` 更准但更慢，首次使用会下载较大的模型缓存。
- 请只下载和处理你有权访问和使用的视频内容。

