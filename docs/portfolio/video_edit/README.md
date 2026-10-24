# 営業用デモの編集プロジェクト

完成動画は`../demo_crowdworks_v052.mp4`。60秒・1920×1080・25fps・H.264・音声なし。説明テロップは映像へ焼き込み済みで、字幕ファイルの読み込みは不要です。`../demo_crowdworks_v052.srt`は補助的な説明原稿です。

- `project.json`：原本ハッシュ、採用区間、各場面の尺、クロップ範囲、字幕原稿。
- `render.py`：テロップ本文・フォントサイズ・配色・拡大枠・場面切り替え。`build()`が文字配置、`composite()`が実画面の拡大と枠線です。
- `check_output.py`：完成MP4の全フレームをデコードし、形式・尺・MP4の先頭索引・確認画像を検査します。
- `verify_playback.cjs`：ローカル限定の一時サーバーと自分で起動するブラウザで、先頭から末尾まで等速再生を確認します。既存アプリや他のブラウザは操作しません。
- `editing-report.md`／`verification.json`：編集内容と今回の検証記録。

## 再生成

Python、Pillowとlibx264対応のFFmpegが必要です。今回の実行は既存Python 3.12.14・既存Pillowを使い、imageio-ffmpeg 0.6.0だけをプロジェクト内の`tmp/video-editor-deps`へ追加しました。アプリの仮想環境・依存設定・OS設定は変更していません。

別環境で必要な場合は、アプリ用venvと分けて準備してください。以下は既存Python 3.12を使う準備例です。権限変更や実行制限の回避は行わないでください。

~~~powershell
py -3.12 -m venv tmp/video-edit-venv
tmp/video-edit-venv/Scripts/python.exe -m pip install Pillow imageio-ffmpeg
$videoFfmpeg = & tmp/video-edit-venv/Scripts/python.exe -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
tmp/video-edit-venv/Scripts/python.exe docs/portfolio/video_edit/render.py --ffmpeg $videoFfmpeg --preview-only
tmp/video-edit-venv/Scripts/python.exe docs/portfolio/video_edit/render.py --ffmpeg $videoFfmpeg --force
tmp/video-edit-venv/Scripts/python.exe docs/portfolio/video_edit/check_output.py --ffmpeg $videoFfmpeg
~~~

`--force`は今回の編集版だけを置き換えます。原本`demo.webm`と同じ出力先は拒否し、原本ハッシュが違う場合も停止します。中間画像・処理ログは`tmp/crowdworks-video/`へ保存します。尺は`project.json`の`duration`で変更でき、総フレーム数と補助SRTは再計算します。採用区間を変えたときは、入力質問と表示結果が食い違う瞬間を含めないよう実物を確認してください。

Windows標準の游ゴシックをローカルで文字画像へ描画します。フォント本体の同梱・変換・動画への埋め込みはしません。[MicrosoftのフォントFAQ](https://learn.microsoft.com/en-us/typography/fonts/font-faq)の動画字幕に関する説明を確認しています。別OSや別フォントでは、利用許諾を確認して`project.json`のフォントパスを指定してください。商用BGM・素材は使用していません。

ブラウザの通し再生検証だけにはNode.js、Playwright、既存のChromeも必要です。これらは完成動画の再生・通常の再生成には必須ではありません。今回の確認は既存環境を利用しました。

~~~powershell
node docs/portfolio/video_edit/verify_playback.cjs docs/portfolio/demo_crowdworks_v052.mp4 tmp/crowdworks-video/final-playback
~~~

原本とアプリ本体、既存評価、過去の配布物は変更しません。GitHub・クラウドワークスへの送信や、アプリの起動・再収録も行いません。
