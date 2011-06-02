# python imports
import re
import weakref
import operator
import time

"""Some basic classes that know how to read, and possibly swallow output
   Cather: a class the takes input to be acted on, listened to, or munged
   CatchQueue: a class that takes input and passes it on to Catchers, it also
               manages the actions for Catchers.

   They share a common subset of functions, so a CatchQueue can also pass on
   events to other CatchQueues it is managing just like Catchers.  This lets
   you make CatchQueues for specific purposes, like per-monster or per-mode
   that have a longer lifespan than Catcher objects, but you still want to
   add/expire.
"""

class CatcherException(Exception): pass
class Filter(CatcherException): pass
class Muffle(CatcherException): pass
class AbortMatch(CatcherException): pass

class CatchQueue(object):
  """ CatchQueue is a dispatcher class.  It keeps a list of Catcher objects
      and calls each of them for every new line of input.

      CatchQueue only keeps a weakref to each Catcher object so it is up
      to the original object creator to keep them alive.  This is so misbehaving
      or buggy owners don't leave Catchers around in a bad state.
  """

  def __init__(self, handle_exception=None):
    self.prioritized_obs = []
    self.handle_exception = handle_exception
    return

  def add(self, ob, priority = 100):
    ob_ref = weakref.ref(ob, self.rm)
    self.prioritized_obs.append((priority, ob_ref))
    self.prioritized_obs.sort(key=operator.itemgetter(0))
    return

  def expire_weakrefs(self):
    ''' clean out all weakrefs that have been garbage collected '''
    new_obs = []
    for pri, wr in self.prioritized_obs:
      if wr() is not None:
        new_obs.append((pri, wr))
    self.prioritized_obs[:] = new_obs

  @property
  def obs(self):
    self.expire_weakrefs()
    return [pair[1] for (pair) in self.prioritized_obs]

  def rm(self, ob):
    """ remove ob from this catcher.  ob can be either the original object,
        a weakref to that object, or a tag string """
    self.expire_weakrefs()
    new_obs = []
    for pri, wr in self.prioritized_obs:
      keep = True
      if wr() is None: # expired
        keep = False
      elif ob is wr or ob is wr(): # object or weakref identify
        keep = False
      elif hasattr(wr(), 'tags') and ob in wr().tags: # matching tag
        keep = False
      if keep:
        new_obs.append((pri, wr))
    self.prioritized_obs[:] = new_obs
    return

  def input_many(self, lines):
    """Like input(), but never returns a value"""
    for (line) in lines:
      self.line(line)
    return

  def line(self, line):
    ret = None
    remove = []
    for obref in self.obs:
      try:
        ob = obref()
        ob.line(line)
      except Muffle:
        line = ''
        break
      except Filter as e:
        line = e.line
        continue
      except Exception as e:
        if not self.handle_exception:
          ob.reset()
          raise
        else:
          self.handle_exception(e)
          ob.reset()
      finally:
        if ob.count == 0:
          remove.append(obref)

    for ob in remove:
      self.rm(ob)
    return line

  def __len__(self):
    return len(self.obs)

  def __str__(self):
    outstr = "%s:%d\n" % (self.__class__.__name__, id(self))
    for obref in self.obs:
      outstr += "   %s\n" % (str(obref()))
    return outstr

  def done(self):
    for obref in self.obs:
      obref().done()
    self.prioritized_obs[:] = []
    return

