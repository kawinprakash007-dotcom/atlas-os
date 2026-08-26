class SystemMetrics:
    def __init__(self):
        self.total_events = 0
        self.validated_events = 0
        self.rejected_events = 0
        self.failed_events = 0

        self.approved_events = 0
        self.review_events = 0
        self.blocked_events = 0

        self.actions_executed = 0
        self.actions_failed = 0
        self.no_action_events = 0

        # Command metrics
        self.commands_total = 0
        self.commands_completed = 0
        self.commands_failed = 0
        self.commands_rejected = 0

    def get_summary(self) -> dict:
        return {
            "events": {
                "total": self.total_events,
                "validated": self.validated_events,
                "rejected": self.rejected_events,
                "failed": self.failed_events
            },
            "verdicts": {
                "approved": self.approved_events,
                "review": self.review_events,
                "blocked": self.blocked_events
            },
            "actions": {
                "executed": self.actions_executed,
                "failed": self.actions_failed,
                "no_action": self.no_action_events
            },
            "commands": {
                "total": self.commands_total,
                "completed": self.commands_completed,
                "failed": self.commands_failed,
                "rejected": self.commands_rejected
            }
        }
