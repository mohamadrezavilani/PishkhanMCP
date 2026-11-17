"""Payment completion is not synonymous with a later settlement state.

Core IPGGhabzino.VerifyTransaction writes Paid on successful bills and Verify
then reports Complete. It does not promise a later Settle transition. This
completion rule is intentionally restricted to the reviewed IPG gateways.
"""

PAYMENT_STATES = {
    "Unknown": "unknown",
    "Undefined": "unknown",
    "Unpaid": "requires_user_action",
    "Paid": "paid_waiting_settlement",  # Legacy fallback, not a guaranteed transition.
    "InProcess": "processing",
    "Settle": "settled",
    "Return": "returned",
    "Unpayable": "unpayable",
}

GHABZINO_IPG_GATEWAYS = frozenset({"OnlinePayment_Sadad_Ghabzino", "OnlinePayment_AP_Ghabzino"})
SUCCESS_STATES = frozenset({"Paid", "Settle"})


def payment_progress(attempt):
    """Interpret the current observation without rewriting Core's raw states.

    A Paid payment can contain only some successful bills. Check every expected
    bill ID, including missing/conflicting observations, before ending the task.
    An empty expected set must not pass the all-bills test vacuously.
    """
    expected = set(attempt.bill_ids or [])
    observed = {}
    for bill in attempt.bill_statuses or []:
        if isinstance(bill, dict) and isinstance(bill.get("bill_id"), str):
            state = bill.get("status")
            state = state if isinstance(state, str) else "Unknown"
            observed.setdefault(bill["bill_id"], set()).add(state)

    def all_match(allowed):
        return bool(expected) and all(
            len(observed.get(key, set())) == 1 and observed[key] <= allowed for key in expected
        )

    all_paid = all_match(SUCCESS_STATES) if expected else None
    all_settle = all_match({"Settle"}) if expected else None
    confirmed = attempt.status in SUCCESS_STATES
    ghabzino_complete = (
        attempt.gateway in GHABZINO_IPG_GATEWAYS and attempt.status == "Paid" and all_paid is True
    )
    complete = ghabzino_complete or (attempt.status == "Settle" and (not expected or all_paid is True))
    financial = "paid" if ghabzino_complete else PAYMENT_STATES.get(attempt.status, "unknown")
    pending = financial in {"unknown", "processing", "paid_waiting_settlement"} or (
        confirmed and not complete
    )
    return {
        "financial_state": financial,
        "payment_confirmed": confirmed,
        "payment_complete": complete,
        "all_bills_payment_confirmed": all_paid,
        "all_bills_settlement_reported": all_settle,
        "completion_basis": (
            "ghabzino_ipg_all_bills_paid"
            if ghabzino_complete
            else "core_settle"
            if complete
            else "additional_verification_required"
        ),
        "requires_user_action": attempt.status == "Unpaid",
        "pending": pending,
    }
