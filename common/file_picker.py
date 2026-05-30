from pathlib import Path
from nicegui import ui


class FilePicker(ui.dialog):
    """ファイル選択ダイアログ。await して [path_str, ...] または None を返す。複数選択可。"""

    def __init__(
        self,
        directory: str,
        *,
        caption: str = "ファイルを選択してください",
        show_hidden_files: bool = False,
        show_files_extension: list[str] | None = None,
        sort: str = 'name',
    ) -> None:
        super().__init__()

        self.root_path = Path(directory).expanduser()
        self.show_hidden_files = show_hidden_files
        # 拡張子を小文字・ドット付きに正規化（例: 'wav' → '.wav'）
        self._exts: set[str] | None = (
            {('.' + e.lstrip('.').lower()) for e in show_files_extension}
            if show_files_extension else None
        )
        self._sort = sort

        self._selected: set[str] = set()
        self._children_cols: dict[str, ui.element] = {}
        self._row_elements: dict[str, ui.element] = {}
        self._arrow_elements: dict[str, ui.icon] = {}
        self._expanded: set[str] = set()
        self._resolved: set[str] = set()
        self._node_paths: dict[str, Path] = {}

        with self, ui.card().classes('h-150 flex flex-col gap-2'):
            ui.label(caption).classes('text-base font-semibold')

            with ui.column().classes('w-96 flex-1 overflow-y-auto border rounded p-1 select-none gap-0'):
                self._render_children(self.root_path, level=0)

            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('キャンセル', on_click=self.close).props('outline')
                ui.button('選択', on_click=self._handle_ok)

    # ──────────────────────────────────────────────
    # スキャン
    # ──────────────────────────────────────────────

    def _is_visible_file(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if not self.show_hidden_files and path.name.startswith('.'):
            return False
        if self._exts is not None and path.suffix.lower() not in self._exts:
            return False
        return True

    def _is_visible_dir(self, path: Path) -> bool:
        if not path.is_dir():
            return False
        return self.show_hidden_files or not path.name.startswith('.')

    def _scan_dir(self, path: Path) -> tuple[list[Path], list[Path]]:
        """(サブフォルダリスト, ファイルリスト) を返す"""
        try:
            entries = list(path.iterdir())
        except PermissionError:
            return [], []
        date_sort = self._sort == 'date'
        key = (lambda p: p.stat().st_mtime) if date_sort else (lambda p: p.name.lower())
        dirs = sorted([p for p in entries if self._is_visible_dir(p)], key=key, reverse=date_sort)
        files = sorted([p for p in entries if self._is_visible_file(p)], key=key, reverse=date_sort)
        return dirs, files

    def _count_files(self, path: Path) -> int:
        try:
            return sum(1 for p in path.iterdir() if self._is_visible_file(p))
        except PermissionError:
            return 0

    def _has_subdir(self, path: Path) -> bool:
        try:
            return any(self._is_visible_dir(p) for p in path.iterdir())
        except PermissionError:
            return False

    # ──────────────────────────────────────────────
    # 描画
    # ──────────────────────────────────────────────

    def _render_children(self, path: Path, level: int):
        dirs, files = self._scan_dir(path)
        for d in dirs:
            self._render_dir_node(d, level)
        for f in files:
            self._render_file_node(f, level)

    def _render_dir_node(self, path: Path, level: int):
        nid = str(path)
        self._node_paths[nid] = path
        has_sub = self._has_subdir(path)
        count = self._count_files(path)
        indent = level * 20

        with ui.row().classes(
            'items-center w-full cursor-pointer rounded px-1 py-0.5 '
            'hover:bg-gray-100 dark:hover:bg-gray-800 gap-1'
        ).style(f'padding-left: {8 + indent}px') as row:
            self._row_elements[nid] = row

            if has_sub:
                arrow = ui.icon('chevron_right', size='xs').classes(
                    'transition-transform duration-150 text-gray-500 flex-shrink-0'
                )
                self._arrow_elements[nid] = arrow
                arrow.on('click.stop', lambda _, n=nid: self._toggle_expand(n))
            else:
                ui.element('div').style('width: 16px; height: 16px; flex-shrink: 0')

            ui.icon('folder', size='xs').classes('text-yellow-600 flex-shrink-0')
            ui.label(path.name).classes('text-sm truncate flex-1')
            ui.label(f'({count})').classes('text-xs text-gray-400 flex-shrink-0')

            # フォルダ行クリック = 展開トグル
            row.on('click', lambda _, n=nid: self._toggle_expand(n))

        if has_sub:
            with ui.column().classes('w-full gap-0') as col:
                col.set_visibility(False)
                self._children_cols[nid] = col

    def _render_file_node(self, path: Path, level: int):
        nid = str(path)
        indent = level * 20

        with ui.row().classes(
            'items-center w-full cursor-pointer rounded px-1 py-0.5 '
            'hover:bg-gray-100 dark:hover:bg-gray-800 gap-1'
        ).style(f'padding-left: {8 + indent}px') as row:
            self._row_elements[nid] = row

            ui.element('div').style('width: 16px; height: 16px; flex-shrink: 0')
            ui.icon('audio_file', size='xs').classes('text-blue-500 flex-shrink-0')
            ui.label(path.name).classes('text-sm truncate flex-1')

            row.on('click', lambda _, n=nid: self._toggle_select(n))
            row.on('dblclick', lambda _, n=nid: self._on_dblclick(n))

    # ──────────────────────────────────────────────
    # 展開 / 折りたたみ
    # ──────────────────────────────────────────────

    def _toggle_expand(self, nid: str):
        if nid in self._expanded:
            self._expanded.discard(nid)
            self._children_cols[nid].set_visibility(False)
            if nid in self._arrow_elements:
                self._arrow_elements[nid].classes(remove='rotate-90')
        else:
            self._expanded.add(nid)
            self._lazy_load(nid)
            self._children_cols[nid].set_visibility(True)
            if nid in self._arrow_elements:
                self._arrow_elements[nid].classes(add='rotate-90')

    def _lazy_load(self, nid: str):
        if nid in self._resolved:
            return
        self._resolved.add(nid)
        path = self._node_paths[nid]
        col = self._children_cols[nid]
        level = len(Path(nid).relative_to(self.root_path).parts)
        with col:
            self._render_children(path, level)

    # ──────────────────────────────────────────────
    # 選択（複数トグル）
    # ──────────────────────────────────────────────

    def _toggle_select(self, nid: str):
        if nid in self._selected:
            self._selected.discard(nid)
            self._set_highlight(nid, False)
        else:
            self._selected.add(nid)
            self._set_highlight(nid, True)

    def _set_highlight(self, nid: str, active: bool):
        row = self._row_elements.get(nid)
        if not row:
            return
        if active:
            row.classes(
                add='bg-blue-100 dark:bg-blue-900',
                remove='hover:bg-gray-100 dark:hover:bg-gray-800',
            )
        else:
            row.classes(
                remove='bg-blue-100 dark:bg-blue-900',
                add='hover:bg-gray-100 dark:hover:bg-gray-800',
            )

    def _on_dblclick(self, nid: str):
        # 選択してすぐ確定
        if nid not in self._selected:
            self._selected.add(nid)
            self._set_highlight(nid, True)
        self.submit(list(self._selected))

    async def _handle_ok(self):
        if self._selected:
            self.submit(sorted(self._selected))
        else:
            self.close()
