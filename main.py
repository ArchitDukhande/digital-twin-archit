import argparse
import json
from twin import DigitalTwin


def main() -> None:
    parser = argparse.ArgumentParser(description="Digital Twin CLI (local .md data)")
    parser.add_argument("question", type=str, help="Ask your digital twin a question")
    parser.add_argument("--debug", action="store_true", help="Show retrieved chunks and context for debugging")
    args = parser.parse_args()

    twin = DigitalTwin()  # loads .env and local data paths from defaults
    result = twin.answer(args.question, debug=args.debug)

    print("\n=== Answer ===\n")
    print(result["answer"])
    print()

    print(f"Confidence: {result.get('confidence', 'unknown').upper()}")
    print()

    if result.get("citations"):
        print("=== Citations ===\n")
        for i, cit in enumerate(result["citations"], 1):
            print(f"{i}. \"{cit['text']}\"")
            print(f"   Source: {cit['source']}")
            if cit.get("timestamp"):
                print(f"   Time: {cit['timestamp']}")
            print()

    if args.debug and result.get("debug"):
        print("=== Debug Info ===\n")
        # Convert datetime objects to strings for JSON serialization
        import datetime
        def json_serial(obj):
            if isinstance(obj, datetime.datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
        print(json.dumps(result["debug"], indent=2, ensure_ascii=False, default=json_serial))
        print()


if __name__ == "__main__":
    main()
