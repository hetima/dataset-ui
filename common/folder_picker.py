from pathlib import Path
from nicegui import ui


class FolderPicker(ui.dialog):
    """フォルダ選択ダイアログ。await して [path_str] または None を返す。"""

    def __init__(
        self,
        directory: str,
        *,
        caption: str = "フォルダを選択してください",
        show_hidden_files: bool = False,
        show_files_count: list[str] | None = None,
    ) -> None:
        super().__init__()

        self.root_path = Path(directory).expanduser()
        self.show_hidden_files = show_hidden_files
        # 拡張子は小文字・ドット付きに正規化（例: 'wav' → '.wav'）
        self._count_exts: set[str] | None = (
            {('.' + e.lstrip('.').lower()) for e in show_files_count}
            if show_files_count else None
        )
        self._selected_path: str | None = None

        # nid -> 子コンテナ / 行要素 / 矢印アイコン
        self._children_cols: dict[str, ui.element] = {}
        self._row_elements: dict[str, ui.element] = {}
        self._arrow_elements: dict[str, ui.icon] = {}
        self._expanded: set[str] = set()
        # 遅延ロード済みノード
        self._resolved: set[str] = set()
        # nid -> Path（遅延ロード用）
        self._node_paths: dict[str, Path] = {}

        with self, ui.card().classes('h-150 flex flex-col gap-2'):
            ui.label(caption).classes('text-base font-semibold')

            with ui.column().classes('w-96 flex-1 overflow-y-auto border rounded p-1 select-none gap-0'):
                self._render_children(self.root_path, level=0)

            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('キャンセル', on_click=self.close).props('outline')
                ui.button('選択', on_click=self._handle_ok)

    # ──────────────────────────────────────────────
    # ツリー描画
    # ──────────────────────────────────────────────

    def _scan(self, path: Path) -> list[Path]:
        try:
            paths = [
                p for p in path.iterdir()
                if p.is_dir() and (self.show_hidden_files or not p.name.startswith('.'))
            ]
        except PermissionError:
            return []
        paths.sort(key=lambda p: p.name.lower())
        return paths

    def _count_files(self, path: Path) -> int | None:
        """対象拡張子ファイルの直下件数を返す。show_files_count 未設定時は None。"""
        if self._count_exts is None:
            return None
        try:
            return sum(
                1 for p in path.iterdir()
                if p.is_file() and p.suffix.lower() in self._count_exts
            )
        except PermissionError:
            return None

    def _has_children(self, path: Path) -> bool:
        try:
            return any(
                p.is_dir() and (self.show_hidden_files or not p.name.startswith('.'))
                for p in path.iterdir()
            )
        except PermissionError:
            return False

    def _render_children(self, path: Path, level: int):
        """path 直下のサブフォルダを描画する"""
        for sub in self._scan(path):
            self._render_node(sub, level)

    def _render_node(self, path: Path, level: int):
        nid = str(path)
        self._node_paths[nid] = path
        has_ch = self._has_children(path)
        indent = level * 20
        label = path.name or str(path)  # ルート直下はフルパス

        with ui.row().classes(
            'items-center w-full cursor-pointer rounded px-1 py-0.5 '
            'hover:bg-gray-100 dark:hover:bg-gray-800 gap-1'
        ).style(f'padding-left: {8 + indent}px') as row:
            self._row_elements[nid] = row

            # 展開矢印
            if has_ch:
                arrow = ui.icon('chevron_right', size='xs').classes(
                    'transition-transform duration-150 text-gray-500 flex-shrink-0'
                )
                self._arrow_elements[nid] = arrow
                arrow.on('click.stop', lambda _, n=nid: self._toggle_expand(n))
            else:
                ui.element('div').style('width: 16px; height: 16px; flex-shrink: 0')

            ui.icon('folder', size='xs').classes('text-yellow-600 flex-shrink-0')
            ui.label(label).classes('text-sm truncate flex-1')
            count = self._count_files(path)
            if count is not None:
                ui.label(f'({count})').classes('text-xs text-gray-400 flex-shrink-0')

            # フォルダ選択モード: 行クリック=選択トグル
            row.on('click', lambda _, n=nid: self._toggle_select(n))
            row.on('dblclick', lambda _, n=nid: self._on_dblclick(n))

        # 子コンテナ（遅延ロード、初期非表示）
        if has_ch:
            with ui.column().classes('w-full gap-0') as col:
                col.set_visibility(False)
                self._children_cols[nid] = col

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
        """初回展開時に子ノードを描画する"""
        if nid in self._resolved:
            return
        self._resolved.add(nid)
        path = self._node_paths[nid]
        col = self._children_cols[nid]
        level = len(Path(nid).relative_to(self.root_path).parts)
        with col:
            self._render_children(path, level)

    # ──────────────────────────────────────────────
    # 選択
    # ──────────────────────────────────────────────

    def _toggle_select(self, nid: str):
        prev = self._selected_path
        if prev == nid:
            self._selected_path = None
            self._set_highlight(nid, False)
        else:
            if prev and prev in self._row_elements:
                self._set_highlight(prev, False)
            self._selected_path = nid
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
        self._toggle_select(nid)
        if self._selected_path:
            self.submit([self._selected_path])

    async def _handle_ok(self):
        if self._selected_path:
            self.submit([self._selected_path])
        else:
            self.close()
