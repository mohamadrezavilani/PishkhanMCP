import json

from django.core.management.base import BaseCommand

from apps.agent.runner import run_turn


class Command(BaseCommand):
    help = "Run one real model-driven Pishkhan agent turn for an existing session."

    def add_arguments(self, parser):
        parser.add_argument("message", nargs="?", help="Message; omitted means read from stdin.")
        parser.add_argument("--session", required=True, help="Existing account-session UUID.")
        parser.add_argument("--conversation", help="Conversation UUID to continue.")

    def handle(self, *args, **options):
        message = options["message"]
        if message is None:
            import sys

            message = sys.stdin.read().strip()
        result = run_turn(options["session"], message, options.get("conversation"))
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
