"""Local pilot feedback/counters; no API or model calls."""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Avg, Count

from apps.portal.models import ChatTurn, Feedback, Visitor
from apps.portal.services import usage


class Command(BaseCommand):
    help = "Show pilot counters/feedback; optionally release a crashed turn after stopping Uvicorn."

    def add_arguments(self, parser):
        parser.add_argument("--feedback", action="store_true", help="Include submitted comments")
        parser.add_argument("--release-turn", help="Turn UUID after stopping Uvicorn; NEVER resends tools")
        parser.add_argument("--server-stopped", action="store_true")

    def handle(self, *args, **options):
        if options["release_turn"]:
            if not options["server_stopped"]:
                raise CommandError(
                    "Stop Uvicorn first, then add --server-stopped. Never release a running process."
                )
            turn = ChatTurn.objects.filter(pk=options["release_turn"], state="running").first()
            if turn:
                turn.state = "unknown"
                turn.response = {
                    "ok": False,
                    "error": {
                        "code": "TURN_INTERRUPTED",
                        "message": "Inspect saved operations before continuing. No tools were retried.",
                    },
                }
                turn.save(update_fields=["state", "response", "updated_at"])
                Visitor.objects.filter(pk=turn.visitor_id, active_turn=str(turn.pk)).update(active_turn="")
        result = {
            "visitors": Visitor.objects.count(),
            "turns": list(ChatTurn.objects.values("state").annotate(count=Count("id"))),
            "active_turns": list(
                Visitor.objects.exclude(active_turn="").values_list("active_turn", flat=True)
            ),
            "feedback": Feedback.objects.aggregate(count=Count("id"), average=Avg("rating")),
            "model_budget": usage(),
        }
        if options["feedback"]:
            result["comments"] = list(
                Feedback.objects.order_by("-created_at").values("rating", "comment", "created_at")[:100]
            )
        self.stdout.write(json.dumps(result, ensure_ascii=False, default=str, indent=2))
