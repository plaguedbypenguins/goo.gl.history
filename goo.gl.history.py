#!/usr/bin/env python

# (c) Robin Humble 2013
# licensed under the GPLv3 or later

import json, httplib, time, cPickle
import sys, os, math, imp

# I made this 'cos I wanted to keep track of download stats for my various
# Android/CyanogenMod derived roms - FirefoxOS/b2g, cm10, cm10.1, cm10.2, etc.
# with various revisions of each. each new revision usually changes name
# (because of dates in the file name and/or cryptographic hashes from download
# sites) so generally each update needs a new download link.
#
# this little tool gathers together an arbitrary number of goo.gl links,
# sums up the stats by "group" where a group is eg. cm10.2, and then presents
# the stats in terms of (usually) downloads/week.
#
# only unprivileged google APIs are used so this can be used to track goo.gl
# stats for anyone. it may be slightly more convenient to use the authenticated
# google APIs to get a complete list of your own goo.gl links than to add them
# into the config file by hand, but then the urls still need to be grouped into
# categories by hand anyway, so hey. also it's much simpler just using the
# unprivileged APIs.


# the default config file name. this can be over-ridden by a command line
# argument eg. '-c /path/to/some_config_file.py' or '-c some_config_file'
configFile = 'goo.gl.history.conf.py'

# the config class that is loaded from a file in loadConfig() below
config = None

class gooGet():
   def __init__(self):
      self.conn = httplib.HTTPSConnection('www.googleapis.com')
      self.r = None

   def url(self,u):
      self.conn.request('GET', '/urlshortener/v1/url?shortUrl=http://goo.gl/' + u + '&projection=FULL&key=' + config.key)
      r = self.conn.getresponse()
      if r.status != 200:
         print 'Error:', r.reason
         r = None
      self.r = r
      self.u = u

   def read(self):
      if self.r == None:
         return ''
      return self.r.read()

class jsonSubset():
   def __init__(self,d):
      self.j = json.load(d)  # json calls .read()

   def get(self,k,range='allTime'):
      if k == 'id':
         return self.j[k]
      if k == 'hits':
         k = 'shortUrlClicks'
      try:
         return self.j['analytics'][range][k]
      except KeyError:
         if k in ( 'countries', 'referrers' ):
            return []
         elif k == 'hits':
            return '0'
         else:
            print 'error: jsonSubset: id ' + self.j['id']
            raise
      return None

class getLatestGooGl():
   def __init__(self):
      self.j = {}
      d = gooGet()
      for g in sorted(config.groups.keys()):
         for u in config.groups[g]:
            d.url(u)
            self.j[u] = jsonSubset(d)
            print u, g, self.j[u].get('hits'),
            if int(self.j[u].get('hits','week')) != 0:
               print self.j[u].get('hits','week'),
            print
      print

   def get(self, range='allTime'):
      summed = {}
      for g in config.groups.keys():
         s = {}
         s['hits'] = 0
         s['countries'] = {}
         s['referrers'] = {}
         for u in config.groups[g]:
            j = self.j[u]
            s['hits'] += int(j.get('hits', range))
            for n in ( 'countries', 'referrers' ):
               for a in j.get(n, range):
                  i = a['id']
                  cnt = a['count']
                  #print i, cnt
                  if a['id'] not in s[n].keys():
                     s[n][i] = 0
                  s[n][i] += int(cnt)
         summed[g] = s
      return summed


def dayToDate(d):
   t = time.strptime(d, '%Y-%j')
   ts = time.strftime('%Y-%m-%d', t)
   return ts

