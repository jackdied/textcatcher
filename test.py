import itertools
import mock
import time
import textcatcher as catcher
import unittest

""" test the textcatcher.CatchQueue and textcatcher.Catcher interfaces """

class AlwaysMatch(object):
    def match(self, txt):
        return True

class NeverMatch(object):
    def match(self, txt):
        return False

def nullfunc(*args): pass

def make_return_x(x):
    def inner(*args):
        return x
    return inner

def make_raise_x(x):
    def inner(*args):
        raise x
    return inner

class CatcherAPI(object):
    """ a class that defines the basic Catcher API and does nothing """
    start = end = NeverMatch()
    count = -1
    action = 'listen'
    def finished(self): pass
    def done(self): pass
    def line(self, txt):
        self.lines = [txt]
    def add_callback(self, *args): pass
    def rm_callback(self, *args): pass
    def clear_callbacks(self): pass
    # data API not included, FIXME

class TestCatchQ(unittest.TestCase):
    def setUp(self):
        self.catchq = catcher.CatchQueue()
        return

    def tearDown(self):
        self.catchq.done()
        del self.catchq
        return

    def test_empty(self):
        self.assertRaises(TypeError, self.catchq.line) # too few args
        self.assertRaises(TypeError, self.catchq.line, 'a', 'b') # too many
        self.catchq.line('') # just right
        self.assertFalse(self.catchq.obs)
        # make sure nothing means no harm
        new_text = self.catchq.line('old text')
        self.assertEqual(new_text, 'old text')
        return

    def test_weakref(self):
        ob = CatcherAPI()
        self.catchq.add(ob)
        self.assertEqual(len(self.catchq.obs), 1)
        del ob
        self.assertEqual(len(self.catchq.obs), 0)
        return

    def test_len(self):
        self.assertEqual(len(self.catchq), len(self.catchq.obs))
        ob = CatcherAPI()
        self.catchq.add(ob)
        self.assertEqual(len(self.catchq), len(self.catchq.obs))
        return

    def test_add_rm(self):
        ob = CatcherAPI()
        self.catchq.add(ob)
        self.assertEqual(len(self.catchq.obs), 1)
        self.catchq.rm(ob)
        self.assertEqual(len(self.catchq.obs), 0)
        # rm'ing a non existent object does nothing
        self.catchq.rm(ob)
        self.assertEqual(len(self.catchq.obs), 0)
        return

    def test_line(self):
        ob = CatcherAPI()
        self.catchq.add(ob)
        line = 'asdf'
        self.catchq.line(line)
        self.assertEqual(ob.lines, [line])
        return

    def test_done(self):
        ob = CatcherAPI()
        self.catchq.add(ob)
        self.catchq.done()
        self.assertFalse(self.catchq.obs)
        return

    def test_input_many(self):
        ob = CatcherAPI()
        self.catchq.add(ob)
        lines = ['asdf', 'xyz']
        self.catchq.input_many(lines)
        self.assertEqual(ob.lines, lines[-1:])
        return

    def test_actions(self):
        # test listen
        ob = catcher.Catcher(listen=True)
        ob.start = ob.end = AlwaysMatch()
        ob.parse = make_return_x('new text')
        self.catchq.add(ob)
        new_text = self.catchq.line('old text')
        self.assertEqual(new_text, 'old text')

        # test muffle
        ob.action = 'muffle'
        new_text = self.catchq.line('old text')
        self.assertEqual(new_text, '')

        # test filter
        ob.action = 'filter'
        self.assertTrue(self.catchq.obs)
        new_text = self.catchq.line('old text')
        self.assertEqual(new_text, 'new text')

        # test count
        ob.count = 1
        ob.action = 'filter'
        self.assertTrue(self.catchq.obs)
        new_text = self.catchq.line('old text')
        self.assertEqual(new_text, 'new text')
        self.assertFalse(self.catchq.obs)
        return

    def test_muffle_filter(self):
        # test that listeners don't muffle/filter
        ob = catcher.Catcher(listen=True)
        ob.start = ob.end = AlwaysMatch()
        self.catchq.add(ob)
        new_text = self.catchq.line('old text')
        self.assertEqual(new_text, 'old text')

        # make sure muffles that don't match don't muffle
        self.catchq.done()
        mob = catcher.Catcher(muffle=True)
        mob.start = mob.end = NeverMatch()
        self.catchq.add(mob)
        lob = catcher.Catcher(listen=True)
        lob.start = lob.end = AlwaysMatch()
        self.catchq.add(lob)
        self.assertEqual('old text', self.catchq.line('old text'))

        # if a muffle matches processing stops
        self.catchq.done()
        mob = catcher.Catcher(muffle=True)
        mob.start = mob.end = AlwaysMatch()
        self.catchq.add(mob)
        invalid = CatcherAPI()
        invalid.start = make_raise_x(ValueError())
        self.catchq.add(invalid)
        output = self.catchq.line('asdf') # shouldn't raise
        self.assertEqual('', output) # but should muffle

        # filters can stack
        self.catchq.done()
        foba = catcher.Catcher(filter=True)
        foba.start = foba.end = AlwaysMatch()
        foba.parse = make_return_x('textA')
        fobb = catcher.Catcher(filter=True)
        fobb.start = fobb.end = AlwaysMatch()
        fobb.parse = make_return_x('textB')
        self.catchq.add(foba)
        self.catchq.add(fobb)
        self.assertEqual('textB', self.catchq.line('text'))

        self.catchq.done()

    def test_exceptions(self):
        ob = catcher.Catcher(listen=1)
        ob.start = ob.end = AlwaysMatch()
        self.catchq.add(ob)
        ob.line = make_raise_x(ValueError())
        self.assertRaises(ValueError, self.catchq.line, '')

        # case where there is no CatchQueue exception handler
        self.assertFalse(self.catchq.handle_exception)
        class ResetCalled(Exception): pass
        old_reset = ob.reset
        ob.reset = make_raise_x(ResetCalled())
        self.assertRaises(ResetCalled, ob.reset)
        self.assertRaises(ResetCalled, self.catchq.line, '')

        # test with custom exception handler
        class HandlerCalled(Exception): pass
        self.catchq.handle_exception = make_raise_x(HandlerCalled())
        self.assertRaises(HandlerCalled, self.catchq.line, '')
        self.catchq.handle_exception = nullfunc
        ob.reset = make_raise_x(ResetCalled())
        self.assertRaises(ResetCalled, self.catchq.line, '')

    def test_str(self):
        # make some minimum guarantees about __str__
        self.assertTrue(getattr(self.catchq, '__str__', None) != None)
        self.assertTrue(self.catchq.__class__.__name__ in str(self.catchq))
        ob = catcher.Catcher(listen=1)
        self.catchq.add(ob)
        self.assertTrue(self.catchq.__class__.__name__ in str(self.catchq))


