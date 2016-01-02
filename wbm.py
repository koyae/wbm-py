# -*- coding: cp1252 -*-
from copy import copy,deepcopy
from datetime import *
from time import *

import bitstring
import math
import wave
import os
import re

i=-1


def get_bookmarks(filename,tidyFunc=None,shiftHackFirst=False):
##    try:
    handle = open(filename,'rb')
    info = []
    result=None
    filePosition=0
    try:
        while 1:
            result = next_mark(handle,startAt=filePosition,tidyFunc=tidyFunc)
            filePosition = result[1]
            info.append(result[0])
    except BufferError,e:
        print "Reached end of file."
##    except Exception,e:
##        raise e
    finally:
        try: handle.close()
        except: pass
    if shiftHackFirst: info[0]['framepos'] *= 16
    papertap(info)
    add_frame_conversions(info)
    return info

        
def next_mark(handle,startAt=0,tidyFunc=None):
    """ open .wbm file-handle -> (dictionary describing next bookmark,nextByte)

handle      --  An open file-handle to a .wbm wav bookmark file.
                Usually the results of open('filename.wbm','rb')

                
startAt     --  Integer. 0 or byte at which the namelength descriptor field
                begins. Throughout the function, this variable is incremented
                in order to provide the next `startAt` value.

*Return value*

    This function returns a dictionary of the form given below:

    { "rawname" : <string>, # the bookmark's name/description as read from .wbm
      "name"    : <string>, # the bookmark's name after cleanup via tidyname()
      "fn"      : <string>, # the basename of the sound-file the .wbm describes
      "framepos": <int>,    # position of bookmark measured in samples (frames)
      "lucky"   : <string>, # unknown meaning. reliably "\x77\x00"
      "lonely"  : <string>, # unknown meaning. reliably "\x01\00"
      "id"      : <int>,    # the bookmark's id-number (always positive)
      "vizn"    : <int>,    # the number of times the bookmark has been visited
      "epoch"   : <int>,    # seconds relative to 1970 last visit occurred
      "lastviz" : <string>  # human-legible timestamp version of 'epoch'
    }

    If add_frame_conversions() is executed on the dictionary, you'll also
    have the additional keys:

    { "secpos"  : <float>,  # bookmark's position represented in seconds
      "minpos"  : <float>,  # bookmark's position represented in minutes
      "hmspos"  : <tuple>,  # bookmark's position as (hour, minute, second)
      "bytepos" : <int>,    # bookmark's position into file's CONTENT-bytes
                            # .. which begin immediately after the audio-file's
                            # .. header
    }
                    
"""
    ############################################################################
    # helper functions: ########################################################
    def read_and_advance(length,startAt,post=None,shoutstring=""):
        """(byte source, bytecount to read, global position in file, cleanup fx)
           -> new byte-position.

        I use this function because some behavior under Windows for
        fileHandle.tell() is not reliable, presumably because of a bad
        C-language implementation which Python relies on the operating system
        to provide.
        
        I've seen a few problems:

            1. Consecutive calls to tell() fail to return the same
            result even though no read()s or seek()s have been performed.

            2. The return-value of tell() is not reliable between calls,
            possibly due to issue 1, described above.

        """
        if shoutstring: shout(shoutstring)
        post = post if callable(post) else lambda a:a
        raw = handle.read(length)
        if not raw: raise BufferError("EOF or otherwise failed to read bytes.")
        data = post(raw)
        newPos = startAt + length
        print "Data: {0} ({1}) starting at {2} (x{2:X}), stopping just before {3} (x{3:X})".format(repr(data),repr(raw),startAt,newPos)
        if shoutstring: shout(shoutstring)
        return data,newPos

    def process_posix_time(data):
        """ (4-byte time-relative-to-epoch data) -> positive or negative int """
        return decrt(data,bytecount=4)
    ######################################################## :helper functions #
    ############################################################################
    print "Starting at {} ({})".format(startAt,hex(startAt))
    tidyFunc = tidyname if not tidyFunc else tidyFunc
    if not startAt:
        handle.seek(7,os.SEEK_CUR) # allows header info be skipped
        startAt = handle.tell()
    else: handle.seek(startAt)
    markdict = {}
    namelength,startAt = read_and_advance(1,startAt,decr,'namelen1')
    if namelength == 0xFF:
        namelength,startAt = read_and_advance(4,startAt,decr,'namelen2')
    # ^ namelength is only used literally for values 254 and below, if the
    # ^.. bookmark's name/description is any longer than that, we read the
    # ^.. next 4 bytes as that number instead, and the first xFF is passed over
    markdict["rawname"],startAt = read_and_advance(namelength,startAt,'rawname')
    markdict["name"] = tidyFunc( markdict["rawname"] ) # bookmark name
    fnlength,startAt = read_and_advance(1,startAt,dec,'fnlength')
    fn,startAt = read_and_advance(fnlength,startAt,'filename')
    markdict["fn"] = fn # parent file name
    markdict["framepos"],startAt = read_and_advance(8,startAt,decr,'framepos')
    markdict["lucky"],startAt = read_and_advance(2,startAt)
    markdict["lonely"],startAt = read_and_advance(2,startAt)
    markdict["id"],startAt = read_and_advance(4,startAt,decr,'mark id')
    markdict["vizn"],startAt = read_and_advance(1,startAt,dec,'visitcount')
    shout("epoch")
    markdict["epoch"],startAt = read_and_advance(4,startAt,process_posix_time)
    shout("epoch")
    markdict["lastviz"] = strftime("%x %X",
                                   ( datetime(1970,1,1,0,0,0)
                                     + timedelta(0,markdict["epoch"])
                                   ).timetuple()
                                  )