class week():
   """keep weekly data and diffs for one group"""
   def __init__(self, db, g):
      self.w = {}
      self.t = []
      self.g = g
      self.firstT = None
      tCheck = []
      # only look at data for this group
      for i in db:
         t, d = i
         if g not in d.keys():
            #print g, 'skipping', d.keys()
            continue
         ts = time.gmtime(t)
         w = int(time.strftime( "%W", ts ))  # week of year, starting from 0
         # bins of week of year in day format, eg. 2010-1, 2010-8, ...
         # note that day needs to start from 1 as %j is 1-366.
         w = time.strftime( "%Y", ts ) + "-%.3d" % ( 7*w + 1)
         #print w
         tCheck.append(w)
         # overwrite each to get the last of the week
         d[g]['timestamp'] = t
         self.w[w] = d[g]
         self.w[w]['timestamp'] = t

         # store the first timestamp
         if self.firstT == None:
            self.firstT = t

      # double check that the db really was sorted in time order
      assert(sorted(tCheck) == tCheck)

      # list of weeks for which we have data
      self.t = sorted(self.w.keys())

      # generate a set of valid diffs
      self.genDiffs()

      # calculate extrapolation of hits to the end of this week
      self.extrapolate()

   def wholeTimes(self):
      return self.t

   def wholeData(self):
      return self.w

   def times(self):
      return self.difft

   def data(self):
      return self.diffw

   def endOfWeekHits(self):
      return self.h

   def genDiffs(self):
      """generate diffs from pairs"""
      self.difft = []  # list of times for which we have a valid diff
      self.diffw = {}  # diffs that are the same format as w

      # handle length 0 (shouldn't happen?)
      if not len(self.t):
         return

      # include the first data point as an absolute as the one before that was implicitly zero
      t = self.t[0]
      self.difft.append(t)
      self.diffw[t] = self.w[t]

      # loop through pairs
      for i in range(1,len(self.t)):
         t = self.t[i]
         t_1 = self.t[i-1]
         #print i, t, t_1
         self.diffw[t] = self.diff(t_1, t)
         self.difft.append(t)

   def diff(self, t0, t1):
      a1 = self.w[t0]
      a2 = self.w[t1]
      #print a1
      #print a2
      diff = {}
      # a2 should always be a super-set of a1
      #  - that isn't quite true as goo.gl stats only show the top10
      #    countries and referrers, so smaller items can be in a1 but
      #    have fallen off the bottom of a2
      for n in ( 'hits', 'timestamp' ):
         diff[n] = a2[n] - a1[n]

      for n in ( 'countries', 'referrers' ):
         diff[n] = {}
         for i,cnt in a2[n].iteritems():
            diff[n][i] = a2[n][i]
            if i in a1[n].keys():
               diff[n][i] -= a1[n][i]
            if diff[n][i] == 0:
               del(diff[n][i])
      return diff

   def extrapolate(self):
      self.h = None
      if len(self.t) == 0:
         return

      if len(self.t) == 1:
         # if we only have 1 data point then assume records began
         # at the start of this week
         t = self.t[0]
         t1 = self.w[t]['timestamp']
         t = time.strptime(t, '%Y-%j')
         t0 = time.mktime(t)
         dt = t1-t0
         #print 'single dt', dt/(24*3600), '(days)'
      else:
         # otherwise, use the timestamp diff between the last 2 data points.
         # this is already calculated in the diff'd data
         t = self.difft[-1]
         dt = self.diffw[t]['timestamp']
         #print 'dt', dt/(24*3600), '(days)'

      # expanding this time interval to 1 week gives the best
      # contant-rate estimate of the number for this week.
      ratio = (24*7*3600)/dt
      t = self.difft[-1]
      self.h = int(ratio*self.diffw[t]['hits'])


def uniq(ll):
   l = []
   prev = None
   for i in ll:
      if i != prev:
         l.append( i )
      prev = i
   return l

def printout(w, c, modes):
   # print all-time stats instead of breaking things up by week
   if 'all-time' in modes:
      for g in sorted(config.groups.keys()):
         t = w[g].wholeTimes()[-1]
         d = w[g].wholeData()[t]
         print g
         print d['hits']
         prettyPrint(d, c)
         print
      return

   # compact one-line display of each week
   if 'compact' in modes:
      # all available diff times
      t = []
      for g in config.groups.keys():
         t.extend(w[g].times())
      t.sort()
      diffT = uniq(t)
      # loop over the super-set of weeks
      for i in diffT:
         ii = dayToDate(i)
         if i == diffT[-1]:
            print 'this week so far'
         print ii,
         for g in sorted(config.groups.keys()):
            if i in w[g].times():
               d = w[g].data()[i]
               print g, d['hits'],
         print
      print 'extrapolate to end of week'
      print '          ',
      for g in sorted(config.groups.keys()):
         if i in w[g].times():
            h = w[g].endOfWeekHits()
            if h != None:
               print g, h,
      print
      print 'all time'
      print '          ',
      for g in sorted(config.groups.keys()):
         t = w[g].wholeTimes()[-1]
         d = w[g].wholeData()[t]
         print g, d['hits'],
      print
      # combine data for all groups this week together
      dd = None
      for g in config.groups.keys():
         if i in w[g].times():
            d = w[g].data()[i]
            dd = add(dd, d)
      #print 'combined', dd
      print 'this week combined hits', dd['hits']
      prettyPrint(dd, c)
      return

   # display each group separately
   if 'separate' in modes:
      for g in sorted(config.groups.keys()):
         print g
         for i in w[g].times():
            ii = dayToDate(i)
            if i == w[g].times()[-1]:
               print 'this week so far'
            print ii,
            d = w[g].data()[i]
            print d['hits']
         print 'extrapolate to end of week'
         print '          ',
         h = w[g].endOfWeekHits()
         if h != None:
            print h
         prettyPrint(d, c)
         print
      return