class TestCatcher(unittest.TestCase):

    def test_interface(self):
        # must pass one of count, listen
        self.assertRaises(ValueError, catcher.Catcher)
        catcher.Catcher(listen=True)
        catcher.Catcher(listen=True, count=1)
        # but bad counts are OK
        catcher.Catcher(listen=True, count='hello')

        # must include a start attr
        ob = catcher.Catcher(listen=1)
        self.assertRaises(AttributeError, ob.line, '')
        # must include one of expects, end, finished
        ob.start = AlwaysMatch()
        self.assertRaises(AttributeError, ob.line, '')
        # end
        ob.end = NeverMatch()
        ob.line('')
        del ob.end
        ob.reset()
        # expects
        ob.expects = 2
        ob.line('')
        del ob.expects
        ob.reset()
        # finished
        ob = catcher.Catcher(listen=1)
        ob.start = AlwaysMatch()
        ob.finished = make_return_x(False)
        class ParseCalled(Exception): pass
        ob.parse = make_raise_x(ParseCalled())
        ob.line('') # shouldn't raise
        ob.finished = make_return_x(True)
        self.assertRaises(ParseCalled, ob.line, '')

        return

    def test_reset(self):
        ob = catcher.Catcher(listen=1)
        ob.start = AlwaysMatch()
        ob.expects = 3
        self.assertEqual(len(ob.lines), 0)
        ob.line('')
        self.assertEqual(len(ob.lines), 1)
        ob.line('')
        self.assertEqual(len(ob.lines), 2)
        ob.reset()
        self.assertEqual(len(ob.lines), 0)

        # make sure reset is called in the natural course too
        ob.parse = nullfunc
        ob.line('')
        ob.line('')
        self.assertEqual(len(ob.lines), 2)
        ob.line('') # trip the expects, reset() is called internally
        self.assertEqual(len(ob.lines), 0)
        return

    def test_add_rm_call_callbacks(self):
        ob = catcher.Catcher(listen=1)
        class Called(Exception): pass
        callback = make_raise_x(Called())

        # add/rm
        self.assertEqual(len(ob.callbacks), 0)
        ob.add_callback(callback)
        self.assertEqual(len(ob.callbacks), 1)
        ob.rm_callback(callback)
        self.assertEqual(len(ob.callbacks), 0)
        # rm is silent if it does nothing
        ob.rm_callback(callback)
        self.assertEqual(len(ob.callbacks), 0)
        # add/add/rm
        self.assertEqual(len(ob.callbacks), 0)
        ob.add_callback(callback)
        ob.add_callback(callback)
        self.assertEqual(len(ob.callbacks), 2)
        ob.rm_callback(callback)
        self.assertEqual(len(ob.callbacks), 0)
        # clear
        ob.add_callback(callback)
        ob.clear_callbacks()
        self.assertEqual(len(ob.callbacks), 0)

        # call types
        ob.add_callback(callback)
        self.assertRaises(Called, ob.do_callbacks, 'end') # end is default
        ob.clear_callbacks()

        ob.add_callback(callback, 'end') # explicit
        self.assertRaises(Called, ob.do_callbacks, 'end')
        ob.do_callbacks('start') # no raise

        ob.clear_callbacks()
        ob.add_callback(callback, 'start')
        self.assertRaises(Called, ob.do_callbacks, 'start')
        ob.do_callbacks('end') # no raise

        # call priorities
        class CalledLow(Exception): pass
        callback_low = make_raise_x(CalledLow())
        ob.clear_callbacks()
        ob.add_callback(callback, priority=1) # lower is better
        ob.add_callback(callback, priority=100)
        self.assertRaises(Called, ob.do_callbacks, 'end')

        # more than one called
        class Counter(object):
            count = 0
            def __call__(self, ob):
                Counter.count += 1
        up_count = Counter()
        ob.clear_callbacks()
        self.assertEqual(Counter.count, 0)
        ob.add_callback(up_count)
        ob.add_callback(up_count)
        ob.do_callbacks('end')
        self.assertEqual(Counter.count, 2)

        # that it is called with the original object
        ob.clear_callbacks()
        class Keeper(object):
            called_with = None
            def __call__(self, ob):
                Keeper.called_with = ob
        keeper = Keeper()
        self.assertEqual(Keeper.called_with, None)
        ob.add_callback(keeper)
        ob.do_callbacks('end')
        self.assertEqual(Keeper.called_with, ob)

        return

    def test_line_callbacks(self):
        # test that callbacks are called properly from inside Catcher.line
        ob = catcher.Catcher(listen=1)
        ob.start = AlwaysMatch()
        ob.expects = 2
        ob.parse = nullfunc
        class Start(Exception): pass
        class End(Exception): pass
        class Parse(Exception): pass
        ob.add_callback(make_raise_x(Start()), 'start')
        ob.add_callback(make_raise_x(End()), 'end')
        parse_callb = make_raise_x(Parse())
        ob.add_callback(parse_callb, 'parse')
        self.assertRaises(Start, ob.line, '')
        self.assertRaises(Parse, ob.line, '')
        ob.rm_callback(parse_callb)
        self.assertRaises(End, ob.line, '')

        # make sure each callback is only called once
        counts = {'start' : 0, 'parse' : 0, 'end' : 0}
        def make_callb_counter(kind):
            def inner(c):
                counts[kind] += 1
            return inner
        ob = catcher.Catcher(listen=1)
        ob.start = ob.end = AlwaysMatch()
        ob.parse = nullfunc
        ob.add_callback(make_callb_counter('start'))
        ob.add_callback(make_callb_counter('parse'))
        ob.add_callback(make_callb_counter('end'))
        ob.line('')
        for k, v in counts.items():
            assert v == 1, (k, v)

        return
    def test_data_api(self):
        ob = catcher.Catcher(listen=1)
        self.assertRaises(KeyError, ob.__getitem__, 'foo')
        self.assertFalse('foo' in ob)
        ob.data['foo'] = 'bar'
        self.assertEqual('bar', ob['foo'])
        self.assertTrue('foo' in ob)
        return

    def test_done_funcs(self):
        # there was a bug where end.match, etc were called even if
        # start.match had never matched.  Test for this.
        class Bad(Exception): pass
        raise_bad = make_raise_x(Bad())
        ob = catcher.Catcher(listen=1)
        ob.start = NeverMatch()
        ob.end = AlwaysMatch()
        ob.expects = -1
        ob.end.match = raise_bad
        ob.finished = raise_bad
        ob.parse = raise_bad

        ob.line('')

    def test_start_once(self):
        # test that start.match isn't called if we are still matching
        ob = catcher.Catcher(listen=1)
        ob.start = AlwaysMatch()
        ob.end = NeverMatch()
        ob.parse = nullfunc
        ob.line('') # should match and start
        class Bad(Exception): pass
        ob.start.match = make_raise_x(Bad())
        ob.line('') # shouldn't raise
        ob.end = AlwaysMatch()
        ob.line('') # ends and resets
        self.assertRaises(Bad, ob.line, '') # should raise

    def test_history(self):
        ob = catcher.Catcher(listen=1)
        ob.start = ob.end = AlwaysMatch()
        ob.parse = nullfunc
        try:
            fake_time = itertools.count().next
        except AttributeError: # py3k
            _fake_time = itertools.count()
            fake_time = lambda: next(_fake_time)

        with mock.patch.object(time, 'ctime', fake_time):
            self.assertEqual(ob.history, [])
            ob.line('')
            self.assertEqual(ob.history, [0])
            ob.line('')
            self.assertEqual(ob.history, [1, 0])
            ob.line('')
            self.assertEqual(ob.history, [2, 1, 0])
            for x in range(10):
                ob.line('')
            self.assertEqual(len(ob.history), 10)

        ob.line('')
        # test that the regular ctime call works
        self.assertEqual(type(ob.history[0]), str)

    def test_tags(self):
        ob = catcher.Catcher(listen=1)
        self.assertEqual(type(ob.tags), set)

    def test_str(self):
        # make some minimum guarantees about __str__
        ob = catcher.Catcher(listen=1)
        self.assertTrue(getattr(ob, '__str__', None) != None)
        self.assertTrue(ob.__class__.__name__ in str(ob))
        ob.data['foo'] = 'bar'
        self.assertTrue('foo' in str(ob))
        self.assertTrue('bar' in str(ob))


    def test_multi_filter(self):
        # muffle
        ob = catcher.Catcher(listen=True)
        ob.start = catcher.TextMatch('START')
        ob.end = catcher.TextMatch('END')
        ob.action = 'muffle'
        ob.line('dont raise')
        self.assertRaises(catcher.Muffle, ob.line, 'START')
        self.assertRaises(catcher.Muffle, ob.line, 'hello')
        self.assertRaises(catcher.Muffle, ob.line, 'END')
        ob.line('dont raise')

        # filter
        ob.action = 'filter'
        ob.parse = make_return_x('filter text')
        ob.line('dont raise')
        self.assertRaises(catcher.Muffle, ob.line, 'START')
        self.assertRaises(catcher.Muffle, ob.line, 'hello')
        self.assertRaises(catcher.Filter, ob.line, 'END')
        ob.line('dont raise')
        self.assertRaises(catcher.Muffle, ob.line, 'START')
        self.assertRaises(catcher.Muffle, ob.line, 'hello')
        try:
            ob.line('END')
        except catcher.Filter as e:
            filter_line = e.line
        self.assertEqual(filter_line, 'filter text')
        ob.line('dont raise')

    def test_abort(self):
        ob = catcher.Catcher(listen=True)
        ob.start = AlwaysMatch()
        ob.finished = make_return_x(False)
        self.assertEqual([], ob.lines)
        ob.line('start')
        self.assertEqual(['start'], ob.lines)
        ob.finished = make_return_x(True)
        ob.add_callback(make_raise_x(catcher.AbortMatch()), when='parse')
        ob.parse = make_raise_x(ValueError()) # shouldn't be reached
        ob.line('end')
        self.assertEqual([], ob.lines)

