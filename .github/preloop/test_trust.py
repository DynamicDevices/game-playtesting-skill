"""Exact event admission tests; no keys or provider calls."""
import unittest
from review_contract import InvalidReview
import trust


class FinalizerAdmissionTests(unittest.TestCase):
    def test_finalizer_needs_exact_signed_event_and_workflow_binding(self):
        admission = dict(explicit_posture_approval=True,
            workflow_path='.github/workflows/preloop-review-finalize.yml',
            event='workflow_run', producer_path='.github/workflows/preloop-review-publish.yml')
        self.assertEqual(trust.workload_events({'publication_finalizer': admission},
                                              'preloop-review-finalize.yml'), ['workflow_run'])
        for field, value in [('explicit_posture_approval', False), ('event', 'repository_dispatch'),
                             ('workflow_path', '.github/workflows/other.yml'),
                             ('producer_path', '.github/workflows/other.yml')]:
            with self.subTest(field=field), self.assertRaises(InvalidReview):
                trust.workload_events({'publication_finalizer': dict(admission, **{field: value})},
                                      'preloop-review-finalize.yml')
        with self.assertRaises(InvalidReview): trust.workload_events({}, 'preloop-review-finalize.yml')

    def test_existing_workload_events_do_not_gain_completion_authority(self):
        self.assertNotIn('workflow_run', trust.workload_events({}, 'preloop-review-publish.yml'))
        self.assertNotIn('workflow_run', trust.workload_events({}, 'preloop-review-trigger.yml'))
        with self.assertRaises(InvalidReview): trust.workload_events({}, 'unknown.yml')


if __name__ == '__main__':
    unittest.main()
