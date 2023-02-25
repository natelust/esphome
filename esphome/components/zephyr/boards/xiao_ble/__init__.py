from __future__ import annotations
from textwrap import dedent
from typing import Tuple, Mapping, List, TYPE_CHECKING

from ..nrf52840_base import NRF52840Base, GPIO_0, GPIO_1
from .. import registry
from .writer import XiaoDirectoryBuilder
from esphome.core import CORE

import os
import warnings
from shutil import which, copy
import psutil
import time

from esphome.util import run_external_process

if TYPE_CHECKING:
    from ...zephyr_writer import ZephyrDirectoryBuilder

pinMapping = {
    "D0": (GPIO_0, 2),
    "D1": (GPIO_0, 3),
    "D2": (GPIO_0, 28),
    "D3": (GPIO_0, 29),
    "D4": (GPIO_0, 4),  # external sda
    "D5": (GPIO_0, 5),  # external scl
    "D6": (GPIO_1, 11),  # TX
    "D7": (GPIO_1, 12),  # RX
    "D8": (GPIO_1, 13),  # sck
    "D9": (GPIO_1, 14),  # MISO
    "D10": (GPIO_1, 15),  # MOSI
    "P0.02": (GPIO_0, 2),
    "P0.03": (GPIO_0, 3),
    "P0.28": (GPIO_0, 28),
    "P0.29": (GPIO_0, 29),
    "P0.04": (GPIO_0, 4),  # external sda
    "P0.05": (GPIO_0, 5),  # external scl
    "P1.11": (GPIO_1, 11),  # TX
    "P1.12": (GPIO_1, 12),  # RX
    "P1.13": (GPIO_1, 13),  # sck
    "P1.14": (GPIO_1, 14),  # MISO
    "P1.15": (GPIO_1, 15),  # MOSI
    "P0.07": (GPIO_0, 7),  # internal sda
    "P0.27": (GPIO_0, 27),  # internal scl
    "P0.31": (GPIO_0, 31),  # battery read
    "P0.06": (GPIO_0, 6),   # blue led
    "P0.26": (GPIO_0, 26),   # red led
    "P0.30": (GPIO_0, 30),   # green led
    "P0.16": (GPIO_0, 16),  # PDM on sense model
    "P0.14": (GPIO_0, 14),  # Battery sink
    "P1.08": (GPIO_1, 8),  # Internal power for LSM6DS3 on sense variant
}

analogMapping: Mapping[str, int] = {
    "A0": (GPIO_0, 2),
    "A1": (GPIO_0, 3),
    "A2": (GPIO_0, 28),
    "A3": (GPIO_0, 29),
    "A4": (GPIO_0, 4),  # external sda
    "A5": (GPIO_0, 5),  # external scl
    "A7": (GPIO_0, 31),  # battery read
    "P0.02": (GPIO_0, 2),
    "P0.03": (GPIO_0, 3),
    "P0.28": (GPIO_0, 28),
    "P0.29": (GPIO_0, 29),
    "P0.04": (GPIO_0, 4),  # external sda
    "P0.05": (GPIO_0, 5),  # external scl
    "P0.31": (GPIO_0, 31),  # battery read

}


