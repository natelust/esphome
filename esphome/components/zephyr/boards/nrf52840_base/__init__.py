from __future__ import annotations

import os
from shutil import which
from abc import abstractmethod
import textwrap
from typing import Tuple, Mapping
import time
from itertools import count

from esphome.util import run_external_process

from ..baseBoard import BaseZephyrBoard

import esphome.config_validation as cv

GPIO_0 = "gpio0"
GPIO_1 = "gpio1"


class NRF52840Base(BaseZephyrBoard):
    def __init__(self, mangager, board_args, *args, **kwargs) -> None:
        super().__init__(mangager, board_args=board_args)
        self.hardware_i2c_devices = ["i2c0"]
        self.pin_control_counter = count()

    @property
    @abstractmethod
    def pinMapping(self) -> Mapping[str, Tuple[str, int]]:
        raise NotImplementedError("Not implemented on the base class")

    @property
    @abstractmethod
    def analogMapping(self) -> Mapping[str, int]:
        raise NotImplementedError("Not implemented on the base class")

    @abstractmethod
    def __str__(self):
        raise NotImplementedError("Not implemented on the base class")

    def validate_gpio_pin(self, value):
        # do nothing for now, fix this later
        return value

    def validate_supports(self, value):
        # do nothing for now, fix this later
        return value

    def get_device_and_pin(self, pin):
        value = self.pinMapping.get(pin)
        if value is None:
            raise NotImplementedError(f"Cannot handle pin specifier {pin}, "
                                      f"must be one of {self.pinMapping.keys()}")
        return value

    def can_openthread(self) -> bool:
        return True

    def i2c_arg_parser(self, kwargs):
        from esphome.components.i2c import CONF_ZEPHYR_I2C_DEVICE
        if self.hardware_i2c_devices:
            hardware = True
            if kwargs[CONF_ZEPHYR_I2C_DEVICE] != '':
                conf_device = kwargs[CONF_ZEPHYR_I2C_DEVICE]
                if conf_device in self.hardware_i2c_devices:
                    self.hardware_i2c_devices.remove(conf_device)
                    device = conf_device
                else:
                    raise ValueError(f"Selected i2c device {conf_device} is not setup for this board")
            else:
                device = self.hardware_i2c_devices.pop()
        else:
            hardware = False
            device = "gpioi2c0"

        if hardware is True:
            if kwargs['frequency'] != 100000.0 and kwargs['frequency'] != 400000:
                raise ValueError(f"{type(self)} only supports 100kHz and 400kHz for "
                                    "the built in i2c controller")
        return hardware, device

    def i2c_hardware_handler(self, device: str, kwargs):
        updated_i2c_dev = textwrap.dedent("""
        &{device} {{
            clock-frequency = < {freq} >;
            compatible = "nordic,nrf-twi";
            status =  "okay" ;
            pinctrl-0 = <&{device}_default_alt>;
            pinctrl-1 = <&{device}_sleep_alt>;
            pinctrl-names = "default", "sleep";
        }};
        &pinctrl {{
            {device}_default_alt: {device}_default_alt{{
                group1 {{
                    psels = <NRF_PSEL(TWIM_SDA, {sda_controller}, {sda_pin})>,
                            <NRF_PSEL(TWIM_SCL, {scl_controller}, {scl_pin})>;
                }};
            }};
            {device}_sleep_alt: {device}_sleep_alt{{
                group1 {{
                    psels = <NRF_PSEL(TWIM_SDA, {sda_controller}, {sda_pin})>,
                            <NRF_PSEL(TWIM_SCL, {scl_controller}, {scl_pin})>;
                    low-power-enable;
                }};
            }};
        }};
        """)
        sda_controller, sda_pin = self.get_device_and_pin(pin=kwargs['sda'])
        scl_controller, scl_pin = self.get_device_and_pin(pin=kwargs['scl'])

        updated_i2c_dev = updated_i2c_dev.format(device=device,
                                                 freq=int(kwargs['frequency']),
                                                 sda_controller=sda_controller.replace("gpio", ""),
                                                 sda_pin=sda_pin,
                                                 scl_controller=scl_controller.replace("gpio", ""),
                                                 scl_pin=scl_pin)
        self._manager.device_overlay_list.append(updated_i2c_dev)
        return (device, kwargs['sda'], kwargs['scl'])

    def spi_device(self) -> str:
        return "spi1"

    def spi_arg_parser(self, kwargs):
        return

    def handle_spi(self, **kwargs) -> Mapping[str, str]:
        clk_pin = kwargs.get("clk_pin")
        mosi_pin = kwargs.get("mosi_pin")
        miso_pin = kwargs.get("miso_pin")
        pins = self.spi_pins(clk=clk_pin['number'] if clk_pin is not None else None,
                             mosi=mosi_pin['number'] if mosi_pin is not None else None,
                             miso=miso_pin['number'] if miso_pin is not None else None)

        updated_spi_dev = textwrap.dedent("""
        &{device}  {{
            pinctrl-0 = <&{device}_default_alt>;
            pinctrl-1 = <&{device}_sleep_alt>;
            pinctrl-names = "default", "sleep";
        }};
        &pinctrl {{
            {device}_default_alt: {device}_default_alt{{
                group1 {{
                    psels = <NRF_PSEL(SPIM_SCK, {sck_controller}, {sck_pin})>,
                            <NRF_PSEL(SPIM_MOSI, {mosi_controller}, {mosi_pin})>,
                            <NRF_PSEL(SPIM_MISO, {miso_controller}, {miso_pin})>;
                }};
            }};
            {device}_sleep_alt: {device}_sleep_alt{{
                group1 {{
                    psels = <NRF_PSEL(SPIM_SCK, {sck_controller}, {sck_pin})>,
                            <NRF_PSEL(SPIM_MOSI, {mosi_controller}, {mosi_pin})>,
                            <NRF_PSEL(SPIM_MISO, {miso_controller}, {miso_pin})>;
                    low-power-enable;
                }};
            }};
        }};
        """)
        updated_spi_dev = updated_spi_dev.format(device=self.spi_device(),
                                                 sck_pin=pins['clk'][1],
                                                 sck_controller=pins['clk'][0].replace("gpio", ""),
                                                 mosi_pin=pins['mosi'][1],
                                                 mosi_controller=pins['mosi'][0].replace("gpio", ""),
                                                 miso_pin=pins['miso'][1],
                                                 miso_controller=pins['miso'][0].replace("gpio", ""))
        self._manager.device_overlay_list.append(updated_spi_dev)
        result = dict(pins.items())
        result['device'] = self.spi_device()
        return result

    def get_analog_channel(self, pin) -> int:
        return self.analogMapping[pin]

    def adc_device(self) -> str:
        return "adc"

    def validate_adc_pin(self, value):
        in_pin = value
        if in_pin not in self.analogMapping:
            raise cv.Invalid(f"{value} cannot be used as ADC on {self}")
        pin = self.get_analog_channel(in_pin)
        return pin

    def adc_arg_validator(self, **kwargs) -> None:
        #if kwargs['gain'].enum_value not in ("ADC_GAIN_1_3", "ADC_GAIN_2_3",
                                             #"ADC_GAIN_1"):
            #raise cv.Invalid(f"{self} does not support gain {kwargs['gain']}")
        if kwargs['ref'].enum_value not in ("ADC_REF_INTERNAL",
                                            "ADC_REF_VDD_1_2",
                                            "ADC_REF_VDD_1_3",
                                            "ADC_REF_VDD_1_4",
                                            "ADC_REF_EXTERNAL0",
                                            "ADC_REF_EXTERNAL1"):
            raise cv.Invalid(f"{self} does not support reference "
                             f"{kwargs['ref']}")

    def pre_compile_bootloader(self, args: list[str]) -> list[str]:
        args = super().pre_compile_bootloader(args)
        args.extend(
            [
                #"-DCONFIG_BOOT_SERIAL_WAIT_FOR_DFU=y",
                #"-DCONFIG_BOOT_SERIAL_WAIT_FOR_DFU_TIMEOUT=5000",
                #"-DCONFIG_BOOT_SERIAL_UART=y",
                #"-DCONFIG_MCUBOOT_INDICATION_LED=y"
            ]
        )
        return args

    def upload(self, flash_args: str, boot_dir: os.PathLike,
               proj_dir: os.PathLike, boot_info_path: os.PathLike,
               bootloader: bool, host: str):
        if which("mcumgr") is None or which("nrfutil") is None:
            raise ValueError(f"mcumgr and nrfutil must be installed to upload to {self}")
        if not bootloader:
            args = ["nrfutil",
                    "pkg",
                    "generate",
                    "--hw-version",
                    "52",
                    "--sd-req=0x00",
                    "--application",
                    f"{boot_dir}/build/zephyr/zephyr.hex",
                    "--application-version",
                    "1",
                    f"{boot_dir}/build/zephyr/mcuboot.zip"]

            result = run_external_process(*args)
            if result != 0:
                print("Creating boot image failed")
                return result
            install_args = ["nrfutil",
                            "--verbose",
                            "dfu",
                            "usb-serial",
                            "-pkg",
                            f"{boot_dir}/build/zephyr/mcuboot.zip",
                            "-p",
                            f"{host}",
                            "-b",
                            "1000000"]

            result = run_external_process(*install_args)
            if result != 0:
                print("Uploading boot image failed, is your device in reset mode")
                return result
            with open(boot_info_path, 'w') as f:
                f.write("")
            # wait for the board to reboot, it will say in upload mode for
            # 2 seconds listening for the device to flash
            time.sleep(2)
            from esphome.__main__ import choose_upload_log_host
            host = choose_upload_log_host(None, None, False, False, False)

        print("### FLASHING APPLICATION #####")
                      #f"--connstring=dev={host},baud=115200",
                      #f"--connstring=dev={host},baud=115200,mtu=512",
        image_args = ["mcumgr",
                      "--conntype=serial",
                      f"--connstring=dev={host},baud=115200",
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
