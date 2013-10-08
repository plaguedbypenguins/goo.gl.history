#!/usr/bin/env python

# (c) Robin Humble 2013
# licensed under the GPLv3 or later

import json, httplib, time, cPickle
import sys, os, math

# read a db of old goo.gl stats
# loop over all my goo.gl's and download all current stats
# group and sum same goo.gl's by download type
# compare current stats with last in db
# print
# if current dl's are the first after Sun 4am then add them to db


groups = { 'b2g':['YYgisb', '7rr5ES'],
          'cm10':['2s2fEm'],
        'cm10.1':['Tvu9vb'],
        'cm10.2':['zv1Mqz', 'yk9BrL', 'gSfw52', 'xJR6V2'] }

dbName = '.goo.gl.pickle'
countryName = '.country'

class gooGet():
   def __init__(self):
      self.conn = httplib.HTTPSConnection('www.googleapis.com')
      self.r = None

   def url(self,u):
      self.conn.request('GET', '/urlshortener/v1/url?shortUrl=http://goo.gl/' + u + '&projection=FULL')
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

   def get(self,k):
      if k == 'id':
         return self.j[k]
      if k == 'hits':
         k = 'shortUrlClicks'
      return self.j['analytics']['allTime'][k]

def getLatestGooGl():
   summed = {}
   d = gooGet()
   for g in groups.keys():
      s = {}
      s['hits'] = 0
      s['countries'] = {}
      s['referrers'] = {}
      for u in groups[g]:
         d.url(u)
         j = jsonSubset(d)
         print 'goo.gl', j.get('id')
         s['hits'] += int(j.get('hits'))
         for n in ( 'countries', 'referrers' ):
            for a in j.get(n):
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
      tCheck = []
      # only look at data for this group
      for i in db:
         t, d = i
         if g not in d.keys():
            #print g, 'skipping', d.keys()
            continue
         ts = time.gmtime(t)
         w = int(time.strftime( "%W", ts ))  # week of year, starting from 0
         w = time.strftime( "%Y", ts ) + "-%d" % ( 7*w )   # bins of week of year, eg. 2010-21
         #print w
         tCheck.append(w)
         # overwrite each to get the last of the week
         d[g]['timestamp'] = t
         self.w[w] = d[g]
         self.w[w]['timestamp'] = t

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

def printout(w, c):
   # print all-time stats instead of breaking things up by week
   if len(sys.argv) > 1 and sys.argv[1] == '-a':
      for g in sorted(groups.keys()):
         t = w[g].wholeTimes()[-1]
         d = w[g].wholeData()[t]
         print g
         print d['hits']
         prettyPrint(d, c)
         print
      return

   # compact one-line display of each week
   if len(sys.argv) > 1 and sys.argv[1] == '-c':
      # all available diff times
      t = []
      for g in groups.keys():
         t.extend(w[g].times())
      t.sort()
      diffT = uniq(t)
      # loop over the super-set of weeks
      for i in diffT:
         ii = dayToDate(i)
         if i == diffT[-1]:
            print 'this week so far'
         print ii,
         for g in sorted(groups.keys()):
            if i in w[g].times():
               d = w[g].data()[i]
               print g, d['hits'],
         print
      print 'extrapolate to end of week'
      print '          ',
      for g in sorted(groups.keys()):
         if i in w[g].times():
            h = w[g].endOfWeekHits()
            if h != None:
               print g, h,
      print
      print 'all time'
      print '          ',
      for g in sorted(groups.keys()):
         t = w[g].wholeTimes()[-1]
         d = w[g].wholeData()[t]
         print g, d['hits'],
      print
      # combine data for all groups this week together
      dd = None
      for g in groups.keys():
         if i in w[g].times():
            d = w[g].data()[i]
            dd = add(dd, d)
      #print 'combined', dd
      print 'this week combined hits', dd['hits']
      prettyPrint(dd, c)
      return

   # display each group separately
   for g in sorted(groups.keys()):
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

