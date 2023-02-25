from textwrap import dedent
from typing import Tuple, Mapping, List
import os
import time
import psutil

from ..nrf52840_base import NRF52840Base, GPIO_0, GPIO_1
from .. import registry, BaseZephyrBoard

from shutil import which, copy
import esphome.config_validation as cv
from esphome.util import run_external_process


pinMapping = {
    "D0": (GPIO_0, 25),  # UART TX
    "D1": (GPIO_0, 24),  # UARD RX
    "D2": (GPIO_0, 10),  # NRF2
    "D3": (GPIO_1, 15),  # led1
    "D4": (GPIO_1, 10),  # led2
    "D5": (GPIO_1, 8),
    "D6": (GPIO_0, 7),
    "D7": (GPIO_1, 2),  # button
    "D8": (GPIO_0, 16),  # NeoPixel
    "D9": (GPIO_0, 26),
    "D10": (GPIO_0, 27),
    "D11": (GPIO_0, 6),
    "D12": (GPIO_0, 8),
    "D13": (GPIO_1, 9),
    "D14": (GPIO_0, 4),
    "D15": (GPIO_0, 5),
    "D16": (GPIO_0, 30),
    "D17": (GPIO_0, 28),
    "D18": (GPIO_0, 2),
    "D19": (GPIO_0, 3),
    "D20": (GPIO_0, 29),  # Battery
    "D21": (GPIO_0, 31),  # ARef
    "A0": (GPIO_0, 4),
    "A1": (GPIO_0, 5),
    "A2": (GPIO_0, 30),
    "A3": (GPIO_0, 28),
    "A4": (GPIO_0, 2),
    "A5": (GPIO_0, 3),
    "A6": (GPIO_0, 29),  # Battery
    "A7": (GPIO_0, 31),  # Aref
    "D22": (GPIO_0, 12),  # SDA
    "D23": (GPIO_0, 11),  # SCL
    "D24": (GPIO_0, 15),  # MISO
    "D25": (GPIO_0, 13),  # MOSI
    "D26": (GPIO_0, 14),  # SCK
    "D27": (GPIO_0, 19),  # QSPI CLK
    "D28": (GPIO_0, 20),  # QSPI CS
    "D29": (GPIO_0, 17),  # QSPI Data0
    "D30": (GPIO_0, 22),  # QSPI Data1
    "D31": (GPIO_0, 23),  # QSPI Data2
    "D32": (GPIO_0, 21),  # QSPI Data3
    "D33": (GPIO_0, 9)  # NRF1 (bottom)
}

analogMapping: Mapping[str, int] = {
    "A0": 0,
    "A1": 1,
    "A2": 2,
    "A3": 3,
    "A4": 4,
    "A5": 5,
    "A6": 6,
    "A7": 7,
    "D14": 0,
    "D15": 1,
    "D16": 2,
    "D17": 3,
    "D18": 4,
    "D19": 5,
    "D20": 6,
    "D21": 7,
}


