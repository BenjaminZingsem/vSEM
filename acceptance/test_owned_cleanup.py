"""Independent observation cases: completion, still-live, zombie and PID reuse."""
import os
import unittest

from scripts.owned_cleanup import process_identity,observe_owned_exit


class OwnedCleanupTests(unittest.TestCase):
    def observe(self, states, timeout=.06):
        now=[0.]
        calls=[0]
        def read(pid):
            index=min(calls[0],len(states)-1);calls[0]+=1
            state=states[index]
            if isinstance(state,Exception):raise state
            return state
        def sleep(delta):now[0]+=delta
        return observe_owned_exit([{'pid':20,'birth':100}],timeout,reader=read,
            clock=lambda:now[0],sleep=sleep)

    def test_running_then_zombie_then_absent_is_not_done_before_absence(self):
        result=self.observe([{'pid':20,'birth':100,'state':'R'},
            {'pid':20,'birth':100,'state':'Z'},None])
        self.assertTrue(result['owned_children_absent'])
        self.assertEqual(result['wait_seconds'],.04)
        self.assertEqual(result['children'][0]['states_seen'],['R','Z'])

    def test_running_child_at_deadline_fails(self):
        result=self.observe([{'pid':20,'birth':100,'state':'R'}])
        self.assertFalse(result['owned_children_absent'])
        self.assertEqual(result['wait_seconds'],.06)

    def test_zombie_at_deadline_fails(self):
        result=self.observe([{'pid':20,'birth':100,'state':'Z'}])
        self.assertFalse(result['owned_children_absent'])
        self.assertEqual(result['children'][0]['outcome'],'PRESENT')

    def test_reused_pid_is_not_mistaken_for_the_original_child(self):
        result=self.observe([{'pid':20,'birth':999,'state':'R'}])
        self.assertTrue(result['owned_children_absent'])
        self.assertEqual(result['children'][0]['outcome'],'PID_REUSED')

    def test_read_failure_is_unknown_and_never_a_pass(self):
        result=self.observe([PermissionError('unavailable')])
        self.assertFalse(result['owned_children_absent'])
        self.assertEqual(result['children'][0]['outcome'],'UNKNOWN')

    @unittest.skipUnless(os.path.isdir('/proc/self'),'Linux proc identity check')
    def test_actual_self_identity_is_stable(self):
        first=process_identity(os.getpid());second=process_identity(os.getpid())
        self.assertEqual(first['pid'],os.getpid())
        self.assertEqual(first['birth'],second['birth'])


if __name__=='__main__':unittest.main()
