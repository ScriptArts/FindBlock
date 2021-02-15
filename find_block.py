from datetime import datetime

import numpy
from amulet import Block
from typing import TYPE_CHECKING, Tuple, Dict
import wx

from amulet_map_editor.api.wx.ui.base_select import EVT_PICK
from amulet_map_editor.api.wx.ui.block_select import BlockDefine
from amulet_map_editor.programs.edit.plugins import OperationUI
from amulet_map_editor.programs.edit.canvas.events import EVT_BOX_CLICK

if TYPE_CHECKING:
    from amulet.api.level import World
    from amulet_map_editor.programs.edit.canvas.edit_canvas import EditCanvas


def _check_block(block: Block, original_base_name: str,
                 original_properties: Dict[str, "WildcardSNBTType"]) -> bool:
    if (block.base_name == original_base_name
            and all(
                original_properties.get(prop) in ["*", val.to_snbt()]
                for prop, val in block.properties.items()
            )
    ):
        return True
    return False


class FindBlock(wx.Panel, OperationUI):
    def __init__(
            self, parent: wx.Window, canvas: "EditCanvas", world: "World", options_path: str
    ):
        wx.Panel.__init__(self, parent)
        OperationUI.__init__(self, parent, canvas, world, options_path)

        self._sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self._sizer)

        options = self._load_options({})

        self._block_define = BlockDefine(
            self,
            world.translation_manager,
            wx.VERTICAL,
            world.world_wrapper.platform,
            wildcard_properties=True,
            show_pick_block=True
        )
        self._block_click_registered = False
        self._block_define.Bind(EVT_PICK, self._on_pick_block_button)
        self._sizer.Add(self._block_define, 1, wx.ALL | wx.ALIGN_CENTRE_HORIZONTAL, 5)

        self._run_button = wx.Button(self, label="検索開始")
        self._run_button.Bind(wx.EVT_BUTTON, self._run_operation)
        self._sizer.Add(self._run_button, 0, wx.ALL | wx.ALIGN_CENTRE_HORIZONTAL, 5)

        self.Layout()

    @property
    def wx_add_options(self) -> Tuple[int, ...]:
        return (1,)

    def _on_pick_block_button(self, evt):
        """Set up listening for the block click"""
        if not self._block_click_registered:
            self.canvas.Bind(EVT_BOX_CLICK, self._on_pick_block)
            self._block_click_registered = True
        evt.Skip()

    def _on_pick_block(self, evt):
        self.canvas.Unbind(EVT_BOX_CLICK, handler=self._on_pick_block)
        self._block_click_registered = False
        x, y, z = self.canvas.cursor_location
        self._block_define.universal_block = (
            self.world.get_block(x, y, z, self.canvas.dimension),
            None,
        )

    def unload(self):
        print("Unload FindBlock")

    def _run_operation(self, _):
        self.canvas.run_operation(
            lambda: self._find_block()
        )

    def _find_block(self):
        world = self.world
        size = 0
        count = 0
        find_block_matches = []
        now = datetime.now()
        (
            original_platform,
            original_version,
            original_blockstate,
            original_namespace,
            original_base_name,
            original_properties,
        ) = (
            self._block_define.platform,
            self._block_define.version_number,
            self._block_define.force_blockstate,
            self._block_define.namespace,
            self._block_define.block_name,
            self._block_define.str_properties,
        )

        # 全てのディメンションのチャンク数を取得
        for dimension in world.dimensions:
            size += len(list(world.all_chunk_coords(dimension)))

        print("ブロック検索プラグイン実行")
        print("総検索チャンク数:" + str(size))
        print("----------検索開始----------")

        for dimension in world.dimensions:
            for cx, cz in world.all_chunk_coords(dimension):
                chunk = world.get_chunk(cx, cz, dimension)
                palette_index = -1

                # チャンクが保持するすべてのブロックから、検索対象のブロックがあるか確認
                # この処理には問題があり、chunk.block_paletteはチャンクが保持するブロックを返却するのではなく
                # ディメンションが保持するブロックを返却してしまう模様
                for index, block in list(chunk.block_palette.items()):
                    if _check_block(block, original_base_name, original_properties):
                        palette_index = index

                # 検索対象のブロックがない場合、このチャンクの検索をスキップ
                if palette_index == -1:
                    count += 1
                    yield count / size
                    continue

                # チャンクの全ブロックを検索
                for x in range(16):
                    for y in range(256):
                        for z in range(16):
                            block = chunk.get_block(x, y, z)

                            # 検索対象のブロックと一致するか確認
                            if _check_block(block, original_base_name, original_properties):
                                world_x = x + cx * 16
                                world_z = z + cz * 16
                                print("X:" + str(world_x) + " Y:" + str(y) + " Z:" + str(world_z) + " " + dimension)
                                find_block_matches.append((str(world_x), str(y), str(world_z), dimension))
                count += 1
                yield count / size

        # 結果をファイル出力
        with open("FindBlock_" + now.strftime("%Y%m%d%H%M%S") + ".txt", "w") as f:
            f.write("x,y,z,dimension\n")
            for x, y, z, dimension in find_block_matches:
                f.write(x + "," + y + "," + z + "," + dimension + "\n")

        print("----------検索終了----------")


export = {
    "name": "ブロック検索",  # the name of the plugin
    "operation": FindBlock,  # the actual function to call when running the plugin
}
