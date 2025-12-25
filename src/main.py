
from core.orchestrator import CoreOrchestrator


def main():
    print("[BOOT] System starting (skeleton mode)")

    orchestrator = CoreOrchestrator()
    orchestrator.run_once()

    print("[BOOT] System shutdown (skeleton mode)")


if __name__ == "__main__":
    main()