class TestConcreteCatchers(unittest.TestCase):
    def test_call_and_response(self):
        # XXX see TODO, CallAndResponse should be killed
        ob = catcher.CallAndResponse('hello', 'world')
        self.assertEqual(ob.raw_input('asdf hello asdf'), 'world')

    def test_text_catcher(self):
        # first test TextMatch, a substitute for regexps
        ob = catcher.TextMatch('hello')
        self.assertFalse(ob.match('zzzz'))
        self.assertFalse(ob.match('hell'))
        self.assertTrue(ob.match('hello'))
        self.assertEqual(ob.index, 0)
        self.assertTrue(ob.match('xxx hello yyy'))
        self.assertEqual(ob.index, 4)

        # now the catcher that uses it
        ob = catcher.TextCatcher('hello', listen=True)
        class ParseCalled(Exception): pass
        ob.parse = make_raise_x(ParseCalled())
        ob.line('') # nothing happens
        self.assertRaises(ParseCalled, ob.line, 'hello')
        self.assertRaises(ParseCalled, ob.line, 'xxx hello yyy')

    def test_re_match(self):
        ob = catcher.REMatch('hel+o', listen=True)
        class ParseCalled(Exception): pass
        ob.parse = make_raise_x(ParseCalled())
        ob.line('help') # nothing happens
        self.assertRaises(ParseCalled, ob.line, 'helo')
        self.assertRaises(ParseCalled, ob.line, 'helllllo')

if __name__ == '__main__':
    unittest.main()