class countryLookup():
   def __init__(self):
      self.l = {}
      for f in open(config.countryName,'r').readlines():
         abrev = f.split()[0].strip()
         country = f[len(abrev)+1:].strip()
         self.l[abrev] = country
      #print self.l

   def lookup(self,abrev):
      if abrev in self.l.keys():
         return self.l[abrev]
      if abrev != '--':
         print 'country code "' + abrev + '" is unknown. consider adding it to', config.countryName
      return 'Unknown'

def add(a1, a2):
   """utility function to sum data"""
   a = {}
   if a1 == None:  # make it easy to loop
      assert(a2 != None)
      return a2.copy()  # should really be a deep copy, but this is fine for current usage

   for n in ( 'hits', 'timestamp' ):
      a[n] = a2[n] + a1[n]

   for n in ( 'countries', 'referrers' ):
      a[n] = {}
      for i,cnt in a2[n].iteritems():
         a[n][i] = a2[n][i]
         if i in a1[n].keys():
            a[n][i] += a1[n][i]
      # add anything that's unique to a1
      for i,cnt in a1[n].iteritems():
         if i not in a2[n].keys():
            a[n][i] = a1[n][i]
   return a

def prettyPrint(d, c):
   hitsSum = d['hits']
   for n in ( 'countries', 'referrers' ):
      print n
      crSum = 0
      pairs = []
      for i,cnt in d[n].iteritems():
         if cnt <= 0:
            continue
         pairs.append((cnt,i))
         crSum += cnt
      if crSum != hitsSum:
         pairs.append((hitsSum - crSum, '--'))

      pairs.sort()
      #pairs.reverse()
      printTwoColumns(n, pairs, c)

def printTwoColumns(n, pairs, c):
   # find left column widths
   ps = []
   maxl = 0
   eo = 0
   bigCnt, i = pairs[0]
   if bigCnt <= 0:
      cntSpace = 1
   else:
      cntSpace = int(math.log10(bigCnt))
   for p in pairs:
      cnt, i = p
      i = i.lower()
      if cnt <= 0:
         cSpace = 1
      else:
         cSpace = int(math.log10(cnt))
      st = ' '*(cntSpace - cSpace) + '%d %s' % (cnt, i)
      if n == 'countries':
         st += ' %s' % c.lookup(i)
      if eo == 0:
         maxl = max(maxl, len(st))
      eo += 1
      eo %= 2
      ps.append(st)

   # print 2 columns
   eo = 0
   for p in ps:
      print p,
      if eo == 0:
         print ' '*(maxl - len(p)),
      if eo == 1:
         print
      eo += 1
      eo %= 2
   if eo == 1:
      print

def checkForDbMonthAgo(w, a, m):
   # look for missing db data a month ago that we might be able to fill in
   d = {}
   td = 0
   for g in config.groups.keys():
      t = w[g].wholeTimes()[-1]
      t0 = w[g].wholeData()[t]['timestamp']
      tm = t0 - 30*24*3600
      ts = time.gmtime(tm)
      tw = int(time.strftime( "%W", ts ))  # week of year, starting from 0
      tw = time.strftime( "%Y", ts ) + "-%.3d" % ( 7*tw + 1 )   # bins of week of year, eg. 2010-21
      tii = dayToDate(t)
      twii = dayToDate(tw)
      #print 'g', g, w[g].g, 't', t, tii, t0, 'tw', tw, twii, tm, 'firstT', w[g].firstT,
      #print tm > w[g].firstT, tw not in w[g].wholeTimes(),
      if tm > w[g].firstT and tw not in w[g].wholeTimes():
         print 'fill in', g, twii
         #print 'tw', tw, 'w[g].wholeTimes()', w[g].wholeTimes()
      else:
         #print
         continue

      td = tm
      a2 = a[g]  # all time
      a1 = m[g]  # in the last month
      #print 'all time', a2
      #print 'last month', a1
      diff = {}
      diff['hits'] = a2['hits'] - a1['hits']
      for n in ( 'countries', 'referrers' ):
         diff[n] = {}
         for i,cnt in a2[n].iteritems():
            diff[n][i] = a2[n][i]
            if i in a1[n].keys():
               diff[n][i] -= a1[n][i]
            if diff[n][i] == 0:
               del(diff[n][i])
      d[g] = diff
   return (td,d)


