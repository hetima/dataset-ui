from pathlib import Path
import time
from nicegui import ui
import platform


class FolderPicker(ui.dialog):
    def __init__(
        self,
        directory: str,
        *,
        caption: str = "フォルダを選択してください",
        show_hidden_files: bool = False,
        read_all: bool = False,
    ) -> None:
        super().__init__()

        if platform.system() == "Windows":
            import ctypes

            self.double_click_interval = ctypes.windll.user32.GetDoubleClickTime()
        else:
            self.double_click_interval = 500

        client = ui.context.client
        if not hasattr(client, "folder_picker_css_loaded"):
            FolderPicker._add_css()
            client.folder_picker_css_loaded = True  # type: ignore

        self.root_path = Path(directory).expanduser()
        self.show_hidden_files = show_hidden_files
        self.read_all = read_all
        self._selected_path: str | None = None
        self._prev_selected_path: str | None = None
        self._expanded_set: set[str] = set()
        self._resolved_set: set[str] = set()
        self._last_select_time: float = 0.0

        with self, ui.card().classes("w-140 h-150"):
            ui.label(caption)
            search = (
                ui.input(label="filter", placeholder="filter")
                .classes("w-full")
                .props("outlined clearable")
            )
            nodes = self._build_tree(self.root_path)
            self.tree = (
                ui.tree(
                    nodes=nodes,
                    node_key="id",
                    label_key="label",
                    on_select=self._handle_select,
                    on_expand=self._handle_expand,
                )
                .bind_filter_from(search, "value")
                .classes("h-full w-full brdr folder-picker-tree")
                .props("dense no-transition no-connectors")
            )

            with ui.row().classes("w-full justify-end"):
                ui.button("キャンセル", on_click=self.close).props("outline")
                ui.button("選択", on_click=self._handle_ok)
        js_code = """
(e) => {
    const targetKeys = ['ArrowUp', 'ArrowDown', 'Enter'];
    if (targetKeys.includes(e.key)) {
        e.preventDefault();
        e.stopPropagation(); 
        emit({key: e.key});
    }
}
"""
        self.tree.on("keydown", self._on_key_down, js_handler=js_code)
        # self._setup_events()
        # self.tree.props('tabindex="0"')

    # 上下キーで選択範囲移動 動かない
    def _setup_events(self):
        js_code = f"""
        (e) => {{
            const targetKeys = ['ArrowUp', 'ArrowDown'];
            if (targetKeys.includes(e.key)) {{
                e.preventDefault();
                e.stopPropagation();
                
                // 上流にあるツリーのルートコンテナ(.q-tree)を取得
                const treeEl = e.target.closest('.q-tree');
                if (!treeEl) return;
                
                // 現在画面に表示されているノード(.q-tree__node)を全件取得
                const nodeElements = treeEl.querySelectorAll('.q-tree__node');
                const visible_ids = [];
                
                
                nodeElements.forEach(el => {{
                    // ノードのテキスト部分かクラス名('label' 'class')しか取れない
                    const labelEl = el.querySelector('.q-tree__node-header-content');
                    if (labelEl) {{
                        const labelText = labelEl.innerText.trim();
                        visible_ids.push(labelText);

                    }}
                }});
                
                // 現在選択されているIDを取得（DOMのaria属性などから）
                let current_id = null;
                const selectedEl = treeEl.querySelector('.q-tree__node--selected .q-tree__node-header-content');
                if (selectedEl) {{
                    current_id = selectedEl.innerText.trim();
                }}
                
                emit({{
                    key: e.key,
                    current_id: current_id,
                    visible_ids: visible_ids
                }});
            }}
        }}
        """
        self.tree.on("keydown", self._on_key_down, js_handler=js_code)

    def _move_selection(self, current_id: str, visible_ids: list, step: int):
        """現在の選択位置から、指定ステップ数だけ移動する"""
        if not visible_ids:
            return

        # 現在選択されているノードの、可視リスト内でのインデックスを探す
        try:
            current_index = visible_ids.index(current_id)
        except ValueError:
            current_index = 0

        # 安全にインデックスを循環させる
        next_index = (current_index + step) % len(visible_ids)
        target_id = visible_ids[next_index]

        # 選択を更新
        self.tree.select(target_id)

    def _on_key_down(self, e) -> None:
        key = e.args.get("key")
        current_id = e.args.get("current_id")
        visible_ids = e.args.get("visible_ids", [])
        if key == "ArrowDown":
            self._move_selection(current_id, visible_ids, 1)
        elif key == "ArrowUp":
            self._move_selection(current_id, visible_ids, -1)
        elif key == "Enter":
            ui.timer(0, self._handle_ok, once=True)

    def _filter_path(self, p: Path) -> bool:
        if not p.is_dir():
            return False
        if not self.show_hidden_files and p.name.startswith("."):
            return False
        return True

    def _scan_subfolders(self, path: Path) -> list[Path]:
        try:
            paths = [p for p in path.iterdir() if self._filter_path(p)]
        except PermissionError:
            return []
        paths.sort(key=lambda p: p.name.lower())
        return paths

    def _has_subfolders(self, path: Path) -> bool:
        try:
            return any(self._filter_path(p) for p in path.iterdir())
        except PermissionError:
            return False

    def _build_node(self, path: Path) -> dict:
        node: dict = {
            "id": str(path),
            "label": f"📁 {path.name}" if path != self.root_path else f"📁 {path}",
        }
        if self.read_all:
            subs = self._scan_subfolders(path)
            if subs:
                node["children"] = [self._build_node(p) for p in subs]
        elif self._has_subfolders(path):
            node["children"] = [{"id": f"__placeholder__:{path}", "label": ""}]
        return node

    def _build_tree(self, root: Path) -> list[dict]:
        subs = self._scan_subfolders(root)
        children = [self._build_node(p) for p in subs]
        if self.read_all:
            self._collect_resolved(children)
        return children

    def _collect_resolved(self, nodes: list[dict]) -> None:
        for node in nodes:
            nid = node.get("id", "")
            self._resolved_set.add(nid)
            ch = node.get("children")
            if ch:
                self._collect_resolved(ch)

    def _is_placeholder(self, children: list[dict]) -> bool:
        return len(children) == 1 and str(children[0].get("id", "")).startswith(
            "__placeholder__"
        )

    def _resolve_node(self, node_id: str) -> None:
        if node_id in self._resolved_set:
            return
        self._resolved_set.add(node_id)

        path = Path(node_id)

        def _find_and_fill(nodes: list[dict]) -> bool:
            for node in nodes:
                if node.get("id") == node_id:
                    subs = self._scan_subfolders(path)
                    node["children"] = [self._build_node(p) for p in subs]
                    return True
                children = node.get("children")
                if children and _find_and_fill(children):
                    return True
            return False

        _find_and_fill(self.tree._props["nodes"])
        self.tree.update()

    def _handle_select(self, e) -> None:
        now = time.monotonic() * 1000
        elapsed = now - self._last_select_time
        if 100 < elapsed < self.double_click_interval:
            # ガバガバダブルクリック判定 たまにミスる
            selection = e.value or self._selected_path
            prev = self._selected_path or self._prev_selected_path
            x = prev and selection != prev
            if not x and selection:
                self.submit([selection])
            return
        if e.value:
            self._prev_selected_path = self._selected_path
        self._selected_path = e.value
        self._last_select_time = now

    def _handle_expand(self, e) -> None:
        if e.value is None:
            return
        current = set(e.value)
        newly_expanded = current - self._expanded_set
        self._expanded_set = current
        for node_id in newly_expanded:
            self._resolve_node(node_id)

    async def _handle_ok(self) -> None:
        if self._selected_path:
            self.submit([self._selected_path])
        else:
            self.close()

    @classmethod
    def _add_css(cls) -> None:
        ui.add_css(
            """
.folder-picker-tree {
    user-select: none;
    overflow-y: auto;
    outline: none;
}

.folder-picker-tree .q-tree__node-header-content {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.folder-picker-tree .q-tree__node--selected {
    background-color: var(--q-primary) !important;
    border-radius: 3px;
}

.folder-picker-tree .q-tree__node--selected .q-tree__node-header-content {
    color: #f4f4f4 !important;
}
"""
        )
