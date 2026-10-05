import argparse
import logging

from app.config import (
    get_metrics_interval,
)

from app.metrics.collector import (
    MetricsCollector,
)


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Hobby Server Monitor "
            "metrics collector"
        )
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Collect one cycle and exit."
        ),
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s "
            "%(message)s"
        ),
    )

    collector = (
        MetricsCollector()
    )

    if args.once:

        count = (
            collector.run_once()
        )

        print(
            f"Stored {count} metric points."
        )

        return

    collector.run_forever(
        get_metrics_interval()
    )


if __name__ == "__main__":
    main()
