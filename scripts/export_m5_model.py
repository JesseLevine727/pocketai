"""Export or independently recheck the ABI-v1 M5 model arena serialization."""
import argparse
import json
from ref.m5_arena import export_model, verify_export


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pack', default='build/m4_pack_v3')
    parser.add_argument('--output', required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    operation = verify_export if args.verify_only else export_model
    print(json.dumps(operation(args.pack, args.output), sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
