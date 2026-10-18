"""Small command line entrypoint: python -m infertrace."""

import argparse
import json

from infertrace.config import discover, load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["capabilities"])
    parser.add_argument("--config")
    args = parser.parse_args()
    print(json.dumps(discover(load_config(args.config)), indent=2))


if __name__ == "__main__":
    main()