class Catcher(object):
  """ the Catcher class defines the API for Catcher classes.
      There is only one way to start capturing
        start # object must have a .match() method, like regexps
      There are three ways to finish capturing normally
        end # like start, finsih if end.match() returns True
        expects = <int> # finish after getting <int> lines of text
        finished # finish if self.finished() returns True
      There is one way to finish capturing irregularly
        raise catcher.AbortMatch().  This aborts and resets the catcher

      callbacks will be called in each of 'start' 'parse' 'end'
      self.add_callback(func, 'start') # call for normal start match
      self.add_callback(func, 'parse')   # call for normal finish _before_ parse
      self.add_callback(func, 'end')   # call for normal finish _after_ parse
      func will be called with this object as its only argument
  """
  callback_types = ['start', 'parse', 'end']

  def __init__(self, **opts):
    # calc pass-through or muffle
    self.action = None
    self.count = -1 # never expire by default
    if opts.get('muffle', None):
      self.action = 'muffle'
    elif opts.get('filter', None):
      self.action = 'filter'
    elif opts.get('listen', None):
      self.action = 'listen'
    else:
      raise ValueError("Must set one of muffle/filter/listen")

    if opts.get('count', None):
      self.count = opts['count']

    self.data = {}
    self.callbacks = []
    self.lines = []
    self.history = [] # list of timestamps of last 10 times the catcher matched
    self.tags = set()
    self.reset()
    return

  def reset(self):
    """ reset the captured lines, called after every completed match """
    self.lines = []
    return

  def parse(self):
    ''' empty parse by default '''
    pass

  def line(self, text):
    try:
      self._line(text)
    except AbortMatch:
      self.reset()
    return

  def _line(self, text):
    started = False # True if we just started on this line
    if not self.lines:
      # there is only one way to start, return true from self.start.match
      if self.start.match(text): # 'start' regexp-alike
        started = True
        self.lines.append(text)
        self.do_callbacks('start')
      else:
        return
    else:
      self.lines.append(text)

    if not list(filter(None, [hasattr(self, v) for (v) in ['expects', 'finished', 'end']])):
      raise AttributeError("catcher has no way to finish!")

    done = False
    # There are three ways to finish normally
    # 1) line count
    if hasattr(self, 'expects'):
      if len(self.lines) >= self.expects:
        done = True
    # 2) 'end' regexp-alike
    if not done and hasattr(self, 'end'):
      if self.end.match(text):
        done = True
    # 3) 'finished' func which returns True
    if not done and hasattr(self, 'finished'):
      if self.finished():
        done = True

    # only one way to finish abnormally
    if not done:
      if self.action in ('muffle', 'filter'):
        raise Muffle()
      return

    self.do_callbacks('parse')
    output = self.parse()
    self.update_history()
    self.do_callbacks('end')
    self.reset()
    self.count -= 1

    if self.action == 'muffle':
      raise Muffle()
    if self.action == 'filter':
      e = Filter()
      e.line = output
      raise e

    return

  def add_callback(self, func, when='end', priority=0):
    assert when in self.callback_types, when
    self.callbacks.append((priority, func, when))
    self.callbacks.sort(key=operator.itemgetter(0)) # sorts by priority
    return

  def clear_callbacks(self):
    self.callbacks[:] = []
    return

  def rm_callback(self, func):
    self.callbacks = [tup for (tup) in self.callbacks if tup[1] != func]
    return

  def do_callbacks(self, when):
    assert when in self.callback_types, when
    for pri, func, kind in self.callbacks:
      if kind == when:
        func(self)

  def __str__(self):
    out = "%s:%d|%d|%s" % (self.__class__.__name__, self.count, len(self.lines), id(self))
    for (k, v) in self.data.items():
      out += "%s:%s," % (str(k), str(v))
    return out

  def done(self): pass

  def update_history(self):
    now = time.ctime()
    self.history = [now] + self.history[:9]
    return

  # data convenience API
  def __getitem__(self, k):
    return self.data[k]

  def __contains__(self, k):
    return (k in self.data)

class CallAndResponse(object):
  def __init__(self, call, response):
    self.call = call
    self.response = response
    return
  def raw_input(self, text):
    if (text.find(self.call) != -1):
      return self.response
    else:
      return None

class Alias(Catcher):
  def __init__(self, **opts):
    Catcher.__init__(self, listen=1, filter=1)
    self.fromthis = opts['alias_from']
    self.tothis = opts['alias_to']
    self.start = re.compile('^%s(.*)' % (self.fromthis))
    self.end = self.start
    return
  def parse(self):
    text = "\n".join(self.lines)
    m = self.start.match(text)
    self.output = self.tothis + m.group(1) + "\n"
    raise DoneReparse()

  def __eq__(self, other):
    if (isinstance(other, Alias) and self.fromthis == other.fromthis):
      return 1
    else:
      return 0


class TextMatch(object):
  """ a class that matches text, suitable for use in catchers
      If the given text _appears anywhere in the line_ it will match
  """
  def __init__(self, text):
    self.match_text = text
    self.index = -1
    return
  def match(self, line):
    self.index = line.find(self.match_text)
    return self.index != -1

class TextCatcher(Catcher):
  """ a Catcher that matches if the text appears anywhere in a line """
  def __init__(self, text, **opts):
    Catcher.__init__(self, **opts)
    self.start = self.end = TextMatch(text)

class LineMatch(TextMatch):
  """ a Catcher that matches text for the whole line. """
  def match(self, line):
    return self.match_text == line

class LineCatcher(Catcher):
  """ a Catcher that matches if the line is equal to text """
  def __init__(self, text, **opts):
    Catcher.__init__(self, **opts)
    self.start = self.end = LineMatch(text)

class REMatch(Catcher):
  """ a Catcher that matches a regular expression """
  def __init__(self, re_text, **opts):
    Catcher.__init__(self, **opts)
    self.start = self.end = re.compile(re_text)
    self.orig_regexp = re_text
    return