class countryLookup():
   def __init__(self):
      self.l = {}
      for f in open(countryName,'r').readlines():
         abrev = f.split()[0].strip()
         country = f[len(abrev)+1:].strip()
         self.l[abrev] = country
      #print self.l

   def lookup(self,abrev):
      if abrev in self.l.keys():
         return self.l[abrev]
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
   cntSpace = int(math.log10(bigCnt))
   for p in pairs:
      cnt, i = p
      i = i.lower()
      st = ' '*(cntSpace - int(math.log10(cnt))) + '%d %s' % (cnt, i)
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

def readCompatFiles(write):
   # read files like .goo.`date` which have a json goo.gl stats in them
   aa = {}
   for fn in sys.argv[1:]:
      print fn
      f = open(fn,'r')
      j = jsonSubset(f)
      f.close()

      t = fn.split('.')[2].strip()
      t = time.strptime(t, '%a %b %d %H:%M:%S EDT %Y')
      t = time.mktime(t)

      gid = j.get('id')

      s = {}
      s['hits'] = 0
      s['countries'] = {}
      s['referrers'] = {}
      s['hits'] += int(j.get('hits'))
      for n in ( 'countries', 'referrers' ):
         for a in j.get(n):
            i = a['id']
            cnt = a['count']
            #print i, cnt
            if a['id'] not in s[n].keys():
               s[n][i] = 0
            s[n][i] += int(cnt)
      aa[(t,gid)] = s
      print (t,fn,gid)

   # if sequential files have very similar times then try to group them together...
   k = aa.keys()
   k.sort()
   #print k
   tPrev = 0
   gPrev = None
   sPrev = None
   mode = ''
   db = []
   for i in k:
      t, gid = i
      grp = groupOfId(gid)
      s = aa[i]
      print '===='
      print i, gid, grp, s
      if abs(t-tPrev) < 120 and grp == gPrev:
         s0 = sPrev
         mode='summing'
      else:
         # not summing so need to add prev to db
         if sPrev != None:
            print 'adding to db', tPrev
            d = {}
            d[gPrev] = sPrev
            db.append((tPrev,d))
         s0 = {}
         s0['hits'] = 0
         s0['countries'] = {}
         s0['referrers'] = {}
         mode='alone'

      s0['hits'] += int(s['hits'])
      for n in ( 'countries', 'referrers' ):
         for i,cnt in s[n].iteritems():
            if i not in s0[n].keys():
               s0[n][i] = 0
            s0[n][i] += int(cnt)

      print mode, s0

      gPrev = grp
      tPrev = t
      sPrev = s0

   # handle the last entry (assumes 1 file on command line or pairs of summings)
   if len(sys.argv[1:]) == 1 or mode == 'summing':
      if sPrev != None:
         print 'adding last to db', tPrev
         d = {}
         d[gPrev] = sPrev
         db.append((tPrev,d))

   print db

   # load the old db
   db0 = cPickle.load(open(dbName, 'rb'))

   # add new data to the in-memory db
   db.extend(db0)

   print db
   if write == 'no':
      sys.exit(0)

   # save the new db
   cPickle.dump(db, open(dbName + '.tmp','wb'))
   os.rename(dbName + '.tmp', dbName)

   sys.exit(0)


def groupOfId(url):
   i = url.split('/')[3].strip()
   #print i
   for a in groups.keys():
      if i in groups[a]:
         #print 'grp', a
         return a
   return None

def main():
   db = []

   # load the old db
   db = cPickle.load(open(dbName, 'rb'))

   # download new goo.gl data
   if len(sys.argv) > 1 and sys.argv[1] == '-d':
      t = time.time()
      l = getLatestGooGl()
      #print l

      # add new data to the in-memory db
      db.append((t,l))

      # save the new db
      cPickle.dump(db, open(dbName + '.tmp','wb'))
      os.rename(dbName + '.tmp', dbName)
      #print db

   # sort by time
   db.sort()

   # load up country codes
   c = countryLookup()

   # split up all data into weekly bins and do diffs etc.
   w = {}
   for g in groups.keys():
      w[g] = week(db, g)

   printout(w, c)


if __name__ == "__main__":
   # read and incorporate old .goo.`date` files with json data in them
   #readCompatFiles(write='no')

   main()
