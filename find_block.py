import os
from datetime import datetime

import numpy
from amulet import Block, SelectionBox
from typing import TYPE_CHECKING, Tuple, Dict
import wx
from amulet.api.partial_3d_array.base_partial_3d_array import BasePartial3DArray

from amulet_map_editor.api.wx.ui.base_select import EVT_PICK
from amulet_map_editor.api.wx.ui.block_select import BlockDefine
from amulet_map_editor.programs.edit.api.operations import OperationUI
from amulet_map_editor.programs.edit.api.events import EVT_BOX_CLICK

if TYPE_CHECKING:
    from amulet.api.level import World
    from amulet_map_editor.programs.edit.api.canvas import EditCanvas


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

        self._description = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP
        )
        self._sizer.Add(self._description, 0, wx.ALL | wx.EXPAND, 5)
        self._description.SetLabel("指定したブロックの座標をワールドから全て検索します。\n" +
                                   "検索した内容はFindBlockディレクトリにCSV形式で出力します。")
        self._description.Fit()

        self._block_define_label = wx.StaticText(self, wx.ID_ANY, "検索するブロック")
        self._sizer.Add(self._block_define_label, 0, wx.LEFT | wx.RIGHT, 5)

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
        self._sizer.Add(self._block_define, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.ALIGN_CENTRE_HORIZONTAL, 5)

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
        chunk_count = 0
        count = 0
        universal_block_count = 0
        file_out_list = []
        find_block_matches = []
        now = datetime.now()
        directory_name = "FindBlock"
        filepath = directory_name + "/" + now.strftime("%Y%m%d%H%M%S") + ".txt"
        (
            find_platform,
            find_version,
            find_blockstate,
            find_namespace,
            find_base_name,
            find_properties,
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
            chunk_count += len(list(world.all_chunk_coords(dimension)))

        print("ブロック検索プラグイン実行")
        print("総検索チャンク数:" + str(chunk_count))
        print("----------検索開始----------")

        for dimension in world.dimensions:
            for cx, cz in world.all_chunk_coords(dimension):
                chunk = world.get_chunk(cx, cz, dimension)

                # チャンクで使用されているブロックのパレットに、今までループしたチャンクのパレットにないブロックがある場合
                if universal_block_count < len(chunk.block_palette):
                    for universal_block_id in range(
                            universal_block_count, len(chunk.block_palette)
                    ):
                        # ブロックを取得
                        version_block = world.translation_manager.get_version(
                            find_platform, find_version
                        ).block.from_universal(
                            world.block_palette[universal_block_id],
                            force_blockstate=find_blockstate,
                        )[
                            0
                        ]

                        # ブロックが検索対象のブロックと一致する場合
                        if _check_block(version_block, find_base_name, find_properties):
                            find_block_matches.append(universal_block_id)

                    # パレットのブロック数を更新
                    universal_block_count = len(chunk.block_palette)

                # 検索対象のブロックと一致したブロックのチャンク座標を全て取得
                chunk_pos_list = numpy.argwhere(numpy.isin(chunk.blocks, find_block_matches))
                for chunk_pos in chunk_pos_list:
                    x = chunk_pos[0] + cx * 16
                    y = chunk_pos[1]
                    z = chunk_pos[2] + cz * 16
                    print("X:" + str(x) + " Y:" + str(y) + " Z:" + str(z) + " " + dimension)
                    file_out_list.append((str(x), str(y), str(z), dimension))

                count += 1
                yield count / chunk_count

        print("----------検索終了----------")
        print("検索結果出力 -> " + filepath)

        # ディレクトリ生成
        os.makedirs(directory_name, exist_ok=True)

        # 結果をファイル出力
        with open(filepath, "w") as f:
            f.write("x,y,z,dimension\n")
            for x, y, z, dimension in file_out_list:
                f.write(x + "," + y + "," + z + "," + dimension + "\n")


export = {
    "name": "ブロック検索",  # the name of the plugin
    "operation": FindBlock,  # the actual function to call when running the plugin
}
