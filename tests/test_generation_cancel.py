import unittest
from backend.server import AppState

class GenerationCancelTests(unittest.TestCase):
    def test_late_stop_does_not_cancel_the_next_question(self):
        state=AppState();old=state.begin_generation('s_test','old');current=state.begin_generation('s_test','new')
        state.set_cancel('s_test',True,request_id='old')
        self.assertTrue(state.is_cancelled('s_test',old));self.assertFalse(state.is_cancelled('s_test',current))
    def test_old_completion_does_not_clear_current_cancellation(self):
        state=AppState();old=state.begin_generation('s_test','old');current=state.begin_generation('s_test','new')
        state.set_cancel('s_test',True,request_id='new');state.clear_cancel('s_test',old)
        self.assertTrue(state.is_cancelled('s_test',current));self.assertFalse(state.is_current('s_test',old))
    def test_legacy_stop_still_cancels_current_generation(self):
        state=AppState();current=state.begin_generation('s_test','new');state.set_cancel('s_test')
        self.assertTrue(state.is_cancelled('s_test',current));state.clear_cancel('s_test',current)
        self.assertFalse(state.is_cancelled('s_test'))
