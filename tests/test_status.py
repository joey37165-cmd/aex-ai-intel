import unittest

from app.domain.status import (
    DELIVERY_STATUSES,
    ITEM_STATUSES,
    REPORT_STATUSES,
    DeliveryStatus,
    ItemStatus,
    ReportStatus,
)


class StatusModelTests(unittest.TestCase):
    def test_item_lifecycle_values_are_stable(self):
        self.assertEqual(
            ITEM_STATUSES,
            frozenset({
                "discovered", "baselined", "notify", "review", "ignore", "sent",
            }),
        )
        self.assertEqual(ItemStatus.NOTIFY, "notify")
        self.assertEqual(ItemStatus.SENT, "sent")

    def test_delivery_and_report_states_are_distinct_contracts(self):
        self.assertEqual(DELIVERY_STATUSES, frozenset({"pending", "retry", "sent"}))
        self.assertEqual(REPORT_STATUSES, frozenset({"pending", "ready", "retry", "sent"}))
        self.assertEqual(DeliveryStatus.RETRY, "retry")
        self.assertEqual(ReportStatus.READY, "ready")


if __name__ == "__main__":
    unittest.main()
