#!/usr/bin/env python3

"""
Measure resource usage of deployed systemd services.

Uses only the Python standard library.
Does not modify application data or LXD containers.
"""

import argparse
import platform
import statistics
import subprocess
import time

from datetime import datetime
from pathlib import Path


SERVICES = {
    "Falcon API": "hobby-server-monitor-api",
    "Metrics collector": "hobby-server-monitor-collector",
    "Nginx": "nginx",
}

DATA_FILES = {
    "SQLite": Path(
        "/var/lib/hobby-server-monitor/app.db"
    ),
    "TinyFlux": Path(
        "/var/lib/hobby-server-monitor/metrics.csv"
    ),
}

MIB = 1024 * 1024


def get_service_metrics(unit):
    result = subprocess.run(
        [
            "systemctl",
            "show",
            unit,
            "-p", "ActiveState",
            "-p", "MainPID",
            "-p", "MemoryCurrent",
            "-p", "CPUUsageNSec",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    values = {}

    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value

    if values.get("ActiveState") != "active":
        raise RuntimeError(
            f"{unit} is not active."
        )

    try:
        pid = int(values["MainPID"])
        memory = int(values["MemoryCurrent"])
        cpu = int(values["CPUUsageNSec"])

    except (KeyError, ValueError) as error:
        raise RuntimeError(
            f"Resource counters unavailable for {unit}."
        ) from error

    if pid <= 0 or memory <= 0 or memory >= 2**63:
        raise RuntimeError(
            f"Invalid service counters for {unit}."
        )

    return {
        "pid": pid,
        "memory": memory,
        "cpu": cpu,
    }


def get_file_sizes():
    return {
        name: path.stat().st_size
        for name, path in DATA_FILES.items()
    }


def take_sample():
    services = {
        name: get_service_metrics(unit)
        for name, unit in SERVICES.items()
    }

    return {
        "time_ns": time.monotonic_ns(),
        "services": services,
        "files": get_file_sizes(),
    }


def get_host_memory():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) * 1024

    raise RuntimeError("Cannot determine host memory.")


def print_results(samples):
    first = samples[0]
    last = samples[-1]

    elapsed = (
        last["time_ns"] - first["time_ns"]
    ) / 1_000_000_000

    print()
    print("=== Service Resource Results ===")
    print(f"Actual duration: {elapsed:.2f} seconds")
    print("CPU percentage basis: one logical CPU = 100%")
    print("RAM: systemd cgroup MemoryCurrent")
    print()

    for name in SERVICES:
        beginning = first["services"][name]
        ending = last["services"][name]

        if beginning["pid"] != ending["pid"]:
            raise RuntimeError(
                f"{name} restarted during measurement."
            )

        cpu_delta = ending["cpu"] - beginning["cpu"]

        if cpu_delta < 0:
            raise RuntimeError(
                f"{name} CPU counter reset."
            )

        cpu_percent = (
            cpu_delta / (elapsed * 1_000_000_000)
        ) * 100

        memories = [
            sample["services"][name]["memory"] / MIB
            for sample in samples
        ]

        print(f"{name}:")
        print(f"  Main PID: {ending['pid']}")
        print(f"  Average CPU: {cpu_percent:.3f}%")
        print(
            f"  Average RAM: "
            f"{statistics.mean(memories):.2f} MiB"
        )
        print(f"  Peak sampled RAM: {max(memories):.2f} MiB")
        print()

    print("=== Persistent Storage ===")

    for name in DATA_FILES:
        beginning = first["files"][name]
        ending = last["files"][name]
        growth = ending - beginning

        print(f"{name}:")
        print(f"  Initial size: {beginning:,} bytes")
        print(f"  Final size: {ending:,} bytes")
        print(f"  Net change: {growth:+,} bytes")
        print()

    print("PASS: Benchmark completed.")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "scenario",
        choices=[
            "no-tabs",
            "one-tab",
            "three-tabs",
            "active-containers",
        ],
    )

    parser.add_argument(
        "seconds",
        type=int,
        nargs="?",
        default=60,
    )

    args = parser.parse_args()

    if not 15 <= args.seconds <= 600:
        parser.error(
            "Duration must be between 15 and 600 seconds."
        )

    print("=== Hobby Server Monitor Benchmark ===")
    print(f"Scenario: {args.scenario}")
    print(
        "Started:",
        datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
    )
    print("OS:", platform.platform())
    print("Logical CPU threads:", __import__("os").cpu_count())
    print(
        "Host RAM:",
        round(get_host_memory() / MIB, 2),
        "MiB",
    )
    print("Requested duration:", args.seconds, "seconds")
    print("Sampling service RAM approximately every 5 seconds.")
    print()

    samples = [take_sample()]

    deadline = time.monotonic() + args.seconds

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        time.sleep(min(5.0, max(0.0, remaining)))

        samples.append(take_sample())

    print_results(samples)


if __name__ == "__main__":
    main()