@registry.register("xiao_ble")
class XiaoBle(NRF52840Base):
    def __init__(self, mangager, board_args, *args, **kwargs) -> None:
        super().__init__(mangager, board_args, *args, **kwargs)
        self.hardware_i2c_devices = ["i2c0", "i2c1"]

    def get_board_KConfig(self) -> list[tuple[str, str]]:
        configs = super().get_board_KConfig()
        configs.extend((
            ("CONFIG_SPI", "y"),
            ("CONFIG_MCUBOOT_GENERATE_CONFIRMED_IMAGE", 'y'),
            ("CONFIG_SPI_NOR_FLASH_LAYOUT_PAGE_SIZE", 4096),
            ("CONFIG_MCUMGR_TRANSPORT_SHELL", "y"),
            ("CONFIG_LOG_MODE_IMMEDIATE", "y"),
            ("CONFIG_GPIO_SHELL", "y"),
            ("CONFIG_I2C_SHELL", "y"),
            ("CONFIG_DEVICE_SHELL", 'y'),
        ))
        return configs

    def __str__(self):
        return "xiao_ble"

    def board_setup(self) -> str:
        if 'sensor' in CORE.config:
            for sens in CORE.config['sensor']:
                if sens['platform'] == 'LSM6DS3':
                    # The sensor pin should be turned on to be used
                    return dedent("""
                        #include <hal/nrf_gpio.h>
                        void board_setup() {
                            nrf_gpio_cfg(40, NRF_GPIO_PIN_DIR_OUTPUT, NRF_GPIO_PIN_INPUT_DISCONNECT, NRF_GPIO_PIN_NOPULL, NRF_GPIO_PIN_H0H1, NRF_GPIO_PIN_NOSENSE);
                            nrf_gpio_pin_set(40);
                        }
                    """)
        return super().board_setup()

    def flash_mapping(self) -> str:
        mapping = dedent("""
        /delete-node/ &code_partition;
        /delete-node/ &boot_partition;

        / {
            chosen {
                zephyr,code-partition = &CODE_PARTITION;
                zephyr,console = &uart0;
            };
        };

        &flash0 {
            partitions {
                boot_partition: partition@27000 {
                    label = "mcuboot";
                    reg = < 0x00027000 0x16000 >;
                };
                slot0_partition: partition@3d000 {
                    label = "image-0";
                    reg = < 0x3d000 0xaf000>;
                };
                uf2_boot_partition: partition@f4000 {
                    label = "adafruit_boot";
                    reg = <0x000f4000 0x0000c000>;
                };
            };
        };

        &p25q16h_spi {
            partitions {
                compatible = "fixed-partitions";
                #address-cells = <1>;
                #size-cells = <1>;


                slot1_partition: partition@0 {
                        label = "image-1";
                        reg = <0x0 0xaf000>;
                };
            };
        };
        """)
        return mapping

    def pre_compile_bootloader(self, args: List[str]) -> List[str]:
        args = super().pre_compile_bootloader(args)
        args.extend(("-DCONFIG_MULTITHREADING=y",
                     "-DCONFIG_SPI_NOR_FLASH_LAYOUT_PAGE_SIZE=4096",
                     "-DCONFIG_BOOT_MAX_IMG_SECTORS=256",
                     "-DCONFIG_SPI=y",
                     #"-DCONFIG_LOG_MAX_LEVEL=2",
                     #"-DCONFIG_SIZE_OPTIMIZATIONS=y",
                     "-DCONFIG_MCUBOOT_LOG_LEVEL_DBG=y",
                     #"-DCONFIG_MCUBOOT_UTIL_LOG_LEVEL_DBG=y",
                     #"-DCONFIG_BOOT_DIRECT_XIP=y",
                     "-DCONFIG_BOOT_SWAP_USING_MOVE=y",
                     "-DCONFIG_BUILD_OUTPUT_UF2=y",
                     #"-DCONFIG_SIZE_OPTIMIZATIONS=y",
                     "-DCONFIG_SERIAL=y",
                     #"-DCONFIG_LOG=n",
                     #"-DCONFIG_UART_NRFX=y",
                     #"-DCONFIG_UART_INTERRUPT_DRIVEN=y",
                     #"-DCONFIG_UART_LINE_CTRL=y",
                     #"-DCONFIG_GPIO=y",
                     #"-DCONFIG_USB_DEVICE_STACK=y",
                     #"-DCONFIG_USB_DEVICE_REMOTE_WAKEUP=n",
                     '-DCONFIG_USB_DEVICE_PRODUCT="DFU MCUBOOT"',
                     #"-DCONFIG_USB_COMPOSITE_DEVICE=n",
                     #"-DCONFIG_USB_MASS_STORAGE=n",
                     #"-DCONFIG_LOG=n",
                     "-DCONFIG_BOOTLOADER_BOSSA=y",
                     "-DCONFIG_BOOTLOADER_BOSSA_ADAFRUIT_UF2=y",
                     #"-DCONFIG_BOOT_USB_DFU_WAIT=y",
                     #"-DCONFIG_BOOT_USB_DFU_WAIT_DELAY_MS=5000",
                     #"-DCONFIG_USB_DFU_CLASS=y"
                     #"-DCONFIG_USB_CDC_ACM=n",
                     "-DCONFIG_I2C=n",
                     #"-DCONFIG_LOG_BACKEND_UART=y",
                     #"-DCONFIG_LOG_MODE_IMMEDIATE=y",
                     #"-DCONFIG_MCUMGR=y",
                     #"-DCONFIG_MCUMGR_GRP_IMG=y",
                     "-DCONFIG_BOOT_SERIAL_WAIT_FOR_DFU=y",
                     "-DCONFIG_BOOT_SERIAL_WAIT_FOR_DFU_TIMEOUT=5000",
                     "-DCONFIG_BOOT_SERIAL_UART=y",
                     "-DCONFIG_MCUBOOT_SERIAL=y",
                     "-DCONFIG_UART_CONSOLE=n",
                     "-DCONFIG_BOOT_SERIAL_DETECT_PIN=2"
                     ))
        return args

    @property
    def pinMapping(self) -> Mapping[str, Tuple[str, int]]:
        return pinMapping

    @property
    def analogMapping(self) -> Mapping[str, int]:
        return analogMapping

    def get_writer(self) -> ZephyrDirectoryBuilder:
        return XiaoDirectoryBuilder(self._manager)

    def i2c_arg_parser(self, kwargs):
        if kwargs['sda'] == 'SDA':
            kwargs['sda'] = "D4"
        if kwargs['scl'] == 'SCL':
            kwargs['scl'] = "D5"
        hardware, device = super().i2c_arg_parser(kwargs)
        return hardware, device

    def spi_pins(self, clk=None, mosi=None, miso=None) -> Mapping[str, str]:
        if clk is None:
            clk = "D8"
        if mosi is None:
            mosi = "D10"
        if miso is None:
            miso = "D9"
        return super().spi_pins(clk, mosi, miso)

    def i2c_hardware_handler(self, device: str, kwargs):
        if device == 'i2c0':
            warnings.warn(
                "i2c0 cannot be used in combination with spi, disabling spi",
                ResourceWarning)
            self._manager.device_overlay_list.append(dedent("""
            &spi0 {
                status = "disabled";
            };
            """))
        return super().i2c_hardware_handler(device, kwargs)

    def upload(self, flash_args: str, boot_dir: os.PathLike,
               proj_dir: os.PathLike, boot_info_path: os.PathLike,
               bootloader: bool, host: str) -> int:
        if which("mcumgr") is None:
            raise ValueError(f"mcumgr must be installed to upload to {self}")
        if not bootloader:
            mount_points = [(x.mountpoint, x.mountpoint) for x in psutil.disk_partitions(all=True)]
            from esphome.__main__ import choose_prompt
            mountpoint = choose_prompt(mount_points)

            # copy the mcubootloader
            try:
                copy(os.path.join(boot_dir, 'build/zephyr/zephyr.uf2'),
                     os.path.join(mountpoint, 'zephyr.uf2'))
            except (FileNotFoundError, OSError):
                # This is thrown because the board reboots right away and copy
                # thinks it should still be there
                pass

            # if this succeded write the indicator that mcuboot has been
            # installed
            with open(boot_info_path, 'w') as f:
                f.write("")

            # wait for it to reboot before trying to flash the image
            time.sleep(2)
            from esphome.__main__ import choose_upload_log_host
            host = choose_upload_log_host(None, None, False, False, False)

        print("### FLASHING APPLICATION #####")
        image_args = ["mcumgr",
                      "--conntype=serial",
                      f"--connstring=dev={host},baud=115200,mtu=512",
                      "image",
                      "upload",
                      "-e",
                      f"{proj_dir}/build/zephyr/zephyr.signed.bin"
                      ]
        result = run_external_process(*image_args)
        if result != 0:
            print("failed to upload image, is your board in boot mode?")
            return result

        restart_args = ["mcumgr",
                        "--conntype=serial",
                        f"--connstring=dev={host},baud=115200",
                        "reset"
                        ]
        result = run_external_process(*restart_args)
        if result != 0:
            print("Failed to restart device through serial connection")
        return result