@registry.register("adafruit_feather_nrf52840")
class AdafruitFeatherNrf52840(NRF52840Base):
    def get_board_KConfig(self) -> list[tuple[str, str]]:
        configs = super().get_board_KConfig()
        configs.extend((
            ("CONFIG_NORDIC_QSPI_NOR", "y"),
            ("CONFIG_NORDIC_QSPI_NOR_FLASH_LAYOUT_PAGE_SIZE", 4096),
            ("CONFIG_NORDIC_QSPI_NOR_STACK_WRITE_BUFFER_SIZE", 16),
        ))
        return configs

    def __str__(self):
        return "adafruit_feather_nrf52840"

    def flash_mapping(self) -> str:
        mapping_west = dedent("""
        /delete-node/ &slot1_partition;

        &slot0_partition {
            reg = < 0x0000C000 0xce000 >;
        };

        &gd25q16 {
            partitions {
                compatible = "fixed-partitions";
                #address-cells = <1>;
                #size-cells = <1>;


                slot1_partition: partition@0 {
                        label = "image-1";
                        reg = <0x0 0xce000>;
                };
            };
        };
        """)

            #zephyr,console = &cdc_acm_uart0;
        mapping_uf2 = dedent("""

        / {
            chosen {
            zephyr,console = &cdc_acm_uart0;
            zephyr,shell-uart = &cdc_acm_uart0;
            zephyr,uart-mcumgr = &cdc_acm_uart0;
            };
            aliases {
                bootloader-led0 = &led1;
                mcuboot-led0 = &led1;
            };
        };


        /delete-node/ &boot_partition;
        /delete-node/ &slot0_partition;
        /delete-node/ &slot1_partition;
        /delete-node/ &scratch_partition;
        /delete-node/ &storage_partition;

        &usbd {
            cdc_acm_uart0: cdc_acm_uart0 {
                compatible = "zephyr,cdc-acm-uart";
                label = "CDC_ACM_0";
            };
        };

        &flash0 {
            partitions {
                boot_partition: partition@26000 {
                    label = "mcuboot";
                    reg = <0x26000 0x11000>;
                };
                slot0_partition: partition@37000 {
                    label = "image-0";
                    reg = <0x37000 0x97000>;
                };
                scratch_partition: partition@ce000 {
                    label = "image-scratch";
                    reg = <0xce000 0x0001e000>;
                };
                storage_partition: partition@ec000 {
                    label = "storage";
                    reg = <0xec000 0x00008000>;
                };
                uf2_boot_partition: partition@f4000 {
                    label = "adafruit_boot";
                    reg = <0x000f4000 0x0000c000>;
                };
            };
        };

        &gd25q16 {
            partitions {
                compatible = "fixed-partitions";
                #address-cells = <1>;
                #size-cells = <1>;


                slot1_partition: partition@0 {
                        label = "image-1";
                        reg = <0x0 0x97000>;
                };
            };
        };
        """)
        if self._args.get("use_west"):
            return mapping_west
        return mapping_uf2

    def pre_compile_bootloader(self, args: List[str]) -> List[str]:
        args = super().pre_compile_bootloader(args)
        args.extend(("-DCONFIG_MULTITHREADING=y",
                     "-DCONFIG_BOOT_MAX_IMG_SECTORS=256",
                     "-DCONFIG_NORDIC_QSPI_NOR=y",
                     "-DCONFIG_NORDIC_QSPI_NOR_FLASH_LAYOUT_PAGE_SIZE=4096",
                     "-DCONFIG_NORDIC_QSPI_NOR_STACK_WRITE_BUFFER_SIZE=16",
                     "-DCONFIG_LOG_MAX_LEVEL=4",
                     "-DCONFIG_SIZE_OPTIMIZATIONS=y",
                     "-DCONFIG_MCUBOOT_LOG_LEVEL_DBG=y",
                     "-DCONFIG_MCUBOOT_UTIL_LOG_LEVEL_DBG=y"))
        if not self._args.get("use_west"):
            args.extend((
                "-DCONFIG_BUILD_OUTPUT_UF2=y",
                "-DCONFIG_BOOT_SERIAL_WAIT_FOR_DFU=y",
                "-DCONFIG_BOOT_SERIAL_WAIT_FOR_DFU_TIMEOUT=7000",
                "-DCONFIG_BOOT_SERIAL_UART=y",
                "-DCONFIG_MCUBOOT_SERIAL=y",
                "-DCONFIG_BOOTLOADER_BOSSA=y",
                "-DCONFIG_BOOTLOADER_BOSSA_ADAFRUIT_UF2=y",
                "-DCONFIG_BOOT_SERIAL_DETECT_PIN=33",
                "-DCONFIG_UART_CONSOLE=n",
                "-DCONFIG_USB_CDC_ACM=y",
                "-DCONFIG_USB_DEVICE_STACK=y",
                "-DCONFIG_BOOT_SERIAL_CDC_ACM=y",
                "-DCONFIG_USB_DEVICE_INITIALIZE_AT_BOOT=y",
                "-DCONFIG_MCUBOOT_INDICATION_LED=y"
            ))
        return args

    @property
    def pinMapping(self) -> Mapping[str, Tuple[str, int]]:
        return pinMapping

    @property
    def analogMapping(self) -> Mapping[str, int]:
        return analogMapping

    def i2c_arg_parser(self, kwargs):
        if kwargs['sda'] == 'SDA':
            kwargs['sda'] = "D22"
        if kwargs['scl'] == 'SCL':
            kwargs['scl'] = "D23"
        hardware, device = super().i2c_arg_parser(kwargs)
        return hardware, device

    def upload(self, flash_args: str, boot_dir: os.PathLike,
               proj_dir: os.PathLike, boot_info_path: os.PathLike,
               bootloader: bool, host: str) -> int:
        if self._args.get("use_west"):
            return BaseZephyrBoard.upload(self)
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
            time.sleep(5)
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

    def spi_pins(self, clk=None, mosi=None, miso=None) -> Mapping[str, str]:
        if clk is None:
            clk = "D26"
        if mosi is None:
            mosi = "D25"
        if miso is None:
            miso = "D24"
        return super().spi_pins(clk, mosi, miso)