##    print "at",handle.tell(),"(",hex(handle.tell()),")"
    print markdict
    return markdict,startAt+1


def tidyname(text):
    """ Tidy up the name of a bookmark """
    weirdChars = {'\xc2\xA0':' ', # nbsp -> regular space
                  '\xc3\xA9':'é', # accented 'e'
                  '\xe2\x80\x94':'-', # map long dash / em dash -> hyphen
                  '\xe2\x80\x98':'\'', # opening single quote -> straight single
                  '\xe2\x80\x99':'\'' # closing single quote -> straight single
                 }
    # ^ use the above mapping to replace characters from bookmark-names
    # ^.. before kicking out filename
    for k,v in dnumerate(weirdChars):
        text = text.replace(k,v)
    # remove double spaces:
    while "  " in text:
        text = text.replace("  "," ")
    return text


def add_frame_conversions(bookmarks,parentfile=None):
    """ iterable of bookmark-dictionaries -> None. Adds human-legible times
    to bookmarks. See bookmark-dictionary documentation under next_mark() for
    more info.

bookmarks  -- Iterable (such as a list). A collection of bookmarks *ALL
              REFERRING TO THE SAME PARENT-FILE;* passing bookmarks with mixed
              parent-files will result in incorrect conversions.
              
parentfile -- String. Optional. Full path to the file which the bookmarks
              describe.

    """
    if not parentfile: parentfile = bookmarks[0]["fn"]
    try:
        print "Opening: "
        print parentfile
        pf = WaveReadWrapper(parentfile)
        for bm in bookmarks:
            framepos = bm["framepos"]
            bm["bytepos"] =  framepos * pf.getsampwidth()
            bm["secpos"] = secpos = framepos/float(pf.getframerate())
            bm["minpos"] = secpos/60.0
            bm["hmspos"] = ( int(secpos//3600),
                             int(secpos//60),
                             secpos%60
                           )
        print "frames:", pf.getnframes()
        print "contentbytes:", pf.contentbyten
        print "file duration:", pf.sec_duration
##    except Exception, e:
##        print "Could not open parent file. Sorry."
##        raise e
    finally:
        try: pf.close()
        except: pass



class WaveReadWrapper(object):


    def __init__(self,filename):
        self.open(filename)
        

    def open(self,filename):
        wavehandle = wave.open(filename,'rb')
##        print dir(wavehandle)
        duration = wavehandle.getnframes() / float(wavehandle.getframerate())
        self.sec_duration = duration
        self.candy = wavehandle
        self.contentbyten = ( wavehandle.getsampwidth()
                              * wavehandle.getnframes() )
        # update dictionary:
##        owndict = copy(self.__dict__)
##        self.__dict__.update(wavehandle.__dict__)
##        self.__dict__.update(owndict)
        # :update_dictionary
        
    def __dir__(self):
        # Transparently expose Wave_read internals along with own attributes:
        dirl = deepcopy(dir(self.candy))
        dirl.extend( self.__dict__.keys() )
        return dirl
        

    def __getattr__(self,attr):
        # expose everything else from the wrapped object:
        return getattr(self.candy,attr)


    
def bindisplay(decimal,mingroups=0):
    s = bin(decimal).replace('0b','')
    fillamount = (4-len(s)%4)+len(s)
    # ^ fill to nearest halfbyte
    if len(s)%4 < mingroups:
        fillamount=mingroups*4
    s = s.rjust(fillamount,'0')
    reg = re.compile('\d\d\d\d')
    return reg.subn('\g<0> ',s)[0].strip()


def dec(s,pre=None,post=None):
    """ To decimal from binary data as string, then to something else if desired

s   --  hex string like "\x00\x00\x00\x2a"

pre --  optional function to run on the list/string ahead of time
        e.g. r() for little-endian hex numbers
        
post -- optional function to format the resulting integer, generally for display
        e.g. convert to group binary or simmilar
        
"""
    pre = (lambda a:a) if not pre else pre
    post = (lambda a:a) if not post else post
    f = lambda a: "{:0>02X}".format(ord(a))
    # ^ here, we show hex ints without the '0x' prefix, and pad with a
    # ^.. leading 0 if we would have a single-digit hex-character e.g. we'd show
    # ^.. '05' instead of just '5'
    s = pre(s)
    s = s if type(s)==type([]) else list(s)
    s = map(f, s)
    s = ''.join(s)
    return post(int(s,16))


def decf(s,pre=None):
    return dec(s,pre,float)


def decr(s,post=None):
    """ Convert bits/bytes representing an unsigned little-endian integer """
    return dec(s,r,post)


def decrt(s,bitcount=None,bytecount=None):
    """ Convert bits/bytes representing a two's-complement little-endian int """
    post = lambda a: two(a,bitcount,bytecount)
    return dec(s,r,post)


def dectest(s):
    if type(s) != type([]): s = s.split(" ")
    s.reverse()
    return int("".join(s),16)


def burp(s):
    s = s.replace(' ','')
    return s


def rburp(s):
    return burp(r(s))


def r(s,splitby=None):
    s = s if type(s)==type([]) else list(s)
    s.reverse()
    return ''.join(s)


def two(integer,bitcount=None,bytecount=None):
    """ Compute two's complement of an unsigned integer, based off a bit-width
    or byte-width """
    # setup:
    if bytecount and bitcount:
        raise ValueError("Pass either bytecount or bitcount, not both.")
    elif bytecount:
        bitcount = int(bytecount * 8)
    # :setup
    if ("{:0>"+str(bitcount)+"b}").startswith("0"):
    # if there's a leading zero, we have no negative offset, so do nothing:
        return integer
    else:
        sa = bitcount - 1 # compute shift-amount
        return (integer&int('1'*sa,2)) - ((integer>>sa)<<sa)
        # ^ above, subtract greatest digit from all lower digits.
        # ^.. For lesser digits, mask out the topmost digit using bitwise AND
        # ^.. For greatest digit, perform two bitshifts to get the form
        # ^.. "X0000..." where X is the greatest digit and 0 now holds the place
        # ^.. of all lesser digits.

##def two(s):
##    bi = bitstring.Bits(bin=s)
##    return bi.int


def dnumerate(dic):
    """ -> generator. Keyword `enumerate` analog for dictionaries """
    return ( (x,y) for x,y in zip(dic.keys(),dic.values()) )


def fudge(x):
    """ Until I discover precisely what's going on, we'll use this fudge-factor
function to approximate the error that's currently occurring."""
    return x/100000 + (x/2408300.0)


def snipe(x,contentbytes):
    """ Function which appears to give more accurate results than fudge() """
    return 4 * (  ( contentbytes / float(x) ) ** i  )


def shout(s):
    pad = ' '*((60 - len(s)) // 2)
    print pad+"--------- "+s.upper()+" ---------"+pad


def papertap(bookmarks):
    """ array bookmark dictionaries -> None. Fix 'factor-16' issue if present.

    Occasionally, bookmark-times are off by a factor of 16. This
    function corrects this, assuming bookmarks are still in the order found
    in the .wbm-file.

    ...Since they're saved in ascending order in a .wbm, the issue is easy to
    detect and correct (unless the first bookmark is off by this factor, of
    course). If you find this is the case, try get_bookmarks() again with the
    `shiftHackFirst`-option."""
    previous = bookmarks[0]
    for v in bookmarks[1:]:
        if v["framepos"] < previous["framepos"]:
            v["framepos"] *= 16
            print "FIXED:",v["name"]
        previous = v


def ebasename(name):
    """ Get the basename from a path minus the basename's extension (if any)."""
    return os.path.splitext( os.path.basename(name) )[0]


def ext(path):
    """ Get the file-extension from a path."""
    return os.path.splitext(path)[1]


def generate_tuples(bookmarks,lastFrameNumber):
    """ (iterable of bookmark-dictionaries) -> list of tuples """
    tuples = []
    for x in range(len(bookmarks[:-1])):
        tuples.append( (bookmarks[x]["framepos"], bookmarks[x+1]["framepos"]) )
    tuples.append( (bookmarks[-1]["framepos"],lastFrameNumber) )
    return tuples


def copy_pieces(tuples,source,dest="",sourceExt=True,noExt=False):
    """ Copy one or more spans from a .wav-file to one or more other files. """
    rhandle = wave.open(source,'rb')
    if not os.path.isfile(source):
        raise ValueError("No valid source-file provided.")
    destIsDir = os.path.isdir(dest)
    destDir = ""
    destEfn = ""
    destExt = ""
    if dest and not destIsDir:
        destDir = os.path.dirname(dest)
        destEfn = ebasename(dest)
        destExt = ext(dest) if not sourceExt else ext(source)
    elif dest and destIsDir:
        if (not noExt) and (not sourceExt):
            raise ValueError("noExt & sourceExt set False but dest is folder.")
        destDir = dest
        destEfn = ebasename(source)        
        destExt = ext(source)
    else:
    # if `dest` not provided:
        if (not noExt) and (not sourceExt):
            raise ValueError("noExt & sourceExt set False but dest not given.")
        destEfn = ebasename(source)
        destDir = os.path.dirname(source)
        destExt = ext(source)
    if noExt: destExt = "" # override other settings if true
    numberFormat = "{:0>" + str(int(math.ceil(math.log10(len(tuples))+1))) + "}"
    destBase = os.path.join(destDir,destEfn) + "_part_" + numberFormat + destExt
    for x,t in enumerate(tuples):
        rhandle.setpos(t[0])
        data = rhandle.readframes(t[1] - t[0])
        whandle = wave.open(destBase.format(x+1),'wb')
        whandle.setparams( rhandle.getparams() )
        whandle.writeframes( data )
        whandle.close()
##        print "Would write:", destBase.format(x+1)
