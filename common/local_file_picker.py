from pathlib import Path
from nicegui import ui

class LocalFilePicker(ui.dialog):
    css_added = False
    
    def __init__(self, directory: str, *,
                 caption = "選択してください",
                 folder_only = False,
                 multiple: bool = False,
                 show_hidden_files: bool = False) -> None:
        """LocalFilePicker
        This is a simple file picker that allows you to select a file from the local filesystem where NiceGUI is running.
        :param directory: The directory to show.
        :folder_only: list directory only
        :param multiple: Whether to allow multiple files to be selected. unused.
        :param show_hidden_files: Whether to show hidden files.
        """
        super().__init__()
        
        if not LocalFilePicker.css_added:
            LocalFilePicker._add_css()
            LocalFilePicker.css_added = True

        self.path = Path(directory).expanduser()
        self.folder_only = folder_only

        self.show_hidden_files = show_hidden_files

        with self, ui.card():
            ui.label(caption)
            self.table = ui.table(
                columns=[
                    {"label": "", "field": "name", "name": "name", "align": 'left'},
                ],
                rows=[],
                selection="single",
                row_key='path',
            ).classes('h-80 w-full no-shadow brdr q-pa-none local-file-picker-table') \
            .props('hide-header hide-bottom') \
            .on('rowClick', lambda e: self._handle_row_click(e))
            
            with ui.row().classes('w-full justify-end'):
                ui.button('キャンセル', on_click=self.close).props('outline')
                ui.button('選択', on_click=self._handle_ok)
        self.update_grid()
    
    def _handle_row_click(self, e):
        row_data = e.args[1]
        self.table.selected=[row_data]
    
    def update_grid(self) -> None:
        paths = list(self.path.glob('*'))
        
        if not self.show_hidden_files:
            paths = [p for p in paths if not p.name.startswith('.')]
        paths.sort(key=lambda p: p.name.lower())
        paths.sort(key=lambda p: not p.is_dir())
        result = []
        for path in paths:
            if self.folder_only and path.is_file():
                continue
            if path.is_dir():
                name = f'📁 {path.name}'
            else:
                name = path.name
            result.append({'path': str(path), 'name':name})
        self.table.rows = result
        if len(result) > 0:
            self.table.selected = [result[0]]
        self.table.update()

    async def _handle_ok(self):
        rows = self.table.selected
        self.submit([r['path'] for r in rows])

    @classmethod
    def _add_css(cls):
        ui.add_css("""
.local-file-picker-table td:first-child, 
.local-file-picker-table th:first-child {
    display: none;
}
.local-file-picker-table .q-table__grid-item,
.local-file-picker-table {
    user-select: none;
}
.local-file-picker-table .q-table__grid-item--selected,
.local-file-picker-table .selected {
    color: #fff !important;
    background-color: var(--q-primary) !important;
}
""")


