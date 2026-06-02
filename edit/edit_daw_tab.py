import json

from nicegui import ui
from edit.edit_app_ctx import EditCtx


_EXPORT_REQUEST_EVENT = "daw-export-request"
_EXPORT_COMPLETE_EVENT = "daw-export-complete"
_EXPORT_ERROR_EVENT = "daw-export-error"
_AAF_EXPORT_REQUEST_EVENT = "daw-aaf-export-request"


def tab_main(ctx: EditCtx):
    ui.markdown(
        "**S** 再生位置でオーディオイベントを分割"
        "<br>**R** 再生位置でコンピングリージョンを分割<br>"
        "**SPACE** 再生/停止（再生開始位置に戻る）<br>"
        "**ENTER** 再生/一時停止"
        "<br>**L** ループ再生オンオフ（波形ビューを右方向にドラッグで選択範囲を作ります。コンピングモードで選択範囲を作るには下側2割くらいのスペースでドラッグしてください）<br>"
        "<br>"
        "コンピングモードではリージョンが存在する箇所のみ再生され、存在しない箇所はミュートされます。<br>"
        "<br>"
        "書き出し時にはマスターボリュームの数値は無視されます。<br>"
        "AAFファイルにはファイルのフルパスで記入されます。書き出し後にファイルを移動すると見失います。<br>"
        "品質を重視するならAAFで書き出してちゃんとしたDAWで作業することをお勧めします。"
    )

    frame_container = ui.element("div").classes("w-full")
    element_id = f"c{frame_container.id}"
    pending_request: dict = {}
    pending_aaf_request: dict = {}
    # 音声書き出しの進行状態。active=True の間だけ進行中スピナー通知を扱う。
    export_progress: dict = {"active": False, "notification": None}

    def finish_export_progress() -> None:
        """進行中スピナー通知が出ていれば閉じ、進行状態を解除する。"""

        export_progress["active"] = False
        notification = export_progress["notification"]
        if notification is not None:
            notification.dismiss()
            export_progress["notification"] = None

    def show_export_progress() -> None:
        """3秒経過してもまだ書き出し中なら進行中スピナー通知を表示する。"""

        if not export_progress["active"] or export_progress["notification"] is not None:
            return
        export_progress["notification"] = ui.notification(
            "書き出し中です", spinner=True, timeout=None
        )

    def on_export_complete(e) -> None:
        """JS 側のアップロード完了通知を表示する。"""

        finish_export_progress()
        args = e.args if isinstance(e.args, dict) else {}
        path = args.get("path")
        if path:
            ui.notify(f"書き出しました: {path}", type="positive")
        else:
            ui.notify("書き出しが完了しました", type="positive")

    def on_export_error(e) -> None:
        """JS/DAW/API 側の書き出しエラーを表示する。"""

        finish_export_progress()
        args = e.args if isinstance(e.args, dict) else {}
        ui.notify(str(args.get("message") or "書き出しに失敗しました"), type="negative")

    ui.on(_EXPORT_COMPLETE_EVENT, on_export_complete)
    ui.on(_EXPORT_ERROR_EVENT, on_export_error)

    with ui.dialog() as export_dialog, ui.card().classes("w-96"):
        ui.label("DAW 書き出し").classes("text-lg font-bold")
        filename_input = ui.input("ファイル名").classes("w-full")
        format_select = ui.select({"wav": "WAV", "flac": "FLAC"}, label="フォーマット", value="wav").classes("w-full")

        def confirm_export() -> None:
            filename = str(filename_input.value or "").strip()
            if not filename:
                ui.notify("ファイル名を入力してください", type="warning")
                return
            options = {
                "filename": filename,
                "format": format_select.value,
                "saveMode": pending_request.get("saveMode", "save"),
            }
            request_id = pending_request.get("requestId", "")
            payload = json.dumps(
                {
                    "type": "daw-export-start",
                    "requestId": request_id,
                    "options": options,
                },
                ensure_ascii=False,
            )
            ui.run_javascript(
                f'''
                const dawContainer = document.getElementById("{element_id}");
                const dawFrame = dawContainer?.querySelector("iframe");
                dawFrame?.contentWindow?.postMessage({payload}, "*");
                '''
            )
            export_dialog.close()
            # 進行状態をセットし、3秒経過してもまだ書き出し中なら通知を出す。
            export_progress["active"] = True
            ui.timer(3.0, show_export_progress, once=True)

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("キャンセル", on_click=export_dialog.close).props("flat")
            ui.button("OK", on_click=confirm_export).props("color=primary")

    def on_export_request(e) -> None:
        """DAW iframe から書き出し開始要求を受けて、設定ダイアログを開く。"""

        args = e.args if isinstance(e.args, dict) else {}
        pending_request.clear()
        pending_request.update(args)
        filename_input.value = str(args.get("defaultFilename") or "daw-export")
        format_select.value = "wav"
        export_dialog.open()

    ui.on(_EXPORT_REQUEST_EVENT, on_export_request)

    with ui.dialog() as aaf_dialog, ui.card().classes("w-96"):
        ui.label("AAF 書き出し").classes("text-lg font-bold")
        aaf_filename_input = ui.input("ファイル名").classes("w-full")

        def confirm_aaf_export() -> None:
            filename = str(aaf_filename_input.value or "").strip()
            if not filename:
                ui.notify("ファイル名を入力してください", type="warning")
                return
            options = {
                "filename": filename,
                "saveMode": pending_aaf_request.get("saveMode", "save"),
            }
            request_id = pending_aaf_request.get("requestId", "")
            payload = json.dumps(
                {
                    "type": "daw-aaf-export-start",
                    "requestId": request_id,
                    "options": options,
                },
                ensure_ascii=False,
            )
            ui.run_javascript(
                f'''
                const dawContainer = document.getElementById("{element_id}");
                const dawFrame = dawContainer?.querySelector("iframe");
                dawFrame?.contentWindow?.postMessage({payload}, "*");
                '''
            )
            aaf_dialog.close()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("キャンセル", on_click=aaf_dialog.close).props("flat")
            ui.button("OK", on_click=confirm_aaf_export).props("color=primary")

    def on_aaf_export_request(e) -> None:
        """DAW iframe から AAF 書き出し開始要求を受けて、設定ダイアログを開く。"""

        args = e.args if isinstance(e.args, dict) else {}
        pending_aaf_request.clear()
        pending_aaf_request.update(args)
        aaf_filename_input.value = str(args.get("defaultFilename") or "daw-edit")
        aaf_dialog.open()

    ui.on(_AAF_EXPORT_REQUEST_EVENT, on_aaf_export_request)

    ui.add_body_html(
        f'''
<script>
if (!window.__datasetUiDawExportBridgeInstalled) {{
    window.__datasetUiDawExportBridgeInstalled = true;
    window.addEventListener("message", async (event) => {{
        const data = event.data || {{}};
        if (data.type === "daw-export-request") {{
            emitEvent("{_EXPORT_REQUEST_EVENT}", data);
            return;
        }}
        if (data.type === "daw-aaf-export-request") {{
            emitEvent("{_AAF_EXPORT_REQUEST_EVENT}", data);
            return;
        }}
        if (data.type === "daw-export-error") {{
            emitEvent("{_EXPORT_ERROR_EVENT}", {{ message: data.message || "書き出しに失敗しました" }});
            return;
        }}
        if (data.type !== "daw-export-audio") return;

        try {{
            const options = data.options || {{}};
            const blob = new Blob([data.wavBuffer], {{ type: "audio/wav" }});
            const form = new FormData();
            form.append("audio", blob, "render.wav");
            form.append("options", JSON.stringify(options));

            const response = await fetch("/api/daw/export", {{
                method: "POST",
                body: form,
            }});
            if (!response.ok) {{
                let message = `書き出し API エラー (${{response.status}})`;
                try {{
                    const errorBody = await response.json();
                    message = errorBody.detail || message;
                }} catch {{}}
                throw new Error(message);
            }}

            if (options.saveMode === "download") {{
                const outBlob = await response.blob();
                const url = URL.createObjectURL(outBlob);
                const a = document.createElement("a");
                const ext = options.format || "wav";
                const name = (options.filename || "daw-export").replace(/\\.[^/.]+$/, "");
                a.href = url;
                a.download = `${{name}}.${{ext}}`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
                emitEvent("{_EXPORT_COMPLETE_EVENT}", {{}});
            }} else {{
                const result = await response.json();
                emitEvent("{_EXPORT_COMPLETE_EVENT}", result);
            }}
        }} catch (error) {{
            emitEvent("{_EXPORT_ERROR_EVENT}", {{
                message: error instanceof Error ? error.message : "書き出しに失敗しました",
            }});
        }}
    }});

    window.addEventListener("message", async (event) => {{
        const data = event.data || {{}};
        if (data.type !== "daw-aaf-export-data") return;

        try {{
            const options = data.options || {{}};
            const response = await fetch("/api/daw/export-aaf", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify({{ options, aaf: data.aaf }}),
            }});
            if (!response.ok) {{
                let message = `AAF 書き出し API エラー (${{response.status}})`;
                try {{
                    const errorBody = await response.json();
                    message = errorBody.detail || message;
                }} catch {{}}
                throw new Error(message);
            }}

            if (options.saveMode === "download") {{
                const outBlob = await response.blob();
                const url = URL.createObjectURL(outBlob);
                const a = document.createElement("a");
                const name = (options.filename || "daw-edit").replace(/\\.[^/.]+$/, "");
                a.href = url;
                a.download = `${{name}}.aaf`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
                emitEvent("{_EXPORT_COMPLETE_EVENT}", {{}});
            }} else {{
                const result = await response.json();
                emitEvent("{_EXPORT_COMPLETE_EVENT}", result);
            }}
        }} catch (error) {{
            emitEvent("{_EXPORT_ERROR_EVENT}", {{
                message: error instanceof Error ? error.message : "AAF 書き出しに失敗しました",
            }});
        }}
    }});
}}
</script>
'''
    )

    def update_frame() -> None:
        """DAW iframe を現在の URL で描画する。"""

        if not ctx.daw_url:
            ui.run_javascript(
                f'''
                const dawContainer = document.getElementById("{element_id}");
                if (dawContainer) {{
                    dawContainer.innerHTML =
                        '<div class="infotxt">ファイルを選択して DAW を開いてください</div>';
                }}
                '''
            )
            return
        ui.run_javascript(
            f'''
            const dawContainer = document.getElementById("{element_id}");
            if (dawContainer) {{
                const dawFrame = dawContainer.querySelector("iframe");
                if (!dawFrame || dawFrame.getAttribute("src") !== "{ctx.daw_url}") {{
                    dawContainer.innerHTML =
                        '<iframe src="{ctx.daw_url}" style="width: 100%; height: 90vh; border: 1px solid #ccc; border-radius: 4px;"></iframe>';
                }}
            }}
            '''
        )

    ctx.daw_refresh_func.append(update_frame)
    ui.timer(0.1, update_frame, once=True)
