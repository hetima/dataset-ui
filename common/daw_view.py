import json
from typing import Any, Callable

from nicegui import ui


def daw_view(
    get_daw_url: Callable[[], str],
    refresh_funcs: list[Callable[[], None]] | None = None,
    post_message_funcs: list[Callable[[dict[str, Any]], None]] | None = None,
) -> Callable[[], None]:
    """DAW iframe と書き出し処理を表示し、再描画用コールバックを返す。"""

    frame_container = ui.element("div").classes("w-full")
    element_id = f"c{frame_container.id}"
    event_suffix = str(frame_container.id)
    export_request_event = f"daw-export-request-{event_suffix}"
    export_complete_event = f"daw-export-complete-{event_suffix}"
    export_error_event = f"daw-export-error-{event_suffix}"
    aaf_export_request_event = f"daw-aaf-export-request-{event_suffix}"
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

    ui.on(export_complete_event, on_export_complete)
    ui.on(export_error_event, on_export_error)

    with ui.dialog() as export_dialog, ui.card().classes("w-96"):
        ui.label("DAW 書き出し").classes("text-lg font-bold")
        filename_input = ui.input("ファイル名").classes("w-full")
        format_select = ui.select(
            {"wav": "WAV", "flac": "FLAC"}, label="フォーマット", value="wav"
        ).classes("w-full")

        def confirm_export() -> None:
            """音声書き出し設定を iframe へ送る。"""

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

    ui.on(export_request_event, on_export_request)

    with ui.dialog() as aaf_dialog, ui.card().classes("w-96"):
        ui.label("AAF 書き出し").classes("text-lg font-bold")
        aaf_filename_input = ui.input("ファイル名").classes("w-full")

        def confirm_aaf_export() -> None:
            """AAF 書き出し設定を iframe へ送る。"""

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

    ui.on(aaf_export_request_event, on_aaf_export_request)

    ui.add_body_html(
        f'''
<script>
if (!window.__datasetUiDawExportBridgeInstalled_{event_suffix}) {{
    window.__datasetUiDawExportBridgeInstalled_{event_suffix} = true;
    window.addEventListener("message", async (event) => {{
        const dawContainer = document.getElementById("{element_id}");
        const dawFrame = dawContainer?.querySelector("iframe");
        if (event.source !== dawFrame?.contentWindow) return;

        const data = event.data || {{}};
        if (data.type === "daw-export-request") {{
            emitEvent("{export_request_event}", data);
            return;
        }}
        if (data.type === "daw-aaf-export-request") {{
            emitEvent("{aaf_export_request_event}", data);
            return;
        }}
        if (data.type === "daw-export-error") {{
            emitEvent("{export_error_event}", {{ message: data.message || "書き出しに失敗しました" }});
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
                emitEvent("{export_complete_event}", {{}});
            }} else {{
                const result = await response.json();
                emitEvent("{export_complete_event}", result);
            }}
        }} catch (error) {{
            emitEvent("{export_error_event}", {{
                message: error instanceof Error ? error.message : "書き出しに失敗しました",
            }});
        }}
    }});

    window.addEventListener("message", async (event) => {{
        const dawContainer = document.getElementById("{element_id}");
        const dawFrame = dawContainer?.querySelector("iframe");
        if (event.source !== dawFrame?.contentWindow) return;

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
                emitEvent("{export_complete_event}", {{}});
            }} else {{
                const result = await response.json();
                emitEvent("{export_complete_event}", result);
            }}
        }} catch (error) {{
            emitEvent("{export_error_event}", {{
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

        daw_url = get_daw_url()
        if not daw_url:
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
                if (!dawFrame || dawFrame.getAttribute("src") !== "{daw_url}") {{
                    dawContainer.innerHTML =
                        '<iframe src="{daw_url}" style="width: 100%; height: 90vh; border: 1px solid #ccc; border-radius: 4px;"></iframe>';
                }}
            }}
            '''
        )

    def post_message(payload: dict[str, Any]) -> None:
        """DAW iframe へ postMessage で通知する。"""

        message = json.dumps(payload, ensure_ascii=False)
        ui.run_javascript(
            f'''
            const dawContainer = document.getElementById("{element_id}");
            const dawFrame = dawContainer?.querySelector("iframe");
            dawFrame?.contentWindow?.postMessage({message}, "*");
            '''
        )

    if refresh_funcs is not None:
        refresh_funcs.append(update_frame)
    if post_message_funcs is not None:
        post_message_funcs.append(post_message)
    ui.timer(0.1, update_frame, once=True)
    return update_frame
