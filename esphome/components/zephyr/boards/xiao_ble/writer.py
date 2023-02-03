import os
from ...zephyr_writer import ZephyrDirectoryBuilder


class XiaoDirectoryBuilder(ZephyrDirectoryBuilder):
    def createAppOverlayBoot(self) -> None:
        contents = self.manager.board.flash_mapping()
        contents = contents.replace("CODE_PARTITION", "boot_partition")
        with open(os.path.join(self.boot_dir, "mcuboot", "boot", "zephyr", "dts.overlay"), "a") as f:
            f.write(contents)

    def createAppOverlay(self) -> None:
        contents = '\n'.join(self.manager.device_overlay_list)
        contents += self.manager.board.flash_mapping()
        contents = contents.replace("CODE_PARTITION", "slot0_partition")
        with open(os.path.join(self.proj_dir, "app.overlay"), "w") as f:
            f.write(contents)
