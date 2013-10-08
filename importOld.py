#!/usr/bin/env python

# (c) Robin Humble 2013
# licensed under the GPLv3 or later

import json, time, cPickle
import sys, os

# rarely used utility program.
# read old goo.gl files retrieved via eg. curl and import them into the db

groups = { 'b2g':['YYgisb', '7rr5ES'],
          'cm10':['2s2fEm'],
        'cm10.1':['Tvu9vb'],
        'cm10.2':['zv1Mqz', 'yk9BrL', 'gSfw52', 'xJR6V2'] }

dbName = '.goo.gl.pickle'

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

if __name__ == "__main__":
   # read and incorporate old .goo.`date` files with json data in them
   readCompatFiles(write='no')
