
from pathlib import Path
from typing import cast
from nicegui import ui
from common.setting import cnfg
import sys
from edit.edit_app_ctx import EditCtx
from common.wavesurfer import simple_player

def tab_compi(ctx: EditCtx):
    ui.label("compi")