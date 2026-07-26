import sys
from pathlib import Path
from nicegui import ui

from ying_music_svc.ying_app_ctx import YingCtx
from common.xterm_dialog import XtermDialog


def tab_main(_ctx: YingCtx):
    with ui.expansion("YingMusic-SVC", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):
        ui.label("test")