def usage():
   print sys.argv[0], '[-h|--help] [-d] [-f] [-s|-a] [-c configFile.py]'
   print '  -h  this message.'
   print '  -d  download new data from goo.gl.'
   print '  -f  append "fill-in" data to the database:'
   print '          data to cover missed time intervals can sometimes be'
   print '          synthesized using current and month-old goo.gl data.'
   print '          write such data to the db when it is found.'
   print ''
   print 'display modes:'
   print '      with no arguments the default (most compact) display mode is used.'
   print '  -s  separate display stats for each group instead of all groups at once.'
   print '  -a  like -s except display the sum of all stats instead of per week.'
   print ''
   print 'default: no download. display compact view of db.'
   sys.exit(0)

def parseArgs():
   modes = []
   if len(sys.argv) <= 1:  # the no args default
      modes.append('compact')
      return modes

   a = sys.argv[1:]

   if '-h' in a or '--help' in a:
      usage()

   global configFile
   if '-c' in a:
      i = a.index('-c')
      if len(a) < i+2:
         print '-c needs a filename argument'
         sys.exit(1)
      configFile = a[i+1]

   if '-d' in a:
      modes.append('download')
   if '-f' in a:
      modes.append('fill-in-write')

   # display modes
   if '-s' in a:
      modes.append('separate')
   elif '-a' in a:
      modes.append('all-time')
   else:
      modes.append('compact')

   return modes

def loadConfig():
   global config

   c = configFile
   # strip off the last .py, if any
   if c[-3:] == '.py':
      c = c[:-3]

   path = None
   if os.path.dirname(c) != '':  # an absolute path given
      path = []
      path.append(os.path.dirname(c))
      c = os.path.split(c)[-1]

   err = 0
   try:
      fp, pathname, description = imp.find_module(c, path)
   except ImportError:
      err = 1

   if err and path == None:
      # try again with cwd in path
      p = os.getcwd()
      # for some reason have to explicitly add cwd to the path in order to get
      # the conf file from the correct dir
      sys.path.insert(0,p)
      try:
         fp, pathname, description = imp.find_module(c, path)
         err = 0
      except ImportError:
         err = 1
   if err:
      print 'error: loadConfig: config file', configFile, 'not found'
      sys.exit(1)

   # check we are reading a .py and noy a .pyc or .pyo or ...
   if pathname.split('.')[-1] != 'py':
      print 'error: loadConfig: looking for .py config file, but only', pathname.split('.')[-1], 'found'
      sys.exit(1)

   config = imp.load_module('config', fp, pathname, description)

   err = 0
   keys = dir(config)
   for f in ('groups', 'dbName', 'countryName', 'keyFile'):
      if f not in keys:
         print 'error: loadConfig: "' + f + '" not found in', configFile
         if f == 'keyFile':
            print '  google now requires a key to access analytics. see'
            print '    https://developers.google.com/url-shortener/v1/getting_started#APIKey'
            print '  put this key into a file and add the filename (not the key) to this config'
         err = 1
   if err:
      sys.exit(1)

   # load the key from the keyfile specified in the config
   config.key = open(config.keyFile, 'r').readlines()[0].strip()

def main():
   # parse args
   modes = parseArgs()

   # load config
   loadConfig()

   # load the old db
   try:
      db = cPickle.load(open(config.dbName, 'rb'))
   except IOError:
      if not os.path.exists(config.dbName):
         if 'download' not in modes:
            print 'error: db load: "' + config.dbName + '" not found and not downloading. maybe run with -d to download something?'
            sys.exit(1)
         print 'warning: db load: "' + config.dbName + '" not found. initial run? setting db to be zero'
         db = []
      else:
         raise

   # download new goo.gl data
   goo = None
   if 'download' in modes:
      t = time.time()
      goo = getLatestGooGl()
      a = goo.get()
      #print 'a', a

      # add new data to the in-memory db
      db.append((t,a))

      # save the new db
      cPickle.dump(db, open(config.dbName + '.tmp','wb'))
      os.rename(config.dbName + '.tmp', config.dbName)
      #print db

   # sort by time
   db.sort()

   # load up country codes
   c = countryLookup()

   # split up all data into weekly bins and do diffs etc.
   w = {}
   for g in config.groups.keys():
      w[g] = week(db, g)

   printout(w, c, modes)

   # look back a month and see if we can fill in missing db records
   if goo != None:
      m = goo.get(range='month')
      #print 'm', m
      t,d = checkForDbMonthAgo(w, a, m)
      #print '(t,d)', t,d
      if d != {}:
         if 'fill-in-write' in modes:
            print 'writing'
            db.append((t,d))
            cPickle.dump(db, open(config.dbName + '.tmp','wb'))
            os.rename(config.dbName + '.tmp', config.dbName)
         else:
            print 'not writing month-ago fill-in. add -f to write'


if __name__ == "__main__":
   main()
