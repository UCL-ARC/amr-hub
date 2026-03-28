from __future__ import annotations

import time

import jax
import jax.numpy as jnp


def print_device_info() -> None:
    print("JAX version:", jax.__version__)
    print("Default backend:", jax.default_backend())
    print()

    devices = jax.devices()
    print("All detected devices:")
    for device in devices:
        print(f"  platform={device.platform}, id={device.id}, device={device}")

    print()
    print("CPU count:", len(jax.devices("cpu")))
    try:
        print("GPU count:", len(jax.devices("gpu")))
    except RuntimeError:
        print("GPU count: 0")
    print()


def test_array_placement() -> None:
    print("=== Array placement test ===")
    x = jnp.arange(10.0)
    y = jnp.sin(x)
    print("Result:", y)
    print("Device:", y.device)
    print()


def benchmark_on_device(device: jax.Device, size: int = 4000) -> None:
    print(f"=== Benchmark on {device.platform.upper()} ===")

    key1 = jax.random.key(0)
    key2 = jax.random.key(1)

    a = jax.random.normal(key1, (size, size), dtype=jnp.float32)
    b = jax.random.normal(key2, (size, size), dtype=jnp.float32)

    a = jax.device_put(a, device)
    b = jax.device_put(b, device)

    def matmul_sum(x: jax.Array, y: jax.Array) -> jax.Array:
        return jnp.sum(x @ y)

    fn = jax.jit(matmul_sum, device=device)

    t0 = time.perf_counter()
    out = fn(a, b)
    out.block_until_ready()
    t1 = time.perf_counter()
    print(f"First run  (compile + execute): {t1 - t0:.4f} s")

    t0 = time.perf_counter()
    out = fn(a, b)
    out.block_until_ready()
    t1 = time.perf_counter()
    print(f"Second run (execute only):     {t1 - t0:.4f} s")

    print("Output device:", out.device)
    print()


def main() -> None:
    print_device_info()
    test_array_placement()

    cpu = jax.devices("cpu")[0]
    benchmark_on_device(cpu)

    try:
        gpus = jax.devices("gpu")
    except RuntimeError:
        gpus = []

    if gpus:
        benchmark_on_device(gpus[0])
    else:
        print("No GPU detected by JAX.")


if __name__ == "__main__":
    main()
