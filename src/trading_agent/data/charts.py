from __future__ import annotations

import base64
from pathlib import Path

from trading_agent.core.io import ensure_dir

PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sY1lX8AAAAASUVORK5CYII="
)


def write_placeholder_chart(output_path: Path) -> None:
    ensure_dir(output_path.parent)
    output_path.write_bytes(PLACEHOLDER_PNG)


def write_chart(rows: list[dict[str, object]], output_path: Path, title: str) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        write_placeholder_chart(output_path)
        return

    x_values = list(range(len(rows)))
    closes = [float(row["close"]) for row in rows]
    volumes = [float(row["volume"]) for row in rows]
    ma20: list[float] = []
    ma50: list[float] = []

    for index in range(len(closes)):
        left20 = max(0, index - 19)
        left50 = max(0, index - 49)
        ma20.append(sum(closes[left20 : index + 1]) / (index - left20 + 1))
        ma50.append(sum(closes[left50 : index + 1]) / (index - left50 + 1))

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, height_ratios=[4, 1])
    axes[0].plot(x_values, closes, label="Close", linewidth=1.2)
    axes[0].plot(x_values, ma20, label="MA20", linewidth=1.0)
    axes[0].plot(x_values, ma50, label="MA50", linewidth=1.0)
    axes[0].set_title(title)
    axes[0].legend(loc="upper left")
    axes[1].bar(x_values, volumes)
    axes[1].set_title("Volume")
    fig.tight_layout()
    ensure_dir(output_path.parent)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
