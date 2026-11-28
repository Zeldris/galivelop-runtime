"""``python -m grun doctor ...`` and ``python -m grun vendor ...``"""
import sys

from . import doctor, vendor


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "vendor":
        return vendor.main(sys.argv[2:])
    return doctor.main()


if __name__ == "__main__":
    sys.exit(main())
