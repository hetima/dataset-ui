from dataclasses import asdict

from nicegui import ui
from common.setting import cnfg
from edit.edit_app_ctx import EditCtx
from common.daw_bridge import add_daw_session_tracks, create_daw_session, create_daw_session_single_track, get_daw_url
from common.plyr import simple_plyr_player
from common.message_dialog import show_confirm_dialog


def tab_main(ctx: EditCtx):

    # ═══════════════════════════════════════════════════════════════════════════════
    # DAW
    # ═══════════════════════════════════════════════════════════════════════════════
    daw_mode = {"single": False}  # False=マルチトラック、True=シングルトラック

    def open_daw() -> None:
        """選択中のファイルを DAW タブで開く。"""

        files = ctx.target_files()
        paths = [edit_file["path"] for edit_file in files]  # type: ignore
        if not paths:
            ui.notify("処理対象がありません")
            return
        cnfg.save()
        if daw_mode["single"]:
            session = create_daw_session_single_track(paths)
        else:
            session = create_daw_session(paths)
        ctx.daw_session_id = session.id
        ctx.daw_url = get_daw_url(session.id)
        ctx.tabs.set_value("daw")
        ui.timer(0.1, lambda: [func() for func in ctx.daw_refresh_func], once=True)

    def append_to_daw() -> None:
        """選択中のファイルを表示中の DAW セッション末尾へ追加する。"""

        if not ctx.daw_session_id:
            ui.notify("先に DAW を開いてください", type="warning")
            return

        files = ctx.target_files()
        paths = [edit_file["path"] for edit_file in files]  # type: ignore
        if not paths:
            ui.notify("処理対象がありません")
            return

        try:
            tracks = add_daw_session_tracks(ctx.daw_session_id, paths)
        except ValueError as exc:
            ui.notify(str(exc), type="negative")
            return

        payload = {
            "type": "daw-add-tracks",
            "tracks": [asdict(track) for track in tracks],
        }
        for func in ctx.daw_post_message_func:
            func(payload)
        ctx.tabs.set_value("daw")
        ui.notify(f"{len(tracks)} 件のトラックを追加しました", type="positive")

    with ui.expansion("DAW", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):
        ui.label(
            "選択したファイルを DAW タブで編集します。マルチトラックでクリップ編集、コンピングなどが行なえます。"
        )
        with ui.row().classes("items-center gap-4"):
            ui.button("DAWで開く", icon="graphic_eq", on_click=open_daw)
            # ui.button("DAW末尾に追加", icon="playlist_add", on_click=append_to_daw)
            ui.toggle(
                {"multi": "マルチトラック", "single": "階段状に並べる"},
                value="multi",
                on_change=lambda e: daw_mode.update({"single": e.value == "single"}),
            ).props("dense")

    # ═══════════════════════════════════════════════════════════════════════════════
    # ファイル一覧
    # ═══════════════════════════════════════════════════════════════════════════════

    plyr = simple_plyr_player("plyr_edit", visible=False, autoplay=True)
    def play_src(path: str):
        plyr.container.set_visibility(True)
        plyr.plyr.load(path)

    with ui.row().classes("w-full gap-4 items-start"):
        with ui.column().classes("flex-1 gap-1"):
            ui.label("書き出しフォルダ").classes("font-bold")
            ctx.table = ui.table(
                columns=[
                    {
                        "label": "",
                        "field": "path",
                        "name": "play",
                        "style": "width: 30px",
                    },
                    {
                        "label": "Name",
                        "field": "name",
                        "name": "name",
                        "align": "left",
                    },
                ],
                rows=[],
                selection="multiple",
                row_key="path",
                pagination=100,
            ).classes("h-120 w-full no-shadow brdr q-pa-none")
            ctx.table.props(':filter-method="(rows, terms) => rows.filter(r => r.name.includes(terms))"')
            with ctx.table.add_slot('body-cell-play'):
                with ctx.table.cell('play'):
                    ui.button(icon="play_circle").props('flat').on(
                        'click',
                        js_handler='() => emit(props.value)',
                        handler=lambda e: play_src(e.args),
                    ).style('padding: 2px 4px;')
            with ctx.table.add_slot("top-right"):
                ui.input(placeholder="フィルタ...").bind_value(
                    ctx.table, "filter"
                ).classes("w-80").props("rounded outlined dense clearable")

        with ui.column().classes("flex-1 gap-1"):
            ui.label("エディットプール").classes("font-bold")
            ctx.pool_table = ui.table(
                columns=[

                    {
                        "label": "",
                        "field": "path",
                        "name": "play",
                        "style": "width: 30px",
                    },
                    {
                        "label": "Name",
                        "field": "name",
                        "name": "name",
                        "align": "left",
                    },
                ],
                rows=[],
                selection="multiple",
                row_key="path",
                pagination=100,
            ).classes("h-120 w-full no-shadow brdr q-pa-none")
            ctx.pool_table.props(
                ':filter-method="(rows, terms) => rows.filter(r => r.name.includes(terms))"'
            )
            with ctx.pool_table.add_slot("body-cell-play"):
                with ctx.pool_table.cell("play"):
                    ui.button(icon="play_circle").props('flat').on(
                        'click',
                        js_handler='() => emit(props.value)',
                        handler=lambda e: play_src(e.args),
                    ).style('padding: 2px 4px;')
            with ctx.pool_table.add_slot("top-right"):
                ui.input(placeholder="フィルタ...").bind_value(
                    ctx.pool_table, "filter"
                ).classes("w-80").props("rounded outlined dense clearable")

    ctx.load_files(str(cnfg.outputs_dir))
    ctx.load_pool()
    
    async def delete_selected(permanent=False):
        if len(ctx.table.selected) == 0:
            ui.notify("処理対象がありません")
            return
        trash = "（ゴミ箱に移動します）" if not permanent else ""
        if not await show_confirm_dialog(f"選択項目を削除しますか？{trash}"):
            return
        ctx.delete_selected(permanent)
    with ui.dropdown_button('選択項目を削除', color='red'):
        ui.item('ゴミ箱に移動...', on_click=lambda: delete_selected(False))
        ui.item('完全に削除...', on_click=lambda: delete_selected(True))
