from pathlib import Path
from nicegui import binding, ui
from music.setting import cnfg
from music.app_ctx import MusicCtx


def tab_setting(ctx: MusicCtx):
    ui.label("setting")

